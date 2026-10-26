# 010 API

GET /api/v1/workspace/indices/live：要求已登录。只读内存快照，不查询外部源。响应包含 indices、served_at、display_interval_seconds、akshare_poll_seconds、current_poll_seconds、provider、longbridge_connected、source_errors、source_attempted_at。每个指数含 id/name/market、last、change_percent、previous_close、open/high/low、volume/turnover、source、source_time、received_at、known_delay_seconds、feed、state、age_seconds、source_age_seconds、market_session。缺失值用 null。

GET /api/v1/workspace/indices/{index_id}：默认快速返回历史缓存及历史统计；refresh=true 明确触发日K重新采集。历史日K与盘中指数快照绝不合并。
