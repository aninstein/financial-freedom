# API 与工具

全部研究/模拟API继续使用已有登录、MFA、同源与写请求CSRF机制。实盘路由未注册。

| 接口 | 用途 |
| --- | --- |
| POST /api/v1/paper/accounts | 创建本人模拟盘，自填资金；Idempotency-Key |
| POST /api/v1/paper/accounts/{id}/reset | 单盘清零并新开；确认字段、近期MFA、幂等键 |
| POST /api/v1/paper/accounts/reset-all | 本人所有活动模拟盘清零后新开一个盘；同上 |
| GET /api/v1/workspace/indices | 指数目录及上次采集状态 |
| GET /api/v1/workspace/indices/{INDEX:id}?refresh=false | 指数日线、来源状态、历史统计 |
| GET /api/v1/research/cycles?instrument_id=CN:600519&years=5 | 1至10年本地历史统计 |
| GET /api/v1/research/flows?refresh=false | 沪深大盘资金历史及覆盖 |
| POST /api/v1/research/funds/collect | {codes:[六位代码],year:年份}，最多5只 |

新增Agent只读工具：get_index_analysis（无ID返回目录）、get_historical_cycles、get_market_flow_history、collect_fund_disclosures、read_uploaded_document（page/offset）。search_uploaded_documents支持document_id过滤。股票、财务、板块、重大基金买卖、文档检索与基线回测工具继续使用。

响应的received_at是接收时间，不等于行情/披露时间；指数as_of以日线bar_time为准；资金与基金披露的来源日期、报告期和单位以原始字段为准。缺失值保持null。历史统计返回sample_hash、method_version、observations、first_bar、last_bar、data_gaps。
