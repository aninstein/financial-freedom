# 开源股票交易系统与接口调研

检索日期：2026-10-27。以下区分“开源引擎”“券商官方 API”和“本项目现状”；是否能够交易特定账户，最终取决于券商账户、地区、权限、终端版本及数据许可。

| 方案 | 模拟能力 | 实盘接口能力 | 对本项目的判断 |
| --- | --- | --- | --- |
| [VeighNa / vn.py](https://github.com/vnpy/vnpy/blob/master/README.md) | 官方 [PaperAccount](https://github.com/vnpy/vnpy_paperaccount/blob/main/README.md) 以接入行情在本地撮合 | 官方列出 A 股 XTP/TORA 等网关，也有算法/组合策略模块；网关取决于相应券商授权 | A 股生态和网关抽象值得参考；PaperAccount [不计算虚拟资金](https://github.com/vnpy/vnpy/blob/master/docs/community/app/paper_account.md)，不宜直接替换现有可核算现金的模拟账本。官方 SimNow 示例是期货 CTP，不能当作股票模拟账户。 |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | [Paper Brokerage](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/quantconnect-paper-trading) 支持美股等资产的虚拟成交 | [经纪商列表](https://www.quantconnect.com/docs/v2/lean-cli/live-trading/brokerages) 有 IBKR、Alpaca 等多家；[本地部署 CLI](https://www.quantconnect.com/docs/v2/lean-cli/api-reference/lean-live-deploy) 另有环境和账户要求 | 适合未来独立策略执行引擎；当前 FastAPI 项目为两页引入 C#/Docker 引擎成本较大，且不能解决中国大陆券商账户授权。 |
| [Backtrader](https://www.backtrader.com/docu/live/ib/ib/) | 可对接 IBKR 纸面账户 | 文档说明 IBKR 实时数据和交易集成 | 候选策略框架，但所查官方集成文档依赖 IbPy，需独立核验维护和兼容性；本期不作为接入基础。 |
| [富途 OpenD / 官方 SDK](https://openapi.futunn.com/futu-api-doc/trade/trade.html) | 官方 `SIMULATE` 环境，可模拟股票；[模拟规则](https://openapi.futunn.com/futu-api-doc/en/qa/trade.html) 与真实成交不同 | 官方 `REAL` 环境提供账户、委托、改单/撤单接口；[真实委托需解锁交易](https://openapi.futunn.com/futu-api-doc/en/trade/unlock.html) | 选为本 change 的港美股票交易接口。官方定义 A 股 `CN` 市场仅模拟；A 股通 `HKCC` 单独验收。 |
| [IBKR TWS API](https://ibkrcampus.com/docs/tws-api/doc/notes-limitations/tws-api-limitations) | 官方纸面账户，成交行为与真实环境可能不同 | TWS/IB Gateway 提供订单、资产和持仓 API；[账户与端口隔离](https://ibkrcampus.com/docs/third-party-integrations/general-third-party-frequently-asked-questions) 需明确 | 适合未来海外市场连接；当前仓库无驱动，不在首期可发送名单。 |
| [迅投 xtquant / QMT](https://dict.thinktrader.net/nativeApi/xttrader.html) | 取决于券商终端提供的测试环境；本项目另有自己的本地模拟账本 | 官方交易模块列出报单、撤单、资产、持仓、订单查询和订单状态 | 大陆 A 股全市场的后续候选；本 change 以富途为首期接口，不启用现有 `qmt_http` 草案。PTrade 不等于 QMT。 |

## 选型结论

1. 页面布局参考 [VeighNa Trader 的交易组件与活动/成交/委托监控](https://www.vnpy.com/docs/cn/community/info/veighna_trader.html) 和开源 [FreqUI 的账户状态/交易总览](https://github.com/freqtrade/freqtrade/blob/develop/docs/freq-ui.md)。前者是桌面交易终端，后者服务加密资产机器人；只借鉴信息架构、状态分区和高风险动作的显著性，沿用本站视觉语言与股票业务字段，不复制界面资产或 GPL 代码。
2. `#/paper` 保留现有本地模拟账本，并新增富途 OpenD `SIMULATE` 账户作为独立来源。现有账本支持虚拟现金、独立账户和订单；富途模拟是券商端模拟，须用富途 `acc_id`/`trd_env` 查询与下单。两者订单、资金和收益不合并。富途模拟[不支持成交明细相关查询/推送](https://openapi.futunn.com/futu-api-doc/en/qa/trade.html)，因此页面不可假装有完整逐笔成交记录。
3. `#/live` 首期只对接富途 OpenD 官方 `REAL` 接口。官方提供[账户、资金、持仓、最大可买卖、订单、撤单和回报接口](https://openapi.futunn.com/futu-api-doc/en/trade/overview.html)。必须用稳定 `acc_id` 而不是会变化的 `acc_index`；[`place_order` 支持 `trd_env`、`acc_id` 和 `remark`](https://openapi.futunn.com/futu-api-doc/en/trade/place-order.html)。实盘交易需要[本人在 OpenD 解锁](https://openapi.futunn.com/futu-api-doc/en/trade/unlock.html)，但网页/Agent 不收集交易密码。所查文档没有独立的只读“解锁状态查询”接口，页面不得声称已验证解锁；锁定时以富途明确拒单回报呈现。
4. [富途官方交易定义](https://openapi.futunn.com/futu-api-doc/en/trade/trade.html) 明确 `CN` A 股市场只支持模拟，`HKCC` A 股通只支持部分标的实盘且不能模拟。首期实际发送限经账户权限核验的港股/美股现金限价单；HKCC 另行验收。QMT/盈立代码保留为未启用草案，不是本 change 的首期接入。
5. 本地模拟、富途模拟和富途实盘从页面/来源标签、环境、账户 ID、存储、幂等键、确认文案和订单状态完全区分。模拟结果不能作为真实可用资金、持仓或成交证明。

## 仓库现状与缺口

- `app/main.py` 已注册 `/api/v1/paper/*`，`prototype/paper.js` 已有账户、委托和 AI 实验 UI；`prototype/app.js` 目前将旧交易地址重定向至持仓页，导航不显示模拟页。
- `app/live.py`、`app/brokers/`、`prototype/live.js` 和 `docs/BROKER_SETUP.md` 是未注册的实盘草案。`app/main.py` 当前健康状态仍写 `live_trading: deferred`，因此不能把代码存在当作可交易。
- `app/futu_feed.py` 与 `app/futu_launcher.py` 当前用于行情/OpenD 登录窗口，尚无富途交易适配器。需新增交易上下文，不能把行情端口可达推断为交易账户可用。
- 现有实盘草案针对 QMT/盈立，不能直接解除路由屏蔽或假定兼容富途。新适配器及持久化必须按当前 MySQL 数据层、鉴权/CSRF、重验、环境开关、富途订单回报和故障恢复重新实施。旧 [券商配置草案](../../../docs/BROKER_SETUP.md) 实施时更新为富途优先状态。
