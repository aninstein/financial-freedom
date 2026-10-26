# 行情数据源接入

项目通过 AKShare 适配多个公共数据源。A 股全市场快照与日线历史行情优先使用东方财富网页行情接口（AKShare 的 `stock_zh_a_spot_em` / `stock_zh_a_hist`），日线接口异常时回退腾讯；行情列表会明确显示东方财富来源。港股、美股、基金和黄金按各自来源采集。富途 OpenD 和长桥 OpenAPI 是可选行情源；是否能收到实时推送取决于账户、市场权限和交易时段。浏览器每秒刷新本机快照，不代表上游每秒更新。需要账号或密钥的数据源由使用者自行申请，仓库不附带任何凭据。

## 东方财富网页行情

A 股快照和日线通过 AKShare 封装的东方财富网页接口获取，覆盖行情列表与个股 K 线。此来源不需要 Choice 账号，但它是网页侧接口，不提供正式 API 的 SLA；请求频率和接口字段可能变化。系统保留腾讯日线作为故障回退，行情卡片和数据源状态会展示实际来源。

此公共网页数据源仅按当前上游接口返回使用。需要把行情对外展示、转发或用于商业服务时，应先确认交易所和数据权利人的授权范围。东方财富用户协议说明其不保证行情信息的及时性、连续性和准确性，并对行情数据的复制或提供设置限制。

## 富途 OpenD

1. 按[富途官方 OpenD 安装与配置说明](https://openapi.futunn.com/futu-api-doc/quick/opend-base.html)安装 OpenD，在官方客户端登录并设置本地 API 监听端口。项目网页不会读取富途密码或验证码。
2. 在 Git 忽略的根目录 `.env` 中配置：

   ```dotenv
   FUTU_ENABLED=true
   FUTU_OPEND_HOST=127.0.0.1
   FUTU_OPEND_PORT=11111
   FUTU_POLL_SECONDS=3
   ```

3. 运行 `./scripts/docker-up.sh`。Docker Compose 会将容器内的 `FUTU_OPEND_HOST` 改为 `host.docker.internal`；本机直连仍使用 `127.0.0.1`。在「数据与模型」检查连接状态、源更新时间与订阅状态。

项目只调用行情上下文，使用[订阅接口](https://openapi.futunn.com/futu-api-doc/quote/sub.html)、[报价推送](https://openapi.futunn.com/futu-api-doc/quote/update-stock-quote.html)、[市场快照](https://openapi.futunn.com/futu-api-doc/quote/get-market-snapshot.html)和历史日线。行情订阅及历史数据需符合富途的[权限与额度说明](https://openapi.futunn.com/futu-api-doc/intro/authority.html)。订阅失败时页面可显示公共源快照或数据缺口；模拟交易在项目本地账本完成。

## 长桥 OpenAPI

1. 阅读[长桥 OpenAPI 快速开始](https://open.longbridge.com/zh-CN/docs/getting-started)，在长桥开发者平台申请当前 SDK 路径需要的 App Key、App Secret 和 Access Token，并确认目标市场的行情权限。
2. 在 Git 忽略的根目录 `.env` 中填写：

   ```dotenv
   INDEX_FEED_PROVIDER=longbridge
   LONGBRIDGE_APP_KEY=
   LONGBRIDGE_APP_SECRET=
   LONGBRIDGE_ACCESS_TOKEN=
   ```

3. 重启服务：`docker compose up -d --force-recreate web`。打开大盘指数页，检查来源名称、源时间、连接状态和错误提示。

当前实现仅使用长桥 `AsyncQuoteContext` 订阅预设指数的 `Quote`，不调用交易上下文。相关规则见[行情订阅说明](https://open.longbridge.com/zh-CN/docs/quote/subscribe/overview)和[行情权限说明](https://open.longbridge.com/zh-CN/docs/quote/overview)。OpenAPI 凭证应按账户级敏感信息保管；即使本项目只读取行情，凭证自身的权限仍由长桥账户决定。

## 凭据与发布

`.env`、`.runtime/secrets/`、`data/`、数据库备份和日志均只留本地，不应提交。公开仓库只提供 `.env.example`，其中所有凭据字段为空。提交前运行 `python3 scripts/check-staged-secrets.py`，并检查 Git 历史；扫描当前文件不能清除已有提交中的敏感内容。
