# 富途 OpenD API 能力盘点（2026-10-26）

## 结论

富途 [OpenD 安装页](https://openapi.futunn.com/futu-api-doc/quick/opend-base.html) 只是入口；真正的功能清单在 [行情接口总览](https://openapi.futunn.com/futu-api-doc/quote/overview.html) 和 [交易接口总览](https://openapi.futunn.com/futu-api-doc/trade/overview.html)。当前产品仍以**只读投研 + 自有多账户模拟盘**为边界。OpenD 可成为 A/港/美市场的首选行情和研究数据源，但不能把目录里的每个接口都当作本机已授权、已接入或适用于该产品。

当前项目的富途适配器只实现 `subscribe(SubType.QUOTE)`、`StockQuoteHandlerBase`、`get_market_snapshot`、`request_history_kline`。覆盖六个 A 股指数、恒生指数以及自选/模拟盘持仓和挂单中的股票与交易所 ETF；`app/providers/futu_provider.py` 和 `app/futu_feed.py` 是现有归属。历史日线失败时仍可回退公共源。页面每秒读取本机快照，上游快照采样默认为 3 秒；不等于交易所逐秒更新。

本机 `futu-api 10.11.7108` 与已登录 OpenD 的**只读、每类一次**抽样：`get_global_state`、`get_search_news('逆回购', 1)`、`get_financials_statements('SH.600519', num=1)`、`get_capital_flow('SH.600519')`、`get_plate_list(Market.SH, Plate.INDUSTRY)`、`get_heat_map_data(Market.SH, count=1)`、`get_rise_fall_distribution(Market.SH)`、`get_ark_fund_holding(count=1)`、`get_research_morningstar_report('HK.00700')` 均返回 `RET_OK`。这证明这些参数组合在当前账号/时点可读，**不证明**所有证券、市场、历史范围或任何实时权限可用。探测仅输出成功状态和字段形状，未保存账号或报告正文。

## 接入矩阵

| 优先级 | 富途接口组 | 产品落点 | 当前状态与边界 |
| --- | --- | --- | --- |
| 已接入 | `subscribe(QUOTE)`、报价回调、`get_market_snapshot` | 自选、持仓估值、大盘快照 | 已接入；推送是否持续送达、各市场延迟仍需在交易时段观察。 |
| 已接入 | `request_history_kline` | 日 K、回测、历史周期 | 已接入未复权日线；每 7 天按不同标的计入历史 K 配额，不能无界批量拉取。 |
| P0 | `get_global_state`、`get_market_state`、`request_trading_days` | 交易时钟、模拟撮合的交易时段 | `get_global_state` 实测可读；交易日与品种状态尚未接入。应替代自行推断的开休市状态，并保留交易所时区。 |
| P0 | `get_search_quote`、`get_stock_basicinfo` | 全局证券搜索和标的主数据 | 尚未接入；可补足股票名称、证券类型与市场代码映射，避免把同名 ETF/指数当作股票。 |
| P0 | `get_plate_list`、`get_plate_stock`、`get_owner_plate`、`get_heat_map_data`、`get_rise_fall_distribution` | A/港/美板块目录、轮动、市场广度 | A 股板块列表、热力图、涨跌分布实测可读。热力图是单次横截面；5/10 日轮动须持久化每日快照后计算。 |
| P0 | `get_financials_statements`、`get_financials_revenue_breakdown`、`get_valuation_detail` | 个股财报、主营与估值 | A 股利润表抽样实测可读。接入时需保存报告期、币种、会计准则、字段 ID/单位；三表同报告期交叉核对。 |
| P0 | `get_search_news`、`get_earnings_calendar`、`get_economic_calendar` | 新闻/公告检索、财报日历与事件研究 | “逆回购”关键词抽样返回资讯索引。接口返回标题、来源、发布时间和链接；不是全文或央行官方公告，AI 不能仅凭标题写成事实。 |
| P0 | `get_capital_flow`、`get_capital_distribution` | 个股资金流 | A 股个股资金流实测可读。它是个股成交分类统计，不能当作北向资金、基金申赎或整个板块真实净流入。 |
| P1 | `get_stock_screen`、`get_stock_filter`、`get_top_movers_rank`、`get_period_change_rank` | 大范围候选股筛选与 Agent 推荐 | SDK 有 `get_stock_screen`，官方 V2 支持 11 类 244+ 因子；本机未跑筛选请求。应服务端限频、缓存，并把筛选条件与结果时间列为证据。 |
| P1 | `get_rehab`、`get_indicator_list`、`request_indicator_calc_async` | 复权研究、技术指标与策略实验 | 尚未接入。回测须记录前复权/后复权/未复权与实际可得时点；技术指标可以本地计算为主，富途结果用于核验。 |
| P1 | `get_rt_data`、`get_cur_kline`、`get_order_book`、`get_rt_ticker` 与对应推送 | 分时、盘口、盘中策略研究 | 尚未接入；通常先订阅并消耗额度，受 LV 等级限制。需要时按当前打开的详情页短时订阅，退出释放，不全市场常驻。 |
| P1 | `get_research_analyst_consensus`、`get_research_rating_summary`、`get_research_morningstar_report` | 研报观点和估值对照 | 晨星 HK.00700 抽样实测可读，含分析文本和 PDF 链接。保留作者/更新时间/观点与事实区分；按需读取，不批量镜像报告。 |
| P1 | `get_shareholders_*`、`get_institution_*`、`get_ark_*`、`get_insider_*` | 机构与基金操作追踪 | ARK 持仓抽样实测可读。机构变动官方接口限定港/美市场，含披露日期和来源；是已披露持仓变化，不是实时交易流水，也不覆盖全部 A 股基金。 |
| P1 | `get_macro_indicator_*`、`get_fed_watch_*`、`get_heat_map_data`、产业链接口 | 宏观与自上而下板块研究 | 文档可用、尚未本机抽样。逆回购公告与净投放仍需央行原始公告/到期数据，不能由新闻搜索或 FedWatch 推导。 |
| P1 | `get_corporate_actions_*`、`get_ipo_list`、`get_dividend_calendar` | 分红、拆股、IPO 与模拟盘公司行为 | 尚未接入。接入后先用于提醒与研究；若要影响模拟盘持仓，需明确账本重算规则。 |
| P1 | `get_user_security_group`、`get_user_security`、`get_price_reminder` | 导入富途自选及提醒 | 尚未接入。只做显式导入，不自动覆盖平台自选；富途自选属于个人数据，走现有登录保护。 |
| P2 | `get_option_*`、窝轮、期货、加密货币、预测市场 | 衍生品扩展 | 当前产品主要模拟股票/ETF；这些接口涉及不同合约、保证金、权限和报价卡，暂不纳入股票模拟撮合。COMEX 黄金期货还需要期货账户与相应行情卡；黄金 ETF 可沿用证券行情。 |
| 暂缓 | `OpenSecTradeContext` 的账户、资金、持仓、订单、成交与富途模拟交易接口 | 券商账户或富途模拟盘 | 用户已决定先不接实盘。富途模拟账户也不能取代产品内可重复创建、初始资金自定、账户隔离的模拟账本。当前代码不建立交易上下文。 |

## 额度、市场和数据语义

- [权限与额度](https://openapi.futunn.com/futu-api-doc/intro/authority.html)明确：OpenD 登录不等于每个行情权限。API 权限与富途 App 权限不完全相同；境内认证客户目前 A 股 LV1、港股 LV2，具体以当前账号和 OpenD 显示为准。美股指数 API 在该表中列为不支持，因此标普/道指/纳斯达克指数继续用独立来源。
- 最低档（总资产低于 1 万港元或未开户）默认同时订阅 100 项、7 天内历史 K 线 100 个不同标的；一只证券每订阅一个数据类型占一个额度。快照示例限频 60 次/30 秒，条件选股 10 次/30 秒，板块列表 10 次/30 秒。接口各有限频，须按接口单独调度，不能把页面每秒刷新转换成每秒对富途全量请求。
- `get_capital_flow` [仅支持个股/基金等](https://openapi.futunn.com/futu-api-doc/quote/get-capital-flow.html)，历史周期近一年、盘中实时近一天；它不能回答“北向资金净买入”。`get_institution_holding_change` [支持港/美机构披露](https://openapi.futunn.com/futu-api-doc/quote/get-institution-holding-change.html)，不能宣称“实时基金操作”。
- [资讯搜索](https://openapi.futunn.com/futu-api-doc/quote/get-search-news.html)只给元数据与详情链接。[财务报表](https://openapi.futunn.com/futu-api-doc/quote/get-financials-statements.html)给结构化字段。[晨星研报](https://openapi.futunn.com/futu-api-doc/quote/get-research-morningstar-report.html)给带更新时间的观点文本。这三类在 Agent 中应分成“线索、原始财务数据、第三方观点”。
- 官方 [AI 与 OpenClaw 页面](https://openapi.futunn.com/futu-api-doc/intro/ai.html)提供面向**开发工具**的 OpenD skills 与脚本，不是本产品的 Agent 运行时或授权边界；项目无需安装其交易脚本即可使用官方 Python SDK。

## 建议落地次序

1. 保留现有行情连接，新增统一 `FutuResearchClient` 只读适配器：逐接口超时、限频、权限错误分类、原始响应到产品模型的映射。结果记录 `provider`、`source_time`、`received_at`、市场/币种/单位、报告期/披露期和是否缓存。
2. 先接 P0 的板块热力图/广度、财报三表、资讯搜索与个股资金流。它们已在本机抽样可读，最直接改善用户要求的板块轮动、财报分析和新闻研究。对 AKShare 保持可见回退，但不混淆不同来源口径。
3. 再接服务器端筛选、机构披露与晨星观点；Agent 只能查询经过验证的只读工具，回答必须带数据时点与来源。宽市场扫描按批次缓存，不让每次对话重新消耗所有额度。
4. 最后按界面实际需要启用盘口/逐笔/分时推送；只订阅打开的证券详情和少数关注标的，退出后释放额度。每个市场的权限和延迟在交易时段单独验证。

这份盘点是能力与优先级，不表示 P0/P1 已经落地。券商交易接口和富途模拟交易仍保持关闭。
