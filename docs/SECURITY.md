# 本地账户安全

## 当前认证策略（009，2026-10-26）

按用户明确要求，默认账号密码登录，取消强制验证器。升级撤销旧会话，保留既有用户名、Argon2id密码、资料和模拟盘。刷新网页后使用原密码即可。

首次账户仍由本人在项目终端运行 `docker compose exec web python -m app.manage init-owner` 设置，无默认密码或公开注册。忘记密码使用同一容器内的 `reset-password`，不通过聊天收集密码。

会话为服务端可撤销的HttpOnly / SameSite=Strict Cookie，最长8小时、默认闲置20分钟锁定。Origin、Host、CSRF、CSP、非回环HTTPS约束及HMAC审计链保留。密码变更和认证策略变更撤销所有旧会话。交易、开户、清零等敏感操作要求最近5分钟密码确认并轮换会话/CSRF；原有预览、危险确认及服务器风控继续有效。

`AUTH_AUDIT_KEY`继续用于审计签名，`AUTH_ENCRYPTION_KEY`保留本机安全配置和旧数据兼容；旧TOTP种子不再参与认证，旧设置/扫码端点撤下。请保管 ENV、Compose secret 和 MySQL 数据卷备份；有 Docker 管理权限的操作者可访问数据库。MySQL 默认不发布宿主端口，持久卷仍需磁盘与备份加密。

## 微信小程序登录

小程序使用 `wx.login` 临时 code；只有服务端保存 AppID/AppSecret 并调用微信 `code2Session`。OpenID 仅以 HMAC 摘要写入绑定表，`session_key` 不落库、也不下发小程序。首次绑定要求现有 owner 的账号密码；微信身份本身不会创建账户。密码变更会提升用户版本，旧绑定须重新验证当前密码。

已绑定微信身份只换取 60 秒、单次使用的网页登录票据。票据放在网页入口的 URL fragment，网页立即移除 fragment，再同源提交票据并接收原有 HttpOnly Cookie；票据和账号密码不会进入服务端 URL 日志。微信登录不会算作最近五分钟的密码重验，敏感操作仍需重新输入工作台密码。请同时把 HTTPS 站点配置为小程序业务域名与 request 合法域名，并在服务端私有环境配置 `WECHAT_MINIPROGRAM_APPID` / `WECHAT_MINIPROGRAM_SECRET`。

## 模拟与真实资金边界

模拟账户按owner_id校验，订单、成交、AI任务按账户隔离；服务器固化白名单、额度、笔数，清零需危险确认/近期密码/CSRF/幂等。模型不能改变账户归属或扩大权限。实盘仍暂缓，券商草案未加载运行时，不需要券商账号密码。

用户密码、模型密钥只在本人终端/本地ENV及受保护服务端处理。含账户数据的AI分析仍需原有明确授权。
