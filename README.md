# finfreedom

finfreedom 是面向国内用户的本地优先投资研究与账户工作台：用 AI 分析行情、板块、财报和自选股，维护个人持仓，进行本地模拟交易，并通过富途 OpenD 查看富途模拟/实盘账户。真实订单发送默认关闭，AI 没有实盘下单权限。

finfreedom 及相关商标归利长安（[lichangan.com](https://lichangan.com)）所有。项目中的历史技术标识（如 `finch` MCP 名称、浏览器存储键和容器项目名）为兼容现有配置与数据保留，不作为软件对外名称。

项目采用 [PolyForm Noncommercial 1.0.0](LICENSE)。允许非商业使用、学习和研究；商业使用需要单独授权。第三方依赖遵循各自许可证。

## 功能简介

| 模块 | 能做什么 | 页面 |
| --- | --- | --- |
| AI 投研 | 查询行情、新闻、流动性、板块、财务、基金披露和历史回测，输出带来源与时间的分析 | `#/chat` |
| 行情与研究 | 自选股、跨市场搜索、个股详情、K 线、指数、行业轮动和资金 | `#/watchlist`、`#/markets`、`#/stocks/...`、`#/indices`、`#/sectors`、`#/flows` |
| 公募基金 | 搜索东方财富基金目录，查看净值、收益、经理、费率、申赎状态和定期披露持仓 | `#/funds`、`#/funds/110022` |
| 我的持仓 | 按 CNY/HKD/USD 管理手工录入的真实持仓快照，支持截图识别草稿 | `#/holdings` |
| 模拟炒股 | 本地模拟账本、富途 `SIMULATE` 账户、模拟订单和受限 AI 模拟任务 | `#/paper`；入口在「更多工具 → 研究工具」 |
| 实盘交易 | 读取富途 `REAL` 账户资金/持仓/委托，逐笔预览和人工确认真实限价单 | `#/live`；入口在主菜单 |
| 资料与记忆 | 导入 PDF/TXT/Markdown/CSV，按页检索；保存投研对话摘要和投资记忆 | `#/documents`、`#/memory` |
| 工作台与扩展 | 管理右栏卡片、日历、Skills 和 MCP；内置 finfreedom 平台 MCP 可供 AI 只读分析交易数据 | `#/settings`、`#/calendar` |

模拟账本、本地持仓、富途模拟和富途真实账户始终分开显示，不合并资金或收益。普通研究只读；AI 只能在用户明确授权的固定本地模拟账户、股票白名单和额度内执行一轮模拟交易。

## 快速启动

### 环境要求

- Docker Desktop（包含 Docker Compose）
- macOS 或 Linux；Windows 建议使用 WSL2
- 如需富途数据：安装官方 [Futu OpenD](https://openapi.futunn.com/futu-api-doc/quick/opend-base.html)

### 启动服务

```bash
git clone <仓库地址> finfreedom
cd finfreedom
./scripts/docker-up.sh
```

脚本会创建 `.env`、MySQL 密钥和本地数据卷，构建并启动 MySQL、迁移任务、DeerFlow worker 和 Web。服务只监听 `127.0.0.1:8000`。

首次使用且没有账号时，创建本机唯一账号：

```bash
docker compose exec web python -m app.manage init-owner
```

打开 <http://127.0.0.1:8000> 登录。API 文档在登录后访问 <http://127.0.0.1:8000/docs>。

### 修改代码或配置后重新部署

只改 `.env`：

```bash
docker compose up -d --force-recreate --wait web deerflow
```

修改 Python、前端或依赖：

```bash
docker compose build web
docker compose up -d --force-recreate --wait web deerflow
```

也可以直接重新运行 `./scripts/docker-up.sh`。不要使用 `docker compose down -v`，否则会删除 MySQL 数据卷。部署后检查：

```bash
docker compose ps
curl http://127.0.0.1:8000/api/v1/health
```

## 配置与密钥

所有私密配置只写根目录 `.env`，不要提交到 Git、截图或聊天。`.env.example` 是配置字段清单；启动脚本会自动补齐本机认证密钥。

### AI 模型（需要 AI 投研时配置）

模型必须提供 OpenAI Chat Completions 兼容接口。密钥放在独立环境变量中，`MODEL_CONFIG_JSON` 只引用变量名：

```dotenv
MODEL_CONFIG_JSON='[{"provider":"openai","model":"你的模型名称","base_url":"https://你的兼容服务/v1","api_key_env":"AI_MODEL_API_KEY"}]'
PRIMARY_MODEL=你的模型名称
AI_MODEL_API_KEY=你的服务端密钥
MODEL_TEMPERATURE=0.2
MODEL_TIMEOUT_SECONDS=45
```

使用本机 Ollama 时：

```dotenv
MODEL_CONFIG_JSON='[{"provider":"ollama","model":"本地模型名称","base_url":"http://host.docker.internal:11434/v1"}]'
PRIMARY_MODEL=本地模型名称
```

模型运行在宿主机时，Docker 配置使用 `host.docker.internal`，不要填容器内的 `127.0.0.1`。图片识别还需要模型支持视觉输入，并在对应模型项增加 `"supports_vision":true`。

### 富途 OpenD（可选）

行情和交易是两个独立开关。登录、交易解锁和密码都在官方 OpenD 中完成，项目不会收集富途密码。

```dotenv
FUTU_ENABLED=true
FUTU_TRADE_ENABLED=true
FUTU_OPEND_PORT=11111
FUTU_TRADE_SECURITY_FIRM=FUTUSECURITIES
FUTU_SIMULATE_ORDERS_ENABLED=true

# 实盘默认关闭；只有本人完成验证后才填写
LIVE_TRADING_ENABLED=false
FUTU_REAL_ORDERS_ENABLED=false
FUTU_REAL_ACCOUNT_IDS=
FUTU_REAL_SYMBOLS=
FUTU_MAX_ORDER_NOTIONAL=1000
FUTU_MAX_DAILY_NOTIONAL=3000
```

`#/paper?source=futu` 读取富途模拟账户；`#/live` 只显示列入 `FUTU_REAL_ACCOUNT_IDS` 的港美真实账户。真实下单需要两个实盘开关、账户白名单、证券白名单、额度和本人在 OpenD 中完成交易解锁。当前富途 `CN` 只支持模拟，`HKCC` A 股通未接入。

### 长桥指数行情（可选）

只有需要长桥实时指数订阅时才填写：

```dotenv
INDEX_FEED_PROVIDER=longbridge
LONGBRIDGE_APP_KEY=你的AppKey
LONGBRIDGE_APP_SECRET=你的AppSecret
LONGBRIDGE_ACCESS_TOKEN=你的AccessToken
```

填写后重新部署 `web`；前端不会接触这些凭据。长桥当前仅用于行情，不用于交易。

### 其他常用配置

| 配置 | 作用 |
| --- | --- |
| `APP_PORT` | 宿主机访问端口，默认 `8000` |
| `AKSHARE_ENABLED` | 开关公共行情/研究采集，默认 `true` |
| `FUTU_POLL_SECONDS` | 富途行情轮询间隔，默认 `3` 秒 |
| `DATA_DIR` | 本地数据目录；Docker 中固定为 `/app/data` |
| `AGENT_MAX_TOOL_CALLS` | 单次 AI 研究最多工具调用数 |

## 数据来源

| 数据 | 默认来源 | 说明 |
| --- | --- | --- |
| A 股、港股、美股、基金和黄金行情 | AKShare 封装的公开网页接口 | 可能限流或字段变化；页面保留来源时间和数据缺口 |
| 公募基金目录与研究 | 东方财富 / 天天基金公开网页接口 | 目录每日缓存、详情按需同步并缓存半小时；目录含历史产品，能否购买以申购状态及交易平台为准 |
| 大盘、行业与北向资金 | 东方财富公开数据接口，部分大盘历史经 AKShare | 成交分类资金、主力净流入和北向成交数据各自保留口径；北向净买额上游为空时显示空值 |
| A 股日线 | 东方财富，异常时回退腾讯 | 用于研究和回测，不直接冒充实时成交价 |
| 富途行情/账户/委托 | 本机 Futu OpenD | 取决于登录状态、市场权限、交易环境和 OpenD 解锁状态 |
| 长桥指数 | Longbridge OpenAPI（可选） | 需要 App Key、App Secret、Access Token；当前只读行情 |
| 交易日历 | XSHG、XHKG、XNYS 与上海黄金交易时段 | 临时节假日以交易所公告为准 |
| 持仓、订单、研究、资料和记忆 | 本地 MySQL/InnoDB | 由 Docker volume 持久化，按账号隔离的内容不送往外部服务，除非用户选择模型分析 |

公共行情没有实时 SLA。基金当日净值估算仅在来源可核实时显示；当前公开接口缺失时展示数据缺口。北向实时买卖额、基金实时操作流水、付费研报全文和扫描版 PDF OCR 不在当前完整覆盖范围内；数据缺失时页面和 Agent 会明确说明。

基金研究接口：`GET /api/v1/research/funds?q=关键词&category=ETF&page=1` 返回全目录搜索；`GET /api/v1/research/funds/{六位代码}` 返回单只基金详情；两者可加 `refresh=true` 强制同步。资金接口 `GET /api/v1/research/flows` 同时返回大盘、行业与北向独立结果。数据同步只读取公开网页，不发起基金交易。

## AI 与 MCP

普通 AI 对话使用 DeerFlow worker，并通过受限工具桥接本项目数据。内置 `mcp__finch__catalog/read/write` 与页面同源：

- 可读：本地模拟账户/订单/AI 任务，富途 `SIMULATE`/`REAL` 账户、持仓和本平台委托，以及行情、研究、资料、日历和投资记忆。
- 可写：用户本人工作台内容、日历、自选、持仓快照和投资记忆。
- 不提供：富途下单、撤单、订单核对写入、交易密码、完整券商账户号和原始历史会话。

富途资源严格按账户 owner 和交易环境隔离；委托资源只代表本平台记录，不能当作券商全部历史。详细资源清单见 [docs/platform-mcp.md](docs/platform-mcp.md) 和 [Agent 扩展说明](docs/AGENT_EXTENSIONS.md)。

## 数据与文件位置

- MySQL：身份、持仓、模拟账本、行情、研究、文档和 AI 运行记录
- Docker volume `mysql-data`：MySQL 数据
- Docker volume `agent-data`：投资记忆、上传资料和 DeerFlow 状态
- `.runtime/secrets/`：本机生成的 MySQL、OpenD 启动密钥
- `.env`：本机私密配置，不进入镜像和 Git

备份：

```bash
./scripts/docker-backup.sh
```

备份文件位于 `.runtime/backups/`，应与 `.env` 和 `.runtime/secrets/` 一起加密保管。

## 安全边界

- 默认只监听本机回环地址，不提供公开注册和默认密码。
- 真实订单发送默认关闭，必须本人在独立交易页面逐笔确认。
- AI 没有实盘下单或撤单工具；模拟 AI 也受固定账户、证券白名单、资金和笔数限制。
- 不要把 API Key、OpenD 密码、交易密码、Access Token 或私钥提交到仓库。
- 这是研究和交易工作台，不构成投资建议，也不保证行情、成交或收益。

## 相关文档

- [富途与券商配置](docs/BROKER_SETUP.md)
- [行情数据源配置](docs/DATA_SOURCE_SETUP.md)
- [Agent 扩展与 MCP](docs/AGENT_EXTENSIONS.md)
- [平台 MCP 资源](docs/platform-mcp.md)
- [登录与安全恢复](docs/SECURITY.md)
- [投资记忆](docs/INVESTMENT_MEMORY.md)
- [本次交易页面 OpenSpec](openspec/changes/add-paper-and-live-trading-pages/design.md)
- [数据源调研](docs/STOCK_DATA_SOURCES.md)
