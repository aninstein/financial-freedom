## Context

FastAPI + MySQL 工作台已具备本地模拟 Broker。`#/holdings` 是用户登记的真实持仓视图，既不是券商实时账户也不是模拟资金账户。本 change 开放 `#/paper`、`#/live`，新增富途交易适配器；`app/live.py` 中的 QMT/盈立草案仍未注册。代码与替身测试不能证明实际富途账户或实盘权限已通过联调。

## Goals / Non-Goals

**Goals:** 两个可直接访问、清楚区分资金性质的页面；模拟页同时支持独立的本地账本与富途 `SIMULATE` 账户；实盘页通过富途 `REAL` 读取和人工下单；服务端订单状态可核对且不会因超时盲目重复发送。

**Non-Goals:** 引入 vn.py/LEAN 作为站内主交易引擎；让 LLM 触达真实下单端点；保证模拟收益可复制；首期接入非富途券商或富途 A 股通；通过网页收集富途密码、交易解锁密码或私钥。

## Decisions

### 1. 导航、路由与数据域

主导航在“我的持仓”下方保留“实盘交易” `#/live`；“模拟炒股” `#/paper` 放在「更多工具 → 研究工具」。页面切换替换主区域内容。旧 `#/accounts` 跳转 `#/paper?tab=accounts`，旧 `#/orders` 和 `#/trading` 跳转 `#/paper?tab=orders`；旧 `#/live` 保留直接访问，停止跳转持仓。`#/holdings` 继续只显示用户登记的真实持仓，可提供进入两个交易页的链接，但不把三个数据域混成一张账户表。`#/paper` 下账户和订单为两个页内视图，不构成第三个一级交易页。

内置平台 MCP 对两个交易页面提供 owner 绑定的只读数据资源。本地模拟账户、委托和 AI 任务与富途 `SIMULATE`/`REAL` 账户、持仓、委托分开命名；富途目录仅提供账户尾号和不含完整 `acc_id` 的连接标识。AI 可按目录中的 `connection_id` 查询资金持仓，并按来源、时间及估值完整性分析；委托资源只覆盖本平台记录。MCP 不提供交易预览、提交、撤单或核对写入能力。

所有 API/页面对象都有 `mode: paper|live`；模拟对象另有 `source: local|futu`。本地 `paper_account_id`、富途模拟 `acc_id` 和富途真实 `acc_id` 各自命名空间、持久化与权限独立，且必须在服务端固定 `trd_env`，不能由前端随意改写。页面标题、资金标签、确认窗口和回执始终包含“本地模拟”“富途模拟”或“真实资金”文字。前端地址栏直接输入、刷新、后退、旧链接均需正确落页。

### 2. 页面布局参考

参考开源 [VeighNa Trader](https://www.vnpy.com/docs/cn/community/info/veighna_trader.html) 的交易输入与“活动委托/成交/委托/持仓”分区，以及 [FreqUI](https://github.com/freqtrade/freqtrade/blob/develop/docs/freq-ui.md) 的账户状态总览。参考的是信息层级和交互，不引入其前端源码或资产。两页沿用现有导航、色彩、排版、卡片和弹窗组件，股票名称/代码可用本站标的搜索。

桌面布局：顶部模式标识、账户/环境选择与连接时点；其下为可用资金/持仓/当日变化的摘要区；主区域左侧是标的报价与限价委托表单，右侧是账户与风险限额；下方用“活动委托 / 全部委托 / 成交或模拟回报 / 持仓”分段表。移动端按同一阅读顺序单列堆叠，确认窗口完整显示账户、方向、数量、价格及环境。任何红绿颜色都辅以文字和数值，订单状态及错误可用键盘与屏幕阅读器读取。实盘的“真实资金”提示和发送按钮在滚动后仍易识别。

### 3. 模拟页面：本地账本与富途 SIMULATE

本地模拟来源继续使用 `GET /api/v1/accounts`（筛选模拟账户）和现有 `/api/v1/paper/*` 账户、订单、表现与 AI 实验端点。保留独立虚拟现金、冻结金额、持仓和收益计算；原有 AI 单轮实验只用于本地模拟账本。

富途模拟来源由服务端通过 OpenD `get_acc_list` 发现 `trd_env=SIMULATE` 的股票模拟账户，并以稳定 `acc_id` 绑定。页面使用新增的 `/api/v1/futu-paper/*` 端点读取资金、持仓、可买卖、委托，提交/撤销模拟订单。服务端调用官方 `accinfo_query`、`position_list_query`、`acctradinginfo_query`、`place_order`、`order_list_query`、`modify_order`，每次显式传 `TrdEnv.SIMULATE` 和已绑定 `acc_id`。本地账本的重开/清零不能重置富途模拟账户；富途模拟账户是否可重置取决于官方客户端能力，本期页面不提供重置按钮。官方模拟环境不支持成交明细相关 API，故按订单状态/已成交数量展示“模拟回报”，不能伪造完整逐笔成交。

两种来源在页面中有固定标签和独立筛选，资金/收益不合计，订单 ID 不互用。本地来源持续说明报价快照全额撮合、简化 10bp 费用等假设；富途来源标明“富途官方模拟环境”，列出其不支持的成交明细与交易时段限制。两者均显示数据时间和收益缺口。此页不调用 `/live/*`。

### 4. 富途实盘连接状态与能力注册

券商目录不等于连接实例。`GET /api/v1/live/status` 对每条实例提供服务端计算的 `provider`、`market`、`account_suffix`（仅已核验后）、`read_state`、`order_state`、`last_verified_at`、`last_broker_response_at`、`capabilities`、`reason`、`max_order_notional`、`max_daily_notional` 和白名单摘要；不返回密钥、完整账号或网关地址。状态至少区分 `unconfigured`、`configured_unverified`、`read_ready`、`order_disabled`、`order_ready`、`degraded`、`unknown_order_blocked`。配置存在并不算连通。页面在未配置时显示官方权限/终端设置说明；只有连接身份、实际账户、只读查询、适配器能力和发送开关都通过时才显示可提交入口。

首期唯一交易提供方为富途 OpenD 官方 SDK。现有 `app/futu_feed.py`/OpenD 启动器只证明行情连接；新交易连接必须另建 `OpenSecTradeContext`、取得 `get_acc_list`、校验 `security_firm`、`trdmarket_auth`、`trd_env=REAL`、稳定 `acc_id` 与账户状态。优先验收港股与美股普通股票现金限价单；`TrdMarket.CN` 只可模拟，`HKCC` 为另一个需单独验收的 A 股通市场，不得在 `CN` 实盘发送。QMT/盈立适配草案本次不注册或开放；不要在富途连接目录中宣称其能力。

### 5. 富途 API 与服务端适配边界

服务端定义富途交易适配器：`get_acc_list → accinfo_query / position_list_query → acctradinginfo_query → place_order → order_list_query / history_order_list_query → modify_order(CANCEL)`，并接收订单/成交推送；断线重连后重新查询核对。所有请求绑定服务端选择的 `security_firm`、市场、`trd_env`、非零 `acc_id`，不能使用默认 `acc_id=0` 或 `acc_index`；这些字段从页面传入时只作一致性校验，绝不决定目标账户。`remark` 可存短客户端标识辅助核对，但不能假定富途提供全局幂等。适配器返回统一币种、精度、券商时间、账户尾号、订单 ID/状态、成交数量与价格；原始回报保留在受控审计层。缺少稳定账户识别、可核验订单标识或异常恢复能力的连接只能只读。

富途交易上下文复用本机 OpenD 进程，但与现有行情上下文分离。`REAL` 下单前须由用户在官方 OpenD GUI 完成交易解锁；所查官方文档未提供独立只读解锁状态查询，页面显示“请在 OpenD 确认解锁”，不得展示“已验证解锁”或在未解锁时承诺可成功发送。富途明确返回“未解锁”时标记连接不可发送并提示用户回官方终端处理，之后重新核对账户；网页与 Agent 不收集解锁密码。`SIMULATE` 不要求交易解锁。OpenD 断线、会话切换或账户变更立即撤销 `order_ready`，不能自动切到另一 `acc_id` 或环境。

建议 API：

| 方法与路径 | 用途 |
| --- | --- |
| `GET /api/v1/live/status` | 列出本用户可见连接和可用能力，无主动券商写入 |
| `GET /api/v1/live/accounts/{connection_id}` | 本人触发真实账户/现金/持仓快照读取，附数据时间及过期状态 |
| `POST /api/v1/live/orders/preview` | 服务端风控，创建短期、一次性、绑定订单草案与连接的预览 |
| `POST /api/v1/live/orders` | 近期身份重验与本人逐笔确认后，以幂等键提交预览 |
| `GET /api/v1/live/orders` | 本平台真实订单列表，可按连接筛选；明确不是券商全部历史 |
| `POST /api/v1/live/connections/{id}/reconcile` | 主动读取券商订单/成交，核对未知或进行中状态 |
| `POST /api/v1/live/orders/{id}/cancel` | 对本平台且券商可核验的订单请求撤单，并再次查询结果 |

富途模拟对应的 `/api/v1/futu-paper/status`、`/accounts/{id}`、`/orders/preview`、`/orders`、`/orders/{id}/cancel` 返回 `source=futu`、`trd_env=SIMULATE`；本地模拟继续 `/api/v1/paper/*`。两套模拟 API 不共用下单 ID、清零接口或业绩口径。

API 与现有认证、CSRF、最近五分钟密码重验及 owner 归属一致；写操作需明确审计。正式启动时以当前 MySQL 方言和迁移机制重建/审计实盘表与事务，不能把原 `app/live.py` 中未联调的 SQL 原样注册。身份重验以服务端有效期校验，不能只靠 `ensureRecentIdentity()` 前端调用。旧接口与状态字段可兼容，但不得削弱下列行为契约。

### 6. 实盘预览、确认和确定性风控

首期只允许已验证的港股/美股现金账户常规交易时段限价买卖，`adjust_limit=0`，不使用自动调价、盘前盘后或融资额度。预览绑定 owner、富途 `REAL` 环境、`security_firm`、稳定 `acc_id`、市场、标的、方向、数量、限价、配置版本及报价/账户快照时间；45 秒内有效，修改任何字段须重做。预览显示真实资金、账户尾号、市场/币种、名义金额、`max_cash_buy` 或 `max_position_sell`、单笔及当日额度、数据时点与券商状态。券商不可用、账户不唯一、报价/快照失效、交易日历未知、白名单外、数量/价格精度错误、可用现金/可卖不足、超限或结果未知时拒绝。

提交前重新读取券商账户/可买可卖并运行同一套确定性风控；以服务端配置的市场、交易时段、整手、价格边界和账户级限制为准。前端确认窗口需要准确列出实盘连接与订单参数，用户主动点击“确认发送真实订单”；取消、关闭或 Escape 不发送。提交可能立即成交，页面只把券商接收标为“已提交”，不能标“已成交”。任何模型输出只可生成研究或可编辑草案，不得调用实盘预览后自动确认、提交或撤单。

### 7. 实盘状态机、重试与隔离

订单以 `(owner_id, idempotency_key)` 去重，预览最多消费一次；服务端先持久化请求和唯一客户端标识并写入富途 `remark`，再调用 `place_order`。状态包含 `validating → dispatching → submitted → partially_filled|filled|canceled|rejected`，发送响应丢失或重启中断进入 `unknown`，撤单进入 `cancel_requested|cancel_unknown`。推送可能先于下单响应，状态合并必须单调保留已成交数量。相同幂等键重试返回同一订单，不自动再发送。结果未知时阻止该账户新的提交，按富途订单编号、`remark`、账户、标的、数量和时间查询；若不足以唯一确认，维持人工处理标记，绝不凭找不到订单就自动重发。

撤单请求调用 `modify_order(CANCEL)`，不等于撤单成功；部分成交数量、剩余数量和费用以券商回报为准。关闭新单开关后仍允许只读核对和风险降低性质的撤单。模拟清零不触及富途真实账户或订单。OpenD 仅监听回环或受控隧道，登录与解锁留在官方终端，日志中脱敏。

### 8. 分阶段开放与回滚

先交付两个页面与本地模拟和只读富途交易状态。依次完成富途 `SIMULATE` 账户发现、资金/持仓/订单、模拟下单/撤单与断线测试；再对 `REAL` 账户进行官方权限/市场核实、只读一致性、订单/部分成交/撤单/断线测试，最后由本人显式配置发送开关。未满足时 `order_state=order_disabled`，服务器返回 403。上线后用全局和逐账户开关暂停新订单；状态查询、撤单和审计继续可用。回滚导航或页面不删除本地账本、富途委托或审计数据。

## Risks / Trade-offs

- 公共行情与券商行情可能延迟/不一致：真实下单以券商账户和可交易数量为准，页面注明时点；不把研究报价视为成交价。
- 券商 API 可能先推送后返回、断线或只给部分订单信息：持久 ID、状态核对、未知状态封锁和手动处理路径优先。
- 模拟撮合容易高估成交质量：在页面固定披露假设，不把模拟业绩映射到实盘收益。
- 富途不同主体、账户、币种、市场规则各异：以实际 `acc_id`、`security_firm`、`trd_env`、市场授权与已核验账户开放，拒绝推断通用能力。

## Open Questions

- 富途当前 OpenD 登录后实际返回哪些 `SIMULATE`/`REAL` 账户及港美市场权限？本 change 不依赖回答即可完成页面和禁用态，真实发送必须以返回账户和联调结果为准。
