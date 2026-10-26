# Financial Freedom

本地优先的量化工作台：市场状态、行情数据、观察列表、手工账户快照、模拟交易、确定性历史研究和 AI 投研/模拟交易 Agent。模拟订单写本地隔离账本；当前专注模拟盘与投研，实盘接入暂缓。

## 当前能力

- FastAPI 本地服务，默认只绑定 `127.0.0.1:8000`。
- AKShare 行情适配器：A 股/创业板、港股、美股、ETF、开放式基金公布净值、上海黄金交易所 Au99.99。A 股东方财富失败后依次尝试腾讯和新浪接口；港股全市场端点失败或超时时，观察列表内的港股代码改用新浪单票报价，保留源时间并按年龄标记新鲜度。美股全市场现价端点在当前环境失败，新浪全市场需要抓取 917 页，本地未启用；对观察列表内的美股，改用新浪同源的单票延迟报价（公开接口标注 15 分钟延迟），无法获取时才回退到日线收盘价。日线数据只用于查看，不能用于模拟成交。
- 交易所日历状态：XNYS、XSHG、XHKG；上海黄金按交易所常规时段及 XSHG 假日表推算，节假日临时安排以 SGE 公告为准。
- MySQL/InnoDB 持久化行情快照、日线历史、观察列表、身份、研究记录和模拟账本；Docker Compose 管理数据库、Web 与 Agent worker。
- 手工录入的账户快照与模拟账户分开展示；按币种保存，不做无 FX 来源的汇总换算。
- 五类独立模拟盘：美股、港股、A股主板、创业板、科创板。可自行开户/设置初始虚拟资金、查看现金/冻结/可卖持仓/盈亏。原有账户与订单保留；新增三类A股默认盘，分别100万元虚拟资金。港股同步HKEX官方每手股数，也可明确录入手工模拟规则。主板/创业板100股整数买入，科创板至少200股整数递增，A股T+1可卖。
- 支持 AKShare 日线手动拉取和观察列表自动回补/增量采集，带内容哈希的数据集版本，以及 SMA 趋势基线回测；回测包含买入持有对照、手续费/滑点假设、最大回撤、年化波动和夏普比率，使用非复权数据并明确标记为历史研究。
- 实盘代码仅保留为草案，不注册路由、不读取券商配置或调用交易接口。
- AI Agent 可用服务端 `.env` 配置 OpenAI-compatible 或 Ollama 模型；可读取行情/日线、筛选基金、查询基金定期报告披露的持仓和重大买入/卖出变动、读取 A 股财务摘要、运行 SMA 历史回测，并检索用户上传的文本 PDF/TXT/Markdown/CSV。基金操作数据是历史披露，不是实时交易流水。所有研究保留运行记录和来源证据；普通聊天继续只读；“账户与模拟盘”可明确授权AI在固定账户、股票白名单、金额和笔数限额内执行一轮模拟买卖，保留模型、原因、来源和实际订单。

## Agent 工作空间

首页是投研对话，左侧菜单进入独立数据页面。聊天中的股票标识和证据卡片可打开个股详情；板块卡片打开成分股与行业资金页。个股/板块页面的“询问 Agent”会把上下文放入草稿，由用户发送。

- `#/chat`：连续对话、最近研究、来源证据与账户上下文选择。
- `#/watchlist`：个人关注标的、行情、均线和波动指标。
- `#/markets`：跨市场搜索、按市场筛选与分页。
- `#/stocks/CN%3A600519`：真实OHLC K线、成交量、MA5/10/20/60、日/周/月周期、历史窗口；公司、盘口估值、财务三表、分红、股东、资金、公告新闻及研报目录。
- `#/sectors`：A 股行业目录、成分股、行业主力资金原始字段；公共源不可用时展示缺口。
- `#/research`、`#/documents`、`#/accounts`、`#/orders`、`#/settings`、`#/security`：策略实验、资料、账户、模拟订单、ENV 配置状态、会话管理和密码修改。

右侧显示自选与市场时钟；窄屏通过顶栏按钮打开。会话草稿在页面切换时保留在内存；刷新页面后可通过“最近研究”重新打开服务端已保存的研究。行业资金不等于北向资金，来源未提供的数据不会填零。

## Docker 启动

```bash
./scripts/docker-up.sh
```

脚本生成 Git 忽略的 MySQL 密钥，并启动 MySQL、一次性迁移任务、DeerFlow worker 与 Web。首次启动会从旧 `data/identity.sqlite3` 和 `data/financial_freedom.sqlite3` 只读导入并逐表核对；旧文件保留。旧库有一条缺少对应账户的外部持仓，迁移原样保留并记入[调研报告](docs/STORAGE_ENGINE_RESEARCH.md)。Web 仅在宿主机 `127.0.0.1:8000` 开放，MySQL 不映射宿主端口。

首次没有旧账号时，在终端创建唯一账号：

```sh
docker compose exec web python -m app.manage init-owner
```

然后打开 <http://127.0.0.1:8000>，用账号和密码登录。已有账号在迁移校验通过后继续使用原密码。默认无需验证器；需要短信登录保护时按 docs/SMS_SETUP.md 配置火山短信。未登录时，行情、账户、资料与API文档均不可访问。没有默认密码或公开注册。

首次批量行情抓取需要时间；上游不可访问时保留数据缺口。API文档在登录后访问 <http://127.0.0.1:8000/docs>。安全与恢复方式见 [docs/SECURITY.md](docs/SECURITY.md)。

可通过 `.env.example` 中列出的环境变量配置刷新频率、模型、数据请求并发数和日线失败重试间隔。Compose 管理 MySQL 凭据和数据卷；私密 `.env`、`.runtime/secrets/` 不进入镜像或 Git。每个模拟账户的初始资金在开户表单自行填写。

### 富途行情接入

这台 Mac 已安装富途官方 OpenD，私密 `.env` 中也已启用 `FUTU_ENABLED=true`。运行 `./run-local.sh` 或 `./scripts/docker-up.sh` 时，启动脚本会检查本机 OpenD：未监听时自动打开官方窗口，已有登录则直接复用。登录入口也在本平台「数据与模型」；点击“打开富途 OpenD 登录窗口”会切换到官方应用，由你在那里完成登录、问卷和协议。平台不接收富途密码或验证码。Docker 容器通过 `host.docker.internal` 连接 Mac 上的 OpenD；页面显示连接及行情状态。模拟交易始终在本地模拟账本执行。接口覆盖范围和回退规则见 [大盘行情来源与富途配置](docs/LIVE_INDEX_FEEDS.md)，更多官方接口的适用性与接入优先级见 [富途 OpenD API 能力盘点](docs/FUTU_API_SURVEY.md)。

备份数据库：`./scripts/docker-backup.sh`。备份保存在 `.runtime/backups/`，请与 `.env`、`.runtime/secrets/` 一起加密保管。`docker compose down` 不删除数据卷；不要使用 `down -v` 清除卷。

### 配置 AI Agent

在项目根目录的本地 `.env` 中配置模型，密钥放在单独的环境变量里。配置方式参考 `/Users/bytedance/work/dual_ai_voice_demo` 的 `MODEL_CONFIG_JSON` / `PRIMARY_MODEL`：

普通投研对话默认使用 DeerFlow 2.1。Docker 镜像安装仓库内固定源码快照，Compose 单独启动 worker。研究运行记录在 MySQL，DeerFlow 单次任务状态使用内存后端，不再创建 SQLite checkpoint；服务中断的单次推理需重新发起。模型由 `.env` 选择。`/api/v1/ai/status` 返回 `runtime` 和 `runtime_ready`；如需临时回退旧循环，设置 `AI_AGENT_RUNTIME=legacy` 并重启容器。未缓存的六位 A 股日线会在研究时尝试补齐最近一年已完成交易日数据，采集失败会显示数据缺口。模拟盘 AI 一轮交易仍走原受限执行器。

```dotenv
MODEL_CONFIG_JSON='[{"provider":"openai","model":"你的模型名称","base_url":"https://你的兼容服务/v1","api_key_env":"AI_MODEL_API_KEY"}]'
PRIMARY_MODEL=你的模型名称
AI_MODEL_API_KEY=你的服务端密钥
AI_AGENT_RUNTIME=deerflow
MODEL_TEMPERATURE=0.2
MODEL_TIMEOUT_SECONDS=45
AGENT_RUN_TIMEOUT_SECONDS=120
AGENT_MAX_TOOL_CALLS=16
```

Ollama 可用 OpenAI-compatible 接口配置：

```dotenv
MODEL_CONFIG_JSON='[{"provider":"ollama","model":"本地模型名称","base_url":"http://127.0.0.1:11434/v1"}]'
PRIMARY_MODEL=本地模型名称
```

在私密 `.env` 配置模型，修改后运行 `docker compose up -d --force-recreate web deerflow`。`/api/v1/ai/status` 会显示模型是否就绪，不会返回密钥。DeerFlow 投研使用 `PRIMARY_MODEL` 指定的首选模型；`AI_MODEL_FALLBACK_ENABLED` 仅适用于旧循环。模型端点需支持 OpenAI Chat Completions 工具调用。若模型运行在宿主机，请使用容器可访问的地址，例如 `host.docker.internal`，不要填容器自身的 `127.0.0.1`。

研报/财报可从页面导入可提取文本的 PDF、TXT、Markdown 或 CSV，原件存放在 MySQL，支持下载、按页/文本片段检索和删除；删除时会清理历史研究记录中的对应文档证据，扫描版 PDF 暂不做 OCR。个股财务摘要和基金持仓在 Agent 查询时调用 AKShare，受上游稳定性影响。北向实时买卖成交额已经停止公开披露，Agent 会说明数据缺口，不会拿空值当作零。宽范围扫描仅能覆盖本地已缓存行情，尚未配置付费新闻/研报源。

AI 使用要求本机有对应数据：个股历史指标需要已拉取日线；策略研究需要本地有足够日线；大盘扫描基于当前缓存快照。行情源可能不可用；模拟交易与回测要求本地有对应行情/日线数据。

## Specs 与调研

- [Spec Kitty 项目章程](.kittify/charter/charter.md)
- [初始版本完整 Spec](kitty-specs/001-quant-trading-foundation/spec.md)
- [AI 投研 Agent Spec](kitty-specs/002-ai-investment-research-agent/spec.md)
- [个股资料与身份安全 Spec](kitty-specs/004-stock-dossier-and-identity/spec.md)
- [个股数据源调研](docs/STOCK_DATA_SOURCES.md)
- [登录、安全与本地恢复](docs/SECURITY.md)
- [Agent 工作空间 Spec](kitty-specs/003-agent-workspace/spec.md)
- [技术实施计划](kitty-specs/001-quant-trading-foundation/plan.md)
- [数据模型](kitty-specs/001-quant-trading-foundation/data-model.md)
- [API 合约](kitty-specs/001-quant-trading-foundation/contracts/openapi.yaml)
- [工作包列表](kitty-specs/001-quant-trading-foundation/tasks.md)
- [产品与技术方案](PRODUCT.md)
- [开源平台与 AI 工具调研](OPEN_SOURCE_RESEARCH.md)
- [UI 设计规范](DESIGN.md)
- [交互约定](UX-CONTRACT.md)

## 边界

这是本地个人研究/模拟交易 MVP。Agent 会基于可核验数据给出当日买入、加仓、持有、减仓、卖出或观望建议，并说明数据时点、条件与风险；没有足够数据时建议暂不操作。建议不会自动触发实盘交易。公共行情库不提供实时 SLA，也不自动赋予展示/再分发许可。真实账户和券商接口接入前需单独确认可用权限、账户归属与数据许可。

## 多市场与 AI 模拟盘

1. 登录后进入“账户与模拟盘”（`#/accounts`），查看或创建对应市场账户，设置初始虚拟资金。
2. 港股在“模拟交易”页同步港交所证券清单；来源不可用时，可手工确认模拟单位（7天有效）。
3. 手动交易选择账户和股票，可点击“拉取该股报价”。市价单需开市且有近期源时点；缺行情/休市可限价挂单并冻结资金/持仓，后续刷新才撮合。
4. AI交易在账户页填写白名单（如`US:AAPL, US:MSFT`）、研究目标、委托名义金额及笔数，勾选授权并确认。它使用既有ENV主模型，无需额外AI交易密钥。
5. 记录区查看每轮证据、总结与真实订单；停止会阻止后续写入并撤销该轮挂单。模型失败或服务中断不会抹除已提交/成交记录；同一请求重试不自动重跑。

升级前已存在的模拟账户及其资金保留；新账户必须自行填写初始资金，不再自动补建固定资金盘。账户各自估值，不做无汇率来源的跨币种汇总。费用简化为10bp；不模拟真实盘口、滑点、部分成交、完整税费、公司行为及券商现金交收；无真实券商交易。大盘在此解释为主板，指数本身不能当股票买卖。

详细契约见 [005 Spec](kitty-specs/005-ai-paper-trading/spec.md)、[API](kitty-specs/005-ai-paper-trading/api.md)。

## 独立实验与清零重开（006）

模拟账户是炒股实验，区别于登录账户。可重复开户、自填初始资金，每盘独立资金、持仓、订单和AI记录。可在账户页“清零重开”或“全部模拟盘清零重开”：本人确认删除后，新盘使用全新ID和指定资金；旧AI任务停止，模拟订单/成交/AI记录删除。少量操作审计保留，实盘和身份不受影响。当前版本不再自动补建固定资金盘，升级前的已有盘保留，未执行任何主动清零。

模拟盘已有owner归属检查；当前登录模块仍是单拥有者，不是已可公开注册的多租户平台。旧盘只迁移给原拥有者，其他业务多用户隔离需要后续独立改造。

## 当前重点：模拟交易与投研

- `#/accounts`：创建多次独立模拟实验，自定市场和初始资金；单盘/全部清零重开。清零需本人确认，升级不执行任何清零。
- `#/orders`：手动模拟委托与受限AI单轮执行。支持美股、港股、A股主板、创业板和科创板，账本按账户隔离。
- 个股详情：K线、公司资料、财务三表、资金、公告与研报目录；增加“历史周期”标签和五年日线采集。
- `#/indices`：上证、深成、沪深300、中证500、创业板、科创50、恒生、标普500、道琼斯、纳斯达克。独立指数ID，不能直接下单。
- `#/flows`：沪深大盘资金历史、各类资金覆盖说明；每次最多5只基金的年度持仓披露采集，逐只缓存并报告缺口。
- `#/documents`：导入自己的研报/财报后点“AI分析”；Agent可以指定文档检索、逐页分段读取并引用页码。扫描件OCR、付费研报全文订阅尚未接入。

历史统计包括5/20/60/120/252根阶段收益、均线结构、波动、最大回撤、月度季节性和收益自相关。统计返回样本范围、样本量、方法版本和样本哈希；样本不足不填值，未完成本月不计入季节性。非复权/非含分红总回报，历史规律不能当作预测。

服务启动后每30分钟独立轮询指数日线及沪深大盘资金；自选报价与日线继续走已有采集任务。指数只收录当地日期早于今天的日线。AKShare是公共数据适配器，无实时或明日一定可用的承诺；失败保留上次数据并标过期/错误，时间始终显示。北向实时买卖额、基金实时操作流水、港美完整财报和机构研报全文不在当前完整覆盖内。

按用户2026-10-26最新决定，实盘暂缓。`app/live.py`、`app/brokers/`、`prototype/live.js`及[配置调研草案](docs/BROKER_SETUP.md)仅保留研究，不加载、不注册路由、不开放页面或模型工具；`#/live`回到账户页。无需申请券商API或提供股票账号密码。

最新范围见[007 Spec](kitty-specs/007-paper-research-workbench/spec.md)。

## 新闻、央行流动性与板块轮动

`#/news`按60秒轮询财经快讯，支持行业/关键词筛选、发布/首见时间与来源；`#/liquidity`查看央行公开市场公告，按期限列逆回购操作量与利率，到期额缺失时不推算净投放；`#/sectors`统一展示A股行业今日/5日/10日轮动、主力资金、采集日快照和行业目录，点击行业进入成分股与资金明细。旧 `#/rotation` 链接继续指向合并后的页面。

Agent研究顺序为“新闻/政策流动性→大盘→行业轮动→候选个股→模拟仓位/退出”。AI模拟下单前须先尝试查询新闻、央行流动性和轮动工具，再受原有账户/证券/额度授权限制。查询前置不是新闻真实性或盈利证明；缺数据需要如实说明并允许不下单。没有新增任何实盘或国债逆回购交易。

数据源为公共轮询，不能保证秒级实时；轮动今日/5/10日排名差不是跨日名次变化，历史快照从实际采集开始积累。源超时/排队时页面保留缺口，后台完成后存储，稍后刷新可见。见[008 Spec](kitty-specs/008-news-liquidity-sector-rotation/spec.md)。

## 009 登录简化与火山短信

按最新要求，默认账号密码登录；模拟交易等敏感操作仅重验当前账户密码。已有账号和密码不变，升级后刷新网页重新登录即可，不再绑定验证器。可选火山短信登录：配置后将AUTH_LOGIN_VERIFICATION改为sms，密码通过后再收短信。未配短信时默认password模式直接可用。

短信使用AK/SK、消息组、已审核签名与模板，不是方舟API Key；配置仅在本机ENV，example为空。见[配置说明](docs/SMS_SETUP.md)及[009 Spec](kitty-specs/009-password-login-and-volc-sms/spec.md)。邮箱验证未接入。

## 大盘指数快照

大盘与指数页每秒从本机快照更新点位、涨跌幅及开高低等字段。默认 AKShare 后台批量采集，不能保证交易所秒级行情。可配置 Longbridge OpenAPI 订阅推送；权限与配置见 [docs/LIVE_INDEX_FEEDS.md](docs/LIVE_INDEX_FEEDS.md)，实现范围见 [kitty-specs/010-live-index-feed/spec.md](kitty-specs/010-live-index-feed/spec.md)。
