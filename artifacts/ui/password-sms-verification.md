# 009 密码登录与火山短信：实施记录

2026-10-26，用户明确要求取消强制TOTP；该授权覆盖旧规格的验证器要求。

## 完成

- 默认password模式，旧TOTP设置/扫码/确认路由不再注册；登录页仅账号密码，重新确认/改密码界面也不含动态码。
- 密码正确后默认创建完整会话；SMS模式先验证密码，挑战只能发送至固定本人号码，验证后创建完整会话。保持账户归属、CSRF、审计、确认和模拟交易范围。
- 火山SMS采用官方Python SDK的V4签名、固定HTTPS SendSms端点和显式ENV凭据；不加载~/.volc、不自动重试、不打印手机号/验证码/供应商响应。
- .env已选择password并添加空短信字段，.env.example保留空凭据，配置/Spec见docs/SMS_SETUP.md及009。既有模型和身份密钥未修改。
- 身份SQLite迁移前已做权限600备份。迁移撤销旧会话，1个拥有者与6个活动模拟盘保留；未读取或修改用户现有密码。

## 观察与静态检查

- 本地服务独立后台运行，health正常；auth/status返回initialized=true、login_verification=password、mfa_required=false、password_only_trading=true。sms_deliveries为0。
- 已在真实用户HTTP标签页6刷新到新登录界面，确认只有账号和密码字段；截图password-login.png。没有代填用户凭据或绕过认证。
- Python compileall及premium-ui.json配置的JS语法命令完成；DESIGN.md lint为0错误/0警告。
- 严格UI扫描仍报22条actionless-button，报告password-sms-audit.json；主要是现有data-action全局代理/ID事件绑定无法被静态扫描识别。未宣称该严格报告通过。
- 未新增或运行测试套件，未执行改密码、模拟开户/清零/下单、短信发送或短信验码。

## 剩余边界

未提供真实火山AK/SK、消息组、已审核签名/模板和本人号码，未联调真实短信受理或运营商送达；未完成登录后敏感操作端到端验收。截图只证明默认登录表单更新，不能作为短信或交易成功证据。邮箱验证码未实现。
