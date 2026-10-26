# 身份与个股资料 API 增量

所有路径均以 `/api/v1` 为前缀。除 `/auth/status`、`/auth/login` 和匿名health外，API必须有HttpOnly会话；非绑定流程还必须已完成MFA。

## 身份

| 路径 | 方法 | 作用 |
|---|---|---|
| /auth/status | GET | 初始化状态、注册关闭、MFA要求；不返回用户名 |
| /auth/login | POST | username/password/code；Origin校验、数据库限流，返回用户/权限/CSRF及会话Cookie |
| /auth/me | GET | 当前身份、MFA状态、CSRF、过期时间 |
| /auth/logout | POST | 删除当前会话及Cookie |
| /auth/totp/setup | POST | 仅未绑定的近期密码会话；生成5分钟绑定资料 |
| /auth/totp/qr | GET | 当前会话的本地绑定二维码；未认证不可读取 |
| /auth/totp/confirm | POST | 验证TOTP、提升MFA会话并一次返回10条恢复码 |
| /auth/reauth | POST | password/code；提升当前会话5分钟敏感操作窗口 |
| /auth/sessions | GET | 当前用户的会话描述，不返回原始Cookie |
| /auth/sessions/{id} | DELETE | 重新验证后撤销本人会话 |
| /auth/password | POST | 当前密码+验证代码+新密码，成功撤销所有会话 |
| /auth/audit | GET | 最近100条脱敏安全事件 |

错误detail为 `{code,message}`；422不回显输入。401 SESSION_EXPIRED要求重新登录；403 MFA_REQUIRED限制绑定流程；403 CSRF_FAILED拒绝来源/CSRF；428 REAUTH_REQUIRED在进入业务处理前拒绝敏感操作；429限流。

写请求须包含精确Origin及会话返回的X-CSRF-Token。X-Finch-Active=1仅用于真实用户活动续期，后台轮询不发送。浏览器CSRF令牌仅存内存，Cookie不允许JavaScript读取。

## 个股

`GET /workspace/instruments/{id}?days=500` 返回完整OHLC、volume、volume_unit、amount、turnover、来源/接收时间、指标及资料关联；既有缓存未知单位为unknown。价格历史当前adjustment=none。

`GET /workspace/instruments/{id}/dossier?sections=profile,snapshot&refresh=false`

可选profile/snapshot/financials/income/balance/cashflow/dividends/ownership/holders/business/flow/news/announcements/reports，一次最多8类。返回sections字典，各分项包括state、rows、source、source_time、received_at、freshness、unit_note及缓存标记。状态available/empty/stale/error/unsupported。原始查询链接由合法标的代码构造。

- 公司/财务/股东等最多24小时缓存；盘口/资金/新闻/公告5分钟；错误/空结果2分钟退避。
- 分项采集在有界子进程中执行，单个子进程16秒预算，聚合响应18秒预算、最多3并发。超时进程终止，不在服务器留下永久阻塞的抓取线程。
- 同一分项共享正在执行的作业；查询不接受自由URL或源凭据。
- 三表按原始报告期最多8期转置，金额单位及累计口径保留；十大股东的日期来自已披露的明确截止日。

AI工具get_stock_dossier可读取同一分项；没有鉴权管理、密钥读取或订单写入工具。默认仅首选模型，含账户上下文请求禁用跨模型回退。
