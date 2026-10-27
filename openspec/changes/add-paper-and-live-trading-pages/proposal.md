## Why

目前项目有可工作的本地模拟交易 API，但模拟页面入口已从导航撤下，旧交易地址跳转到“我的持仓”。实盘的服务与页面代码只是暂缓草案，尚未注册、联通或验证。用户需要两个明确分开的页面：一个使用虚拟资金练习与复盘，另一个查看真实券商接入状态，并在完成接入验证后由本人逐笔操作真实委托。

## What Changes

- 新增一级页面“模拟炒股” `#/paper`：保留既有本地模拟账户，同时提供富途 `SIMULATE` 账户来源；两种模拟账本独立展示，不合并资金、订单或收益。
- 新增一级页面“实盘交易” `#/live`：以富途 OpenD 官方交易接口的 `REAL` 环境为首期接入，展示真实账户、限价委托预览、逐笔确认、订单状态、撤单和核对；未接通时展示原因并禁止发送。
- 页面交互参考开源 [VeighNa Trader](https://github.com/vnpy/vnpy) 的行情/委托/活动/成交分区与 [FreqUI](https://github.com/freqtrade/frequi) 的账户状态总览；按现有工作台视觉规范重新设计，不复制其代码或界面资产。
- 为富途模拟与实盘定义按 `trd_env`、稳定 `acc_id`、市场和 owner 隔离的连接、风控、状态及审计契约。仓库已有 QMT/盈立代码继续保留为未启用草案，不作为本 change 的首期交易接口。
- 调整旧 `#/accounts`、`#/orders`、`#/trading` 到模拟页的兼容跳转；`#/holdings` 继续表示手工登记的真实持仓，不与真实券商账户或模拟账本混用。

## Capabilities

### New Capabilities

- `paper-trading-page`: 独立模拟炒股页面、虚拟账户与订单交互。
- `live-trading-page`: 独立实盘交易页面、券商能力标识和真实委托流程。
- `broker-connection-and-order-safety`: 券商连接门槛、服务端风控、幂等、状态核对和审计。

### Modified Capabilities

无 OpenSpec 主规格可修改。实施时同步 `UX-CONTRACT.md`、`README.md` 与受影响的 `kitty-specs`，取消其中“实盘暂缓/交易页下线”的旧约定。

## Impact

- 前端：`prototype/app.js` 路由/导航、`prototype/paper.js` 与 `prototype/live.js`、`prototype/api.js`、样式和账户上下文入口。
- 后端：`app/main.py`、`app/paper.py`、`app/live.py`、`app/brokers/`、身份安全、MySQL 迁移、审计与运行状态。
- 部署：复用已有的富途 OpenD 行情进程，新增服务端交易上下文和权限验证；默认无实盘发送能力。模拟与真实交易是否可用取决于 OpenD 登录状态、账户类型、市场及接口权限。

## Scope

本 change 是实施规格，不表示两个页面或富途交易 API 已上线；本次不发送真实订单、不申请券商权限、不导入新的交易引擎。首期实盘仅在富途实际账户支持的港股/美股现金限价单；富途 `CN` 市场只允许模拟，A 股通 `HKCC` 需单独验收后再列入实盘。首期不提供 AI 实盘下单、自动策略实盘执行、融资融券、期权、出入金或跨账户资产合计。
