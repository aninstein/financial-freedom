# 接口

沿用已有登录/MFA、Host/Origin和写请求CSRF保护，不接收用户提供的任意抓取URL。

| 路由 | 用途 |
| --- | --- |
| GET /api/v1/research/news?query=&limit=30&refresh=false | 分源快讯、首次观察文本、发布时间、首次采集、关键词关联候选 |
| GET /api/v1/research/liquidity?refresh=false | 央行最近6份公开市场公告、分期限操作量/利率、原文、到期/净投放null |
| GET /api/v1/research/rotation?refresh=false | 三窗口相对强弱、共同样本、采集日历史、方法与缺口 |

Agent新增只读工具：get_market_news(query,limit)、get_macro_liquidity()、get_sector_rotation(name可选)。轮动默认每阶段最多4个摘要，指定name可查询对应行业；完整列表在页面。新闻工具返回最多10条、内容片段600字符；央行工具最多4份、原文片段1200字符，不能声称已读未返回的全文。

数据：research_news保存首见新闻；sector_rotation_snapshots按采集日期存最后成功完整快照；workspace_cache继续保存分源载荷和失败状态。news_id由来源/发布时间/标题哈希，content_hash对应首次观察内容。

前端入口：#/news、#/liquidity、#/rotation；market-context.js负责页面和60秒新闻刷新，离开/退出取消计时器及等待。全局股票及模拟盘路由保持。
