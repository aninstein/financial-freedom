# 工作空间 API 增量

## GET /api/v1/quotes?browse=true

可选 market、q，limit 1–1000，offset ≥0；q 匹配代码、名称及标准标的ID。返回 quotes、count、total_count、offset。默认非 browse 保持原有行情/Agent调用行为。

## GET /api/v1/workspace/instruments/{instrument_id}?days=250

days 20–500。标的格式 MARKET:CODE，港股补齐五位、黄金保留代码大小写。返回标准ID、名称、quote（可为null）、watched、bars、bars_source、daily_metrics及数据缺口。bars按时间升序，数值只来自本地真实行情/日线。

## GET /api/v1/workspace/sectors?name=行业名&refresh=false

无name返回A股行业目录；有name还尝试成分股和行业资金。返回原始中文字段 sectors/summary/constituents/flow、source、received_at、exchange_time（来源未提供为null）、freshness、errors、flow_note、state。

state: available / partial / stale / unavailable。独立源共享20秒响应预算；成功缓存300秒，异常60秒退避，refresh可重试。不把接收时间当源行情时间，不插入假资金数据。

## POST /api/v1/ai/research

原有请求增加history，最多12个role/content对象；只保留user/assistant角色，每条截断4000字符。前端带最近10条正常消息。账户仍需include_account/account_id显式选择。

同步响应新增cards列表，kind为instrument/sector/market。卡片仅由实际工具evidence生成，包含标准标的/行业/市场及evidence_ids；前端构造本地详情路由。历史列表和单次运行端点也返回cards。

新增只读工具search_instruments(query)、get_sector_overview(name)，复用同一数据与来源口径。模型不可用仍返回503，工具不包含订单写入。
