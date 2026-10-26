# 大盘行情来源与配置

当前页面每秒请求一次本机 /workspace/indices/live 快照。这个频率是**画面刷新频率**；上游行情是否秒级，取决于源、市场权限、网络与交易时段。日K及历史指标来自独立历史采集，不能用于盘中报价。

## 已接入

| 模式 | 来源 | 方式 | 当前条件 |
| --- | --- | --- | --- |
| 默认 | AKShare / 东方财富指数快照 | 服务端批量采集；至少每15秒启动一轮，失败保留旧值 | 无需密钥，可能被限流或断开；来源不保证实时 |
| 本机优先 | 富途 OpenD 官方行情接口 | 本地 OpenD 登录后订阅报价推送，并每 3 秒取跟踪标的快照补缺；前端每秒显示本机最新值 | 需官方 OpenD 与对应市场行情权限；没有 OpenD 时自动保留公共数据 |
| 可选 | Longbridge OpenAPI | 服务端长连接订阅报价，按变更推送 | 需 OpenAPI 凭证及相应市场行情权限 |

## 富途 OpenD 接入

1. 安装富途官方 [macOS OpenD](https://openapi.futunn.com/futu-api-doc/quick/opend-base.html)。在 **OpenD 自身**完成登录、首次问卷和协议；本项目网页没有富途密码输入框。
2. 项目 `.env` 设置 `FUTU_ENABLED=true`、`FUTU_OPEND_PORT=11111`。运行 `./run-local.sh` 或 `./scripts/docker-up.sh` 时，宿主机脚本会自动检查端口并在需要时打开官方 OpenD。Docker 容器使用 `host.docker.internal` 访问 Mac 上的 OpenD。
3. 打开「数据与模型」查看富途连接状态；可点击“打开富途 OpenD 登录窗口”切换到官方登录界面。页面按钮经已登录会话、CSRF 校验和本机私有令牌调用固定的应用启动动作，不传富途账号、密码或验证码。状态显示“行情已连接”表示当前收到快照；交易时段还需检查推送与实际延迟。

Docker Compose 的 Web 容器使用 `host.docker.internal` 访问这台 Mac 上的 OpenD；本机直接运行时继续使用 `127.0.0.1`。2026-10-26 已通过容器内官方 SDK 读取全部六个配置的 A 股指数、恒生指数及 `US.AAPL` 快照，并将 `US.AAPL` 富途快照写入平台数据库；三个市场的报价订阅请求均获 OpenD 接受。订阅推送的实际送达和各市场权限等级仍需在对应交易时段继续观察。

富途优先覆盖六个 A 股指数、恒生指数，以及自选、模拟盘持仓和挂单中的 A/港/美股与交易所 ETF；最多同时跟踪 55 个个人标的，香港市场单批最多 20 个。历史日线优先请求富途，失联或额度不足时退回原有公共源。全市场证券发现、财经新闻、财报、基金定期披露、板块资金流和黄金仍由现有公共数据管线提供，不冒充富途数据。富途官方权限页目前标明美股指数 API 暂不支持，标普/道指/纳指保留独立公共源并显示来源和时点。模拟下单仍只在本地模拟账本执行，代码不创建富途交易上下文。

本期采用[官方订阅推送](https://openapi.futunn.com/futu-api-doc/quote/update-stock-quote.html)与[快照接口](https://openapi.futunn.com/futu-api-doc/quote/get-market-snapshot.html)组合：有实时权限时按报价变化推送，没有订阅权限时保留带源更新时间的快照；快照请求间隔是 3 秒，浏览器 1 秒刷新只影响展示。快照链路已经实测；不能从快照请求成功推断用户拥有实时推送权限。

配置 Longbridge：在被 Git 忽略的根目录 .env 中设置 INDEX_FEED_PROVIDER=longbridge，并填写 LONGBRIDGE_APP_KEY、LONGBRIDGE_APP_SECRET、LONGBRIDGE_ACCESS_TOKEN，然后重启本机服务。前端不接触这些值。代码只创建行情 QuoteContext；**这些 OpenAPI 凭证本身可能具有账户交易权限**，应单独保管。港股 BMP 延迟行情没有推送权限，需要适当行情卡；A股实时权限受地区限制。订阅失败的指数会退回可用公共快照或显示缺失。

公共模式可设置 INDEX_POLL_SECONDS，服务端强制不低于10秒，并限制并发采集；各市场都不在交易或盘前阶段时降为每5分钟一轮。AKShare 背后是公共网页源，频繁采集可能限流；来源时间缺失时只展示“批量快照，延迟未知”。当前纳斯达克综合指数没有已核验的盘中映射；NDX 是纳斯达克100，不能代替它。成交量/额为来源原始单位，不跨源比较。

## 量化平台调研

- [上证所 Level-1 行情](https://www.sseinfo.com/services/assortment/level1/) 包括指数和即时行情，有行情网关/客户端接入及授权许可；不是给个人网页直接调用的免密 OpenAPI。
- [迅投 QMT / XtQuant](https://dict.thinktrader.net/nativeApi/xtdata.html) 的 subscribe_whole_quote 和 subscribe_quote 可通过本地 MiniQMT 客户端收取行情回调。适合已有 QMT 客户端与权限的环境；本 Mac 未配置 MiniQMT。
- [Longbridge 订阅概览](https://open.longbridge.com/zh-CN/docs/quote/subscribe/overview) 和[行情权限说明](https://open.longbridge.com/zh-CN/docs/quote/overview) 描述长连接、推送及 A/美/港市场差异；[凭证配置](https://open.longbridge.com/zh-CN/docs/getting-started) 需要 App Key、App Secret、Access Token。当前没有提供凭证，尚未做真实送达联调。
- [富途 OpenD 订阅接口](https://openapi.futunn.com/futu-api-doc/quote/sub.html) 支持报价推送，但需本地 OpenD 及对应市场的订阅额度和行情权限；本机 `11111` 已监听并完成快照联调，推送送达还需交易时段验证。
- [AKShare 官方接口列表](https://github.com/akfamily/akshare/blob/main/docs/tutorial.md) 包含指数实时快照接口；它是公共数据适配层，没有交易所直连推送的时效承诺。

## 当前限制

Longbridge 映射支持六个 A股指数、恒生、标普500、道琼斯；每个符号须在实际权限下核验。纳斯达克综合暂仅有历史日K。行情未实时联调前不保证秒级交易所更新，也不将刷新频率包装成数据新鲜度。
