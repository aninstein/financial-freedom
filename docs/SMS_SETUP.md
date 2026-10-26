# 密码登录与可选火山短信

## 直接登录（默认）

已有用户名、密码保持不变。刷新页面，输入账号密码即可进入，不再要求安装验证器或绑定二维码。首次升级会撤销旧会话，需要重新登录。交易、开户、清零等敏感模拟操作只重验当前账号密码，验证结果5分钟有效；普通会话保护、CSRF和确认窗口继续保留。仍不接实盘。

`.env`默认：

```dotenv
AUTH_LOGIN_VERIFICATION=password
```

未配置短信不影响这个默认模式。没有默认密码、公开注册、短信免密码登录或在线找回密码。忘记密码由本人在项目终端运行 `.venv/bin/python -m app.manage reset-password`。

## 火山短信配置

根据火山[调用方式](https://docs.volcengine.com/docs/SMSservice/Callmethod-7?lang=zh)与[Python SDK](https://docs.volcengine.com/docs/SMSservice/PythonSDK-4?lang=zh)，短信使用AccessKey ID和Secret Access Key签名，不是方舟模型API Key。发送还需要开通短信服务、消息组、审核通过的签名和验证码模板。因此一个API Key字符串不足以发送短信。

1. 在本人火山账号开通短信服务并准备余额。
2. 在短信控制台创建消息组、申请签名与验证码模板，等待审核通过。模板验证码参数名默认`code`，例如模板包含`${code}`。
3. 创建仅有所需短信发送权限的专用访问密钥，将以下内容填入本地`.env`；不贴入聊天、不写入源码。

```dotenv
AUTH_LOGIN_VERIFICATION=sms
VOLC_SMS_ACCESS_KEY_ID=
VOLC_SMS_SECRET_ACCESS_KEY=
VOLC_SMS_ACCOUNT=
VOLC_SMS_SIGN=
VOLC_SMS_TEMPLATE_ID=
VOLC_SMS_PHONE_NUMBER=
VOLC_SMS_CODE_PARAM=code
VOLC_SMS_REGION=cn-north-1
```

- `VOLC_SMS_ACCOUNT`：消息组ID（接口参数SmsAccount）。
- `VOLC_SMS_SIGN`：已审核短信签名内容（接口参数Sign）。
- `VOLC_SMS_TEMPLATE_ID`：已审核模板ID（接口参数TemplateID）。
- `VOLC_SMS_PHONE_NUMBER`：本人中国大陆手机号，11位或+86前缀。当前单拥有者版本仅向这个号码发送；页面不能填写其他号码。
- `VOLC_SMS_CODE_PARAM`：模板内验证码占位参数名称。模板如果还要求其他参数，应先使用仅包含验证码参数的模板；当前不自动猜测模板字段。
- `VOLC_SMS_REGION`：cn-north-1；固定官方HTTPS短信端点，禁止在页面提供任意URL。

填写后重启本地服务。保持`.env`权限600，不提交Git；`.env.example`只保留空值。若主动设为sms但缺少配置，登录会明确报错，不会静默降级。可在本机将模式改回password后重启恢复密码登录。

## 登录流程

账号密码验证 → 返回脱敏手机号的短信页面 → 本人点击“发送验证码” → 填写6位短信码 → 创建完整登录会话。只验证密码的中间状态不能访问账户或投研数据。无需手机验证器App。

服务端在发送前固化挑战、码摘要及发送额度，默认5分钟有效，每码最多5次错误，同一号码发送间隔至少60秒，每次挑战最多3次、滚动24小时最多10次。登录和验码还受IP/账号限流。验证码用独立随机数生成，仅HMAC摘要入库；挑战与浏览器HttpOnly Cookie、本人、密码版本及短信配置指纹绑定，成功原子消费，过期或新登录后不可重放。

SDK仅用于官方V4签名，使用显式ENV凭据，不读取其他应用的密钥或`~/.volc`文件；HTTP单次请求，不自动重发。短信回执只代表受理，不保证手机已送达；超时显示结果不确定，可能收到的验证码仍可验证。重发生成新码并作废旧码。短信费用由本人火山账户承担。

## 当前验证边界

接入实现与本地默认密码模式已配置；未提供真实短信凭据、签名和模板，没有发送付费短信或验证真实运营商送达。邮箱验证码尚未接入，本期选用用户指定的火山短信。
