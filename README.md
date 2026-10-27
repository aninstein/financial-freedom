# Financial Freedom

本项目采用 [PolyForm Noncommercial 1.0.0](LICENSE)：允许非商业使用、学习和研究；商业使用未获授权。因禁止商业使用，本项目属于**源码可见**，并非 OSI 定义的开源软件。第三方依赖保留各自许可证。公开发布前请先看[发布核对](docs/PUBLICATION.md)。

本地优先的量化工作台：市场状态、行情数据、观察列表、手工账户快照、模拟交易、确定性历史研究和 AI 投研/模拟交易 Agent。本地模拟盘与富途模拟盘独立；富途实盘页面默认关闭真实订单发送。

## 当前能力

- FastAPI 本地服务，默认只绑定 `127.0.0.1:8000`。
- AKShare 行情适配器：A 股/创业板、港股、美股、ETF、开放式基金公布净值、上海黄金交易所 Au99.99。A 股东方财富失败后依次尝试腾讯和新浪接口；港股全市场端点失败或超时时，观察列表内的港股代码改用新浪单票报价，保留源时间并按年龄标记新鲜度。美股全市场现价端点在当前环境失败，新浪全市场需要抓取 917 页，本地未启用；对观察列表内的美股，改用新浪同源的单票延迟报价（公开接口标注 15 分钟延迟），无法获取时才回退到日线收盘价。日线数据只用于查看，不能用于模拟成交。
- 交易所日历状态：XNYS、XSHG、XHKG；上海黄金按交易所常规时段及 XSHG 假日表推算，节假日临时安排以 SGE 公告为准。
- MySQL/InnoDB 持久化行情快照、日线历史、观察列表、身份、研究记录和模拟账本；Docker Compose 管理数据库与 Web。
- 手工录入的账户快照与模拟账户分开展示；按币种保存，不做无 FX 来源的汇总换算。
- 五类独立模拟盘：美股、港股、A股主板、创业板、科创板。可自行开户/设置初始虚拟资金、查看现金/冻结/可卖持仓/盈亏。原有账户与订单保留；新增三类A股默认盘，分别100万元虚拟资金。港股同步HKEX官方每手股数，也可明确录入手工模拟规则。主板/创业板100股整数买入，科创板至少200股整数递增，A股T+1可卖。
- 支持 AKShare 日线手动拉取和观察列表自动回补/增量采集，带内容哈希的数据集版本，以及 SMA 趋势基线回测；回测包含买入持有对照、手续费/滑点假设、最大回撤、年化波动和夏普比率，使用非复权数据并明确标记为历史研究。
- 富途 OpenD 交易通过独立的模拟与实盘页面接入；实盘订单须单独配置账户、证券、限额和双重开关。
- AI Agent 可用服务端 `.env` 配置 OpenAI-compatible 或 Ollama 模型；可读取行情/日线、筛选基金、查询基金定期报告披露的持仓和重大买入/卖出变动、读取 A 股财务摘要、运行 SMA 历史回测，并检索用户上传的文本 PDF/TXT/Markdown/CSV。基金操作数据是历史披露，不是实时交易流水。所有研究保留运行记录和来源证据；普通聊天继续只读；“账户与模拟盘”可明确授权AI在固定账户、股票白名单、金额和笔数限额内执行一轮模拟买卖，保留模型、原因、来源和实际订单。
- 投研对话由服务端保存，并按用户生成 `llm-wiki`：当天共享摘要、每日归档、短期事项和带来源的长期偏好。聊天页「投资记忆」可浏览和编辑 Markdown；头像菜单「记忆保留期限」管理原始会话 1–30 天、归档记忆 1–365 天的留存。

## Agent 工作空间

首页是投研对话，左侧菜单进入独立数据页面。聊天中的股票标识和证据卡片可打开个股详情；板块卡片打开成分股与行业资金页。个股/板块页面的“询问 Agent”会把上下文放入草稿，由用户发送。

- `#/chat`：连续对话、最近研究、来源证据与账户上下文选择。
- `#/watchlist`：个人关注标的、行情、均线和波动指标。
- `#/markets`：跨市场搜索、按市场筛选与分页。
- `#/stocks/CN%3A600519`：真实OHLC K线、成交量、MA5/10/20/60、日/周/月周期、历史窗口；公司、盘口估值、财务三表、分红、股东、资金、公告新闻及研报目录。
- `#/sectors`：A 股行业目录、成分股、行业主力资金原始字段；公共源不可用时展示缺口。
- `#/research`、`#/documents`、`#/accounts`、`#/orders`、`#/settings`、`#/security`：策略实验、资料、账户、模拟订单、ENV 配置状态、会话管理和密码修改。

右侧显示自选与市场时钟；窄屏通过顶栏按钮打开。会话草稿在页面切换时保留在内存；刷新页面后可从服务端会话列表继续保留期内的对话。行业资金不等于北向资金，来源未提供的数据不会填零。

## Docker 启动

```bash
./scripts/docker-up.sh
```

脚本生成 Git 忽略的 MySQL 密钥，并启动 MySQL、一次性迁移任务、DeerFlow worker 与 Web。首次启动会从旧 `data/identity.sqlite3` 和 `data/financial_freedom.sqlite3` 只读导入并逐表核对；旧文件保留。Web 仅在宿主机 `127.0.0.1:8000` 开放，MySQL 不映射宿主端口。

首次没有旧账号时，在终端创建唯一账号：

```sh
docker compose exec web python -m app.manage init-owner
```

然后打开 <http://127.0.0.1:8000>，用账号和密码登录。已有账号在迁移校验通过后继续使用原密码。默认采用密码登录。未登录时，行情、账户、资料与API文档均不可访问。没有默认密码或公开注册。

微信小程序入口位于 [financial-freedom-applet](https://github.com/aninstein/financial-freedom-applet)。部署 HTTPS 后，可在服务端配置 `WECHAT_MINIPROGRAM_APPID` 与 `WECHAT_MINIPROGRAM_SECRET`：小程序通过 `wx.login` 取得一次性 code，服务端向微信换取 OpenID。首次登录需用现有账号密码绑定；密码变更后需重新绑定。已绑定用户以 60 秒、单次使用的网页登录票据建立原有 HttpOnly Cookie 会话。AppSecret、OpenID 和会话密钥不会下发到小程序。

首次批量行情抓取需要时间；上游不可访问时保留数据缺口。API文档在登录后访问 <http://127.0.0.1:8000/docs>。安全与恢复方式见 [docs/SECURITY.md](docs/SECURITY.md)。

可通过 `.env.example` 中列出的环境变量配置刷新频率、模型、数据请求并发数和日线失败重试间隔。Compose 管理 MySQL 凭据和数据卷；私密 `.env`、`.runtime/secrets/` 不进入镜像或 Git。每个模拟账户的初始资金在开户表单自行填写。

### 行情数据源接入

如已安装富途官方 OpenD，可在私密 `.env` 中启用 `FUTU_ENABLED=true` 获取行情，另以 `FUTU_TRADE_ENABLED=true` 发现交易账户。运行 `./run-local.sh` 或 `./scripts/docker-up.sh` 时，启动脚本会检查本机 OpenD；登录、问卷、协议和交易解锁都在官方窗口完成。平台不接收富途密码或验证码。Docker 容器通过 `host.docker.internal` 连接 Mac 上的 OpenD。`#/paper` 为本地模拟，`#/paper?source=futu` 为富途模拟，`#/live` 为真实账户，三者账本独立。交易开关与配置见 [券商接入](docs/BROKER_SETUP.md)；行情覆盖和回退见 [大盘行情来源与富途配置](docs/LIVE_INDEX_FEEDS.md)。

备份数据库与投资 wiki：`./scripts/docker-backup.sh`。备份保存在 `.runtime/backups/`，请与 `.env`、`.runtime/secrets/` 一起加密保管。`docker compose down` 不删除数据卷；不要使用 `down -v` 清除卷。记忆目录与恢复步骤见 [投研记忆说明](docs/INVESTMENT_MEMORY.md)。

### 配置 AI Agent

在项目根目录的本地 `.env` 中配置模型，密钥放在单独的环境变量里。使用 `MODEL_CONFIG_JSON` / `PRIMARY_MODEL`：

普通投研对话默认使用固定版本的公开源码 [DeerFlow](https://github.com/bytedance/deer-flow) worker，通过受限工具桥接本项目的行情和研究能力。研究运行记录在 MySQL；模型由 `.env` 选择。`/api/v1/ai/status` 返回运行时与连接状态。模拟盘 AI 仍走独立的受限执行器。

```dotenv
MODEL_CONFIG_JSON='[{"provider":"openai","model":"你的模型名称","base_url":"https://你的兼容服务/v1","api_key_env":"AI_MODEL_API_KEY"}]'
AI_AGENT_RUNTIME=deerflow
PRIMARY_MODEL=你的模型名称
AI_MODEL_API_KEY=你的服务端密钥
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

在私密 `.env` 配置模型，修改后运行 `docker compose up -d --force-recreate web deerflow`。`/api/v1/ai/status` 会显示模型是否就绪，不会返回密钥。DeerFlow 投研使用 `PRIMARY_MODEL` 指定的首选模型；`AI_MODEL_FALLBACK_ENABLED` 仅适用于内置循环。模型端点需支持 OpenAI Chat Completions 工具调用。若模型运行在宿主机，请使用容器可访问的地址，例如 `host.docker.internal`，不要填容器自身的 `127.0.0.1`。

聊天框支持直接粘贴剪贴板图片（`⌘V` / `Ctrl+V`）；粘贴后立即交给支持视觉的模型预解析，无需先写提示词。支持 PNG、JPEG、GIF、WebP，单张上限 5 MB。原图、文件名、大小、尺寸、SHA-256 和解析文本按当前账号与会话保存在 MySQL，后续可在同一会话追问或导入持仓；删除会话或原始会话到期时清理。截图中未显示代码的持仓会保留在核对草稿，补齐代码后才能保存。官方 DeepSeek 端点的 `deepseek-flash` 自动开启视觉能力；其他模型请在对应的 `MODEL_CONFIG_JSON` 项显式设置 `"supports_vision":true`，并确认服务端模型确实接受 OpenAI 兼容的图片输入。未开启视觉能力时界面不显示图片预览，粘贴图片会提示当前模型不支持。修改配置后重启 `web` 和 `deerflow`。

研报/财报可从页面导入可提取文本的 PDF、TXT、Markdown 或 CSV，原件存放在 MySQL，支持下载、按页/文本片段检索和删除；删除时会清理历史研究记录中的对应文档证据，扫描版 PDF 暂不做 OCR。个股财务摘要和基金持仓在 Agent 查询时调用 AKShare，受上游稳定性影响。北向实时买卖成交额已经停止公开披露，Agent 会说明数据缺口，不会拿空值当作零。宽范围扫描仅能覆盖本地已缓存行情，尚未配置付费新闻/研报源。

AI 使用要求本机有对应数据：个股历史指标需要已拉取日线；策略研究需要本地有足够日线；大盘扫描基于当前缓存快照。行情源可能不可用；模拟交易与回测要求本地有对应行情/日线数据。

Skills 和 MCP 在「数据与模型」配置；也可在聊天中发送安装公开 GitHub Skill 或 `mcpServers` JSON 的明确请求。ZIP 在该设置页上传。配置、权限与支持范围见 [Agent 扩展接入说明](docs/AGENT_EXTENSIONS.md)。

## Specs 与调研

- [Spec Kitty 项目章程](.kittify/charter/charter.md)
- [初始版本完整 Spec](kitty-specs/001-quant-trading-foundation/spec.md)
- [AI 投研 Agent Spec](kitty-specs/002-ai-investment-research-agent/spec.md)
- [投资记忆 OpenSpec](openspec/changes/add-investment-llm-wiki-memory/specs/investment-memory-wiki/spec.md)
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

这是本地个人研究与交易工作台。Agent 会基于可核验数据给出买入、加仓、持有、减仓、卖出或观望建议，并说明数据时点、条件与风险；没有足够数据时建议暂不操作。建议不会自动触发实盘交易。公共行情库不提供实时 SLA，也不自动赋予展示/再分发许可。富途真实账户能力取决于本人权限、OpenD 状态和交易解锁。

## 多市场与 AI 模拟盘

1. 登录后进入“账户与模拟盘”（`#/accounts`），查看或创建对应市场账户，设置初始虚拟资金。
2. 港股在“模拟交易”页同步港交所证券清单；来源不可用时，可手工确认模拟单位（7天有效）。
3. 手动交易选择账户和股票，可点击“拉取该股报价”。市价单需开市且有近期源时点；缺行情/休市可限价挂单并冻结资金/持仓，后续刷新才撮合。
4. AI交易在账户页填写白名单（如`US:AAPL, US:MSFT`）、研究目标、委托名义金额及笔数，勾选授权并确认。它使用既有ENV主模型，无需额外AI交易密钥。
5. 记录区查看每轮证据、总结与真实订单；停止会阻止后续写入并撤销该轮挂单。模型失败或服务中断不会抹除已提交/成交记录；同一请求重试不自动重跑。

升级前已存在的本地模拟账户及其资金保留；新账户必须自行填写初始资金，不再自动补建固定资金盘。账户各自估值，不做无汇率来源的跨币种汇总。本地模拟费用简化为10bp；不模拟真实盘口、滑点、部分成交、完整税费、公司行为及券商现金交收。富途模拟盘使用券商模拟环境，不套用本地撮合假设。大盘在此解释为主板，指数本身不能当股票买卖。

详细契约见 [005 Spec](kitty-specs/005-ai-paper-trading/spec.md)、[API](kitty-specs/005-ai-paper-trading/api.md)。

## 独立实验与清零重开（006）

模拟账户是炒股实验，区别于登录账户。可重复开户、自填初始资金，每盘独立资金、持仓、订单和AI记录。可在账户页“清零重开”或“全部模拟盘清零重开”：本人确认删除后，新盘使用全新ID和指定资金；旧AI任务停止，模拟订单/成交/AI记录删除。少量操作审计保留，实盘和身份不受影响。当前版本不再自动补建固定资金盘，升级前的已有盘保留，未执行任何主动清零。

模拟盘已有owner归属检查；当前登录模块仍是单拥有者，不是已可公开注册的多租户平台。旧盘只迁移给原拥有者，其他业务多用户隔离需要后续独立改造。

## 当前重点：模拟交易与投研

“我的持仓”先按 CNY/HKD/USD 选择币种，再按股票、基金、黄金查看和录入；黄金 ETF/联接基金可用基金代码归入黄金，份额按“份”显示。这里支持手工登记真实持仓，也可上传券商持仓截图生成待核对的识别草稿；保存后按最新可用行情计算参考市值与收益率，并单独显示截图记录的收益率供校准。视觉识别需要在“数据与模型”配置支持图片的模型。在“交易日历”订阅“持仓截图同步”后，每天北京时间 22:00 出现需要确认的网页闹钟；如果当时未登录，下一次登录会补显示。日历订阅及闹钟确认状态保存在当前浏览器，不会向系统或手机发送推送。

- `#/accounts`：创建多次独立模拟实验，自定市场和初始资金；单盘/全部清零重开。清零需本人确认，升级不执行任何清零。
- `#/orders`：手动模拟委托与受限AI单轮执行。支持美股、港股、A股主板、创业板和科创板，账本按账户隔离。
- 个股详情：K线、公司资料、财务三表、资金、公告与研报目录；增加“历史周期”标签和五年日线采集。
- `#/indices`：上证、深成、沪深300、中证500、创业板、科创50、恒生、标普500、道琼斯、纳斯达克。独立指数ID，不能直接下单。
- `#/flows`：沪深大盘资金历史、各类资金覆盖说明；每次最多5只基金的年度持仓披露采集，逐只缓存并报告缺口。
- `#/documents`：导入自己的研报/财报后点“AI分析”；Agent可以指定文档检索、逐页分段读取并引用页码。扫描件OCR、付费研报全文订阅尚未接入。

历史统计包括5/20/60/120/252根阶段收益、均线结构、波动、最大回撤、月度季节性和收益自相关。统计返回样本范围、样本量、方法版本和样本哈希；样本不足不填值，未完成本月不计入季节性。非复权/非含分红总回报，历史规律不能当作预测。

服务启动后每30分钟独立轮询指数日线及沪深大盘资金；自选报价与日线继续走已有采集任务。指数只收录当地日期早于今天的日线。AKShare是公共数据适配器，无实时或明日一定可用的承诺；失败保留上次数据并标过期/错误，时间始终显示。北向实时买卖额、基金实时操作流水、港美完整财报和机构研报全文不在当前完整覆盖内。

富途实盘页面已开放，只读账户发现和资产查询可在启用富途交易连接后使用。真实委托默认关闭，须本人在 OpenD 完成登录及交易解锁，并在私密配置中启用账户与证券白名单、限额和双重发送开关。`app/live.py`、`app/brokers/` 中的 QMT/盈立适配器仍未注册；AI 仍无实盘下单工具。详见[券商接入](docs/BROKER_SETUP.md)。

最新范围见[007 Spec](kitty-specs/007-paper-research-workbench/spec.md)。

## 新闻、央行流动性与板块轮动

`#/news`按60秒轮询财经快讯，支持行业/关键词筛选、发布/首见时间与来源；`#/liquidity`查看央行公开市场公告，按期限列逆回购操作量与利率，到期额缺失时不推算净投放；`#/sectors`统一展示A股行业今日/5日/10日轮动、主力资金、采集日快照和行业目录，点击行业进入成分股与资金明细。旧 `#/rotation` 链接继续指向合并后的页面。

Agent研究顺序为“新闻/政策流动性→大盘→行业轮动→候选个股→模拟仓位/退出”。AI模拟下单前须先尝试查询新闻、央行流动性和轮动工具，再受原有账户/证券/额度授权限制。查询前置不是新闻真实性或盈利证明；缺数据需要如实说明并允许不下单。富途实盘委托仅由本人在独立页面逐笔确认，AI 没有实盘或国债逆回购交易工具。

数据源为公共轮询，不能保证秒级实时；轮动今日/5/10日排名差不是跨日名次变化，历史快照从实际采集开始积累。源超时/排队时页面保留缺口，后台完成后存储，稍后刷新可见。见[008 Spec](kitty-specs/008-news-liquidity-sector-rotation/spec.md)。

## 账号登录

默认账号密码登录；模拟交易等敏感操作仅重验当前账户密码。没有公开注册和默认密码。

## 大盘指数快照

大盘与指数页每秒从本机快照更新点位、涨跌幅及开高低等字段。默认 AKShare 后台批量采集，不能保证交易所秒级行情。可配置 Longbridge OpenAPI 订阅推送；权限与配置见 [数据源接入说明](docs/DATA_SOURCE_SETUP.md)，实现范围见 [kitty-specs/010-live-index-feed/spec.md](kitty-specs/010-live-index-feed/spec.md)。
