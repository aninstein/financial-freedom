# 认证API

| 接口 | 行为 |
|---|---|
| GET /api/v1/auth/status | 初始化状态、login_verification=password/sms、mfa_required是否需短信 |
| POST /api/v1/auth/login | username/password；默认返回完整身份，sms模式返回202、requires_sms、challenge_id、masked_phone、expires_at |
| POST /api/v1/auth/sms/send | challenge_id及绑定Cookie；密码已校验才可发送，60秒冷却/3次挑战/10次日额度 |
| POST /api/v1/auth/sms/verify | challenge_id、6位code及绑定Cookie；原子消费并创建完整会话 |
| POST /api/v1/auth/reauth | 当前账户password；轮换会话/CSRF，5分钟近期确认 |
| POST /api/v1/auth/password | password、new_password；更改后撤销所有会话 |
| GET /api/v1/auth/me | 身份/权限、当前登录方式、短信配置完整性、会话/近期验证到期 |

登录、短信发送和验码是公开但强制Origin+JSON的接口，不接收任意手机号、模板或消息。挑战令牌不是完整会话，必须结合HttpOnly/SameSite登录流程Cookie。错误保持通用账号密码提示；短信错误不返回供应商原文、手机完整号码或验证码。验证码不出现在返回、URL、日志或审计里。

原totp/setup、totp/confirm、totp/qr不再注册。旧存储字段保留兼容本机恢复和历史备份，不用于认证。
