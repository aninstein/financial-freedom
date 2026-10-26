"""Volcengine SMS transport. ENV only; official V4 signer; no automatic sends/retries."""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass

import httpx

ENV_FIELDS = ('VOLC_SMS_ACCESS_KEY_ID','VOLC_SMS_SECRET_ACCESS_KEY','VOLC_SMS_ACCOUNT',
              'VOLC_SMS_SIGN','VOLC_SMS_TEMPLATE_ID','VOLC_SMS_PHONE_NUMBER')


class SMSUnavailable(RuntimeError): pass
class SMSRejected(RuntimeError): pass
class SMSUnknown(RuntimeError): pass


@dataclass(frozen=True, repr=False)
class SMSConfig:
    access_key: str
    secret_key: str
    account: str
    sign: str
    template: str
    phone: str
    code_param: str
    region: str

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.__dict__,sort_keys=True).encode()).hexdigest()

    @property
    def masked_phone(self):
        return self.phone[:5]+'****'+self.phone[-4:]


def config() -> SMSConfig:
    values=[os.getenv(key,'').strip() for key in ENV_FIELDS]
    if not all(values):
        raise SMSUnavailable('火山短信未配置完整，请填写服务端短信ENV后重启。')
    phone=values[-1]
    if re.fullmatch(r'1[3-9][0-9]{9}',phone):phone='+86'+phone
    # This owner-login release intentionally restricts delivery to one mainland recipient.
    if not re.fullmatch(r'\+861[3-9][0-9]{9}',phone):
        raise SMSUnavailable('VOLC_SMS_PHONE_NUMBER请配置中国大陆手机号。')
    code_param=os.getenv('VOLC_SMS_CODE_PARAM','code').strip()
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}',code_param):
        raise SMSUnavailable('短信模板验证码参数名无效。')
    region=os.getenv('VOLC_SMS_REGION','cn-north-1').strip()
    if region!='cn-north-1':
        raise SMSUnavailable('短信服务地域请使用cn-north-1。')
    return SMSConfig(*values[:5],phone,code_param,region)


def readiness():
    try:
        config()
        return {'configured':True,'provider':'volcengine','missing_env':[]}
    except SMSUnavailable:
        return {'configured':False,'provider':'volcengine','missing_env':[k for k in ENV_FIELDS if not os.getenv(k,'').strip()]}


async def send_code(settings: SMSConfig, code: str):
    from volcengine.Credentials import Credentials
    from volcengine.base.Request import Request
    from volcengine.auth.SignerV4 import SignerV4

    body=json.dumps({'SmsAccount':settings.account,'Sign':settings.sign,'TemplateID':settings.template,
                     'TemplateParam':json.dumps({settings.code_param:code},ensure_ascii=False),
                     'PhoneNumbers':settings.phone,'Tag':'finch-login'},ensure_ascii=False,separators=(',',':'))
    signed=Request()
    signed.schema='https';signed.method='POST';signed.host='sms.volcengineapi.com';signed.path='/'
    signed.query={'Action':'SendSms','Version':'2020-01-01'}
    signed.headers={'Host':signed.host,'Content-Type':'application/json'}
    signed.body=body
    # Sign directly with explicit credentials; do not load ~/.volc or unrelated model keys.
    SignerV4.sign(signed,Credentials(settings.access_key,settings.secret_key,'volcSMS',settings.region))
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10,connect=4),follow_redirects=False) as client:
            response=await client.post('https://sms.volcengineapi.com/',params=signed.query,headers=signed.headers,content=body.encode())
    except httpx.HTTPError:
        raise SMSUnknown('发送结果暂不确定，请先查看手机；勿立即重复发送。') from None
    if response.status_code>=500:
        raise SMSUnknown('短信服务暂不可用，发送结果待确认，请先查看手机。')
    if response.status_code!=200:
        raise SMSRejected('短信服务拒绝请求，请检查火山短信权限、签名及模板配置。')
    try: payload=response.json()
    except ValueError: raise SMSUnknown('短信服务响应无法确认，请先查看手机。') from None
    if not isinstance(payload,dict):raise SMSUnknown('短信服务响应无法确认，请先查看手机。')
    if payload.get('ResponseMetadata',{}).get('Error') or payload.get('Code') not in (None,0,'0','OK','Success'):
        raise SMSRejected('火山短信发送失败，请检查权限、余额、消息组、签名及模板。')
    result=payload.get('Result')
    if not isinstance(result,dict) or not result.get('MessageID'):
        raise SMSUnknown('未获得短信发送回执，请先查看手机。')
    # A provider receipt confirms acceptance, not handset delivery. Never return raw provider data.
    return {'accepted':True}
