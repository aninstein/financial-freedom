> 实盘API为暂缓草案，当前应用不注册；模拟账户生命周期API继续有效。最新范围见007。

# API增量 /api/v1

- POST `/paper/accounts/{id}/reset`、`/paper/accounts/reset-all`：body为label、market、initial_cash、confirm（分别`RESET PAPER ACCOUNT`/`RESET ALL PAPER ACCOUNTS`），带Idempotency-Key。仅清理当前用户范围，返回新账户及清理数量。
- GET `/live/status`：适配器目录、真实连接配置状态、发送开关、白名单与限额；不返回凭据。
- GET `/live/accounts/{connection_id}`：主动请求券商账户/持仓，不使用模拟余额。
- POST `/live/orders/preview`：connection_id、instrument_id、side、quantity、limit_price；返回45秒有效、绑定owner与配置指纹的preview_id。
- POST `/live/orders`：preview_id、confirm=`REAL ORDER`、Idempotency-Key；仅已开启发送的已配置连接；单笔/当日限额、现金数量及未知订单阻断。
- GET `/live/orders`：当前用户最近100笔本平台真实委托。
- POST `/live/connections/{id}/reconcile`：主动查询券商委托，按券商编号或QMT精确标签对账；无法确定的不自动重发。
- POST `/live/orders/{id}/cancel`：仅当前用户本平台的真实委托；撤单是请求，须查询回报。

全部接口受登录/MFA/CSRF保护。重开和所有实盘POST要求最近5分钟重新验证。实盘连接在ENV定义，不接受任意URL、账号密码或模型自选账户。网关自己的回环HTTP接口使用独立Bearer凭据，不能公网暴露。
