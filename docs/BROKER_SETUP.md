> **当前接入：富途 OpenD。** 以下中信、国金、盈立内容是历史调研草案；这些适配器仍未注册到网页交易接口。

## 富途模拟与实盘

安装官方 OpenD，按官方流程登录。`FUTU_TRADE_ENABLED=true` 后，`#/paper?source=futu` 查询富途 `SIMULATE` 账户，`#/live` 仅显示明确列入 `FUTU_REAL_ACCOUNT_IDS` 的 `REAL` 港股/美股账户。界面和接口不会要求登录密码或交易密码。`FUTU_ENABLED` 只控制行情，不能启用交易。

```dotenv
FUTU_TRADE_ENABLED=true
FUTU_TRADE_SECURITY_FIRM=FUTUSECURITIES
FUTU_SIMULATE_ORDERS_ENABLED=true
LIVE_TRADING_ENABLED=false
FUTU_REAL_ORDERS_ENABLED=false
FUTU_REAL_ACCOUNT_IDS=
FUTU_REAL_SYMBOLS=
FUTU_MAX_ORDER_NOTIONAL=1000
FUTU_MAX_DAILY_NOTIONAL=3000
```

先用页面查询账户尾号、币种、资金和持仓，再在富途模拟环境验证预览、下单、撤单与核对。真实发送必须由本人在 OpenD 手动解锁，并同时设置两个实盘发送开关、真实 `acc_id` 白名单、证券白名单与额度。账户被发现或开关开启不代表已经解锁；富途 SDK 没有独立的只读解锁确认步骤。未提供真实权限时保持两个发送开关为 `false`。

2026-10-27 本机只读核验：OpenD 可连接，发现 4 个模拟账户（港股 2、美股 1、A 股 1）；四个账户的资金/持仓查询均成功，美股模拟账户的可买卖、当前委托和历史委托查询成功。当前未发现真实账户。没有向 OpenD 提交或撤销任何订单；下单、幂等、未知结果和撤单路径仅用替身测试验证。

只支持港美股真实现金限价委托；`CN` 仅富途模拟，其资金查询按富途 SDK 的 `CNH` 币种参数与标识展示；`HKCC` A 股通未接入。订单预览 45 秒有效，提交前重新查询可买卖数量与现金并预留 1% 费用缓冲。每单使用持久请求键；超时后保留未知状态、阻断该账户新单，需先查询富途订单核对，不自动重发。富途模拟环境未提供独立成交明细时，页面展示订单累计成交数量。费用和成交以富途回报为准；撤单请求不代表撤单成功。

参考：[富途交易概览](https://openapi.futunn.com/futu-api-doc/en/trade/overview.html)、[账户列表](https://openapi.futunn.com/futu-api-doc/en/trade/get-acc-list.html)、[下单](https://openapi.futunn.com/futu-api-doc/en/trade/place-order.html)、[交易解锁](https://openapi.futunn.com/futu-api-doc/en/trade/unlock.html)。

---

# 历史草案：中信 / 国金 / 盈立（当前未注册）

## 当前状态

已实现QMT网关与盈立HK版OpenAPI协议的代码适配、账户查询、限价预览/确认/发送、撤单、委托核对。**没有提供券商权限/凭据，未联通、未提交任何真实委托，也未宣称通过实盘联调。** 平台默认关闭真实发送；富途、盈透仅调研，尚无驱动。港股实盘本期暂缓。

账号和登录密码不是通用API凭据。请本人在券商官方渠道开通和登录；不要把密码、令牌、私钥发给Agent或贴入聊天。

## 中信证券 / 国金证券

先向客户经理确认：你的账户是否可开通QMT/miniQMT，是否有外部Python交易权限、支持哪版SDK及运行环境。品牌本身不能证明权限。若仅有PTrade，请取得券商对应文档，本次QMT驱动不能用于PTrade，不能标已接通。

有miniQMT时，在其支持的Windows机器上安装券商官方终端和配套xtquant，在官方终端本人登录。选择与供应商xtquant兼容且支持本网关依赖的Python版本（本代码需Python3.10+）；不使用第三方来源的股票软件安装包。

网关ENV（不要提交）：

```dotenv
QMT_USERDATA_PATH=D:\broker-terminal\userdata_mini
QMT_ACCOUNT_ID=
QMT_GATEWAY_TOKEN=
QMT_GATEWAY_ALLOW_ORDERS=false
QMT_GATEWAY_DATA_DIR=D:\finch-private\gateway-data
```

网关凭据由本人生成，至少32字符。先安装FastAPI、uvicorn和Pydantic；xtquant必须来自券商/迅投匹配版本，不能拿不明第三方包代替。

```sh
python -m uvicorn app.brokers.qmt_gateway:app --env-file .env.qmt --host 127.0.0.1 --port 8781
```

Mac平台通过自己控制的SSH通道转发到Windows回环端口，本平台QMT适配器仅接受回环网关URL。不要直接把网关监听到公网/局域网。两个券商各运行独立终端、配置、网关实例及凭据，使用不同转发端口与数据目录。

```dotenv
CITIC_QMT_GATEWAY_TOKEN=
SINOLINK_QMT_GATEWAY_TOKEN=
BROKER_CONNECTIONS_JSON=[{"id":"citic-a","label":"中信A股","provider":"qmt_http","market":"CN","gateway_url":"http://127.0.0.1:8781","token_env":"CITIC_QMT_GATEWAY_TOKEN","symbols":["CN:600519"],"max_order_notional":"1000","max_daily_notional":"3000","trading_enabled":false},{"id":"sinolink-a","label":"国金A股","provider":"qmt_http","market":"CN","gateway_url":"http://127.0.0.1:8782","token_env":"SINOLINK_QMT_GATEWAY_TOKEN","symbols":["CN:600000"],"max_order_notional":"1000","max_daily_notional":"3000","trading_enabled":false}]
LIVE_TRADING_ENABLED=false
```

白名单代码只示范配置格式，不是荐股。限额必须由本人根据账户设置；示例金额可能不足一手，不能当作可执行订单。查询阶段两个开关均保持false。完成联调、本人在终端确认对应账户后，再由本人设置网关发送开关和平台全局/连接发送开关。

## 盈立美股

从[盈立官方OpenAPI申请页](https://hk.usmartglobal.com/en/open-api)申请权限，核对开户实体及API版本。已实现的驱动基于[HK版官方接口文档](https://api-doc.usmart8.com/trade.html)，不是新加坡SG接口，也不是手机APP密码登录模拟器。

需要券商分配的Channel、本人授权的账户Token和RSA私钥文件；依文档对精确JSON正文签名，TLS校验开启。私钥文件仅本人可读（POSIX权限600）。若券商下发的签名/认证方案与公开旧文档不同，应先适配确认，不能盲目开启发送。部分账户下单仍需交易密码授权；当前驱动不收集/传输交易密码，遇到券商拒绝将保留拒绝状态，需按官方流程处理。

```dotenv
USMART_CHANNEL=
USMART_TOKEN=
USMART_PRIVATE_KEY_PATH=/private/path/usmart-signing-key.pem
# 将以下连接合并入已有BROKER_CONNECTIONS_JSON数组，不要覆盖其他连接。
# {"id":"usmart-us","label":"盈立美股","provider":"usmart","market":"US","channel_env":"USMART_CHANNEL","token_env":"USMART_TOKEN","private_key_path_env":"USMART_PRIVATE_KEY_PATH","symbols":["US:AAPL"],"max_order_notional":"1000","max_daily_notional":"3000","trading_enabled":false}
```

不自动在不同盈立实体/地区之间回退凭据。不接期权/融资/出入金。Token过期须按券商官方方式重新授权。该驱动使用Token绑定的默认交易账户，必须本人先核对账户与资产；不能把多资金账户混作一账户。

## 平台使用

进入`#/live`，先查看接入状态并主动查询真实账户。真实委托界面与模拟交易结构一致，但有显著“真实资金”标记；每笔都需本人确认。仅现金限价单，预览45秒有效，提交前再查券商现金可买/可卖数量，保留1%费用缓冲。

每次请求有持久化流水和本地订单。提交结果未知不会自动重发，也会阻断该连接新委托；先查询券商核对。QMT可通过精确策略标签恢复订单编号，盈立没有订单编号的情况可能仍需向券商查询原始请求流水。撤单不代表撤单成功，不能回滚已成交部分。

模拟清零不会动实盘表、真实账户或凭据。AI只有投研和明确授权的模拟交易工具，本版本不自动操作真实资金。

## 官方参考

- [迅投原生交易接口](https://dict.thinktrader.net/nativeApi/xttrader.html)：报单/撤单、资产/持仓/委托查询。
- [盈立官方FAQ](https://hk.usmartglobal.com/zh-cn/helpframe/142/detail/10831)：API权限申请与接口凭据。
- [盈立交易协议](https://api-doc.usmart8.com/trade.html)：签名、现金数量、限价单与委托查询。
- [富途交易范围](https://openapi.futunn.com/futu-api-doc/en/qa/trade.html)：A股实盘仅部分陆股通标的，不能替代大陆券商全市场账户。
