# 工作包

- WP01 实现：默认密码登录、移除强制TOTP入口、迁移旧会话。
- WP02 实现：密码敏感确认与修改密码流程，保留CSRF和审计。
- WP03 实现：官方SDK V4签名与火山SendSms，固定接收号码、签名/模板/配置指纹。
- WP04 实现：短信挑战、验证码HMAC、原子消费、冷却/次数/每日额度、未知状态。
- WP05 实现：登录/短信/安全页共享界面，ENV example和本机空配置。
- WP06 已完成语法/静态/本地启动观察：语法/静态/本地运行；无短信凭据不发送真实短信，不执行模拟交易或用户密码重置。

运行观察：auth/status=initialized:true, login_verification:password, mfa_required:false；保留1个拥有者和6个活动模拟盘。已在实际浏览器刷新并看到仅账号/密码的登录页，截图artifacts/ui/password-login.png。未替用户输入密码、执行改密、模拟委托、发短信或完成登录后流程；SMS真实送达待本人凭据及模板配置后联调。
