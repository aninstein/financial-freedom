from __future__ import annotations

import base64
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class BrokerFailure(RuntimeError):
    """A read error or explicit broker rejection; never include credential-bearing responses."""


class BrokerUnknown(RuntimeError):
    """A write may have reached the broker. Never automatically replay."""


def secret(config, name):
    env_name = config.get(name, '')
    value = os.getenv(env_name, '') if env_name else ''
    if not value:
        raise BrokerFailure('缺少服务端券商凭据配置：' + name)
    return value


class QMTHTTP:
    def __init__(self, config):
        self.config = config
        self.url = config.get('gateway_url', '').rstrip('/')
        parsed = urlsplit(self.url)
        if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
            raise BrokerFailure('QMT网关仅允许本机HTTP回环地址；远程Windows终端请通过SSH隧道转发')
        self.token = secret(config, 'token_env')
        if len(self.token) < 32:
            raise BrokerFailure('QMT网关凭据至少32字符')

    async def call(self, path, body=None, write=False):
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                response = await client.request('POST' if body is not None else 'GET', self.url + path,
                                                headers={'Authorization': 'Bearer ' + self.token}, json=body)
            if response.status_code >= 500 and write:
                raise BrokerUnknown('网关返回异常，提交结果待核对')
            if response.status_code != 200:
                raise BrokerFailure('QMT网关拒绝请求，状态码 ' + str(response.status_code))
            return response.json()
        except (httpx.RequestError, ValueError) as exc:
            if write:
                raise BrokerUnknown('网关响应丢失，禁止自动重发') from exc
            raise BrokerFailure('无法读取QMT网关') from exc

    async def snapshot(self):
        return await self.call('/snapshot')

    async def capacity(self, order):
        return await self.call('/capacity', order)

    async def place(self, order, serial):
        return await self.call('/orders', {**order, 'client_order_id': str(serial)}, write=True)

    async def orders(self):
        result = await self.call('/orders')
        return result['orders']

    async def cancel(self, order_id):
        return await self.call('/cancel', {'broker_order_id': str(order_id)}, write=True)


class USmart:
    """uSMART HK OpenAPI HTTP contract; tokens/keys must be issued by the broker."""
    URL = 'https://open-jy.yxzq.com'

    def __init__(self, config):
        self.config = config
        if config['market'] != 'US':
            raise BrokerFailure('当前盈立适配器仅开放美股现金限价单')
        self.channel = secret(config, 'channel_env')
        self.token = secret(config, 'token_env')
        key_path = Path(secret(config, 'private_key_path_env')).expanduser()
        if os.name != 'nt' and key_path.stat().st_mode & 0o077:
            raise BrokerFailure('盈立RSA私钥文件需仅本人可读（600权限）')
        self.key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if not isinstance(self.key,rsa.RSAPrivateKey) or self.key.key_size<2048:
            raise BrokerFailure('需要券商支持的2048位或以上RSA私钥')

    async def call(self, endpoint, body, serial=None, write=False):
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()
        # The broker's published legacy contract specifies MD5withRSA, not an invented signing scheme.
        sign = self.key.sign(raw, padding.PKCS1v15(), hashes.MD5())
        headers = {'Content-Type': 'application/json;charset=UTF-8', 'Authorization': self.token,
                   'X-Channel': self.channel, 'X-Lang': '1', 'X-Dt': '3', 'X-Type': '1',
                   'X-Time': str(int(time.time() * 1000)), 'X-Request-Id': str(serial or (10**18 + secrets.randbelow(8*10**18))),
                   'X-Sign': base64.urlsafe_b64encode(sign).decode()}
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                response = await client.post(self.URL + '/stock-order-server/open-api/' + endpoint, content=raw, headers=headers)
            if response.status_code >= 500:
                if write: raise BrokerUnknown('盈立返回异常，提交结果待核对')
                raise BrokerFailure('盈立服务暂不可用')
            if response.status_code != 200:
                raise BrokerFailure('盈立拒绝请求，HTTP ' + str(response.status_code))
            result = response.json()
            if result.get('code') != 0:
                raise BrokerFailure('盈立返回错误代码 ' + str(result.get('code'))[:30])
            return result.get('data')
        except (httpx.RequestError, ValueError, TypeError) as exc:
            if write: raise BrokerUnknown('盈立响应丢失，禁止自动重发') from exc
            raise BrokerFailure('无法读取盈立数据') from exc

    async def snapshot(self):
        asset = await self.call('stock-asset', {'exchangeType': 5})
        holdings = await self.call('stock-holding', {'exchangeType': 5})
        if not isinstance(asset, dict) or not isinstance(holdings, list):
            raise BrokerFailure('盈立账户返回结构与当前文档不匹配')
        return {'currency': 'USD', 'cash': asset.get('enableBalance'), 'equity': asset.get('asset'),
                'positions': [{'instrument_id': 'US:' + str(p['stockCode']), 'quantity': p.get('currentAmount'),
                               'sellable': p.get('enableAmount'), 'name': p.get('stockName'),
                               'average_cost': p.get('costPriceAccurate')} for p in holdings],
                'as_of': int(time.time())}

    async def capacity(self, order):
        result = await self.call('trade-quantity', {'exchangeType': 5, 'stockCode': order['instrument_id'].split(':')[1],
                                                 'entrustProp': '0', 'entrustPrice': float(order['limit_price'])})
        if not isinstance(result, dict): raise BrokerFailure('盈立数量风控字段不可用')
        # Missing cash-only fields are rejected; margin capacity is never substituted.
        return {'buyable': result.get('cashEnableIntAmount'), 'sellable': result.get('saleEnableIntAmount'),
                'lot_size': result.get('handAmount')}

    async def place(self, order, serial):
        data = await self.call('entrust-order', {'serialNo': serial, 'entrustAmount': order['quantity'],
                                'entrustPrice': float(order['limit_price']), 'entrustProp': '0',
                                'entrustType': 0 if order['side'] == 'buy' else 1, 'exchangeType': 5,
                                'stockCode': order['instrument_id'].split(':')[1], 'sessionType': 0,
                                'forceEntrustFlag': False}, serial=serial, write=True)
        if not isinstance(data, dict) or not data.get('entrustId'):
            raise BrokerUnknown('盈立未返回可核验的订单编号')
        return {'broker_order_id': str(data['entrustId']), 'broker_status': str(data.get('statusName') or data.get('status'))}

    async def orders(self):
        data = await self.call('today-entrust', {'exchangeType': 5, 'pageNum': 1, 'pageSize': 100})
        if not isinstance(data, dict) or not isinstance(data.get('list'), list): raise BrokerFailure('盈立委托返回格式异常')
        return [{'broker_order_id': str(o.get('entrustId')), 'broker_status': str(o.get('statusName') or o.get('status')),
                 'instrument_id': 'US:' + str(o.get('stockCode')), 'quantity': o.get('entrustAmount'),
                 'filled_quantity': o.get('businessAmount'), 'filled_price': o.get('businessPrice')} for o in data['list']]

    async def cancel(self, order_id):
        await self.call('modify-order', {'actionType': 0, 'entrustAmount': 0, 'entrustId': int(order_id),
                                        'entrustPrice': 0, 'forceEntrustFlag': False}, write=True)
        return {'broker_order_id': str(order_id), 'broker_status': '撤单请求已发送，需查询券商结果'}


def adapter(config):
    if config['provider'] == 'qmt_http': return QMTHTTP(config)
    if config['provider'] == 'usmart': return USmart(config)
    raise BrokerFailure('这个接口尚未实现适配')
