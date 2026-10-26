# 个股资料与身份边界检查记录

日期：2026-10-26。未创建生产测试账户，未代填本人密码或验证器，未执行任何交易、账户写入或资料删除。

## 已执行

- `node --check` app.js / api.js / ui.js / identity.js / stock.js。
- `.venv/bin/python -m compileall -q app scripts`。
- DESIGN.md官方lint，结果随本轮命令记录。
- 实际本机服务HTTP读取：health/auth status返回200；匿名accounts、quotes、ai/documents、/docs、/openapi.json均401。
- 已观察no-store、nosniff安全头；.env及两份SQLite为600、data目录700。
- 公开数据采集：CN:600519的profile、snapshot（23项）、financials（24行）、announcements（20条）、income（9指标）、balance（12指标）、cashflow（6指标）均返回available并已缓存。
- 参考项目AI首选模型已按官方快捷配置+JSON列表的优先级同步到本机ENV。仅检查配置解析及首选匹配，未发送实际LLM请求；默认不跨供应商回退。
- 扫描Git候选文件与当前ENV密钥值，没有检测到密钥泄漏；暂存区为空，没有执行commit/push。本地ENV及其变体被忽略，.env.example保留可提交。
- 企业已有core.hooksPath保持原样，未覆盖；新增的暂存区扫描脚本可手动运行或接CI。
- 浏览器正常HTTP入口显示私人空间初始化页，工作空间内容隐藏，没有匿名管理员创建入口。

## 浏览器范围与未完成检查

首个账户必须由本人在终端创建，之后本人绑定验证器。尚不能声明完整MFA登录、恢复码、会话撤销、重新验证或登录后的个股UI已经通过操作验证。

尝试打开仅含公开OHLC的file://预览时，浏览器安全策略拒绝了该协议；没有通过其他浏览器或临时HTTP服务绕过该限制，生成的临时预览已移除。K线纯渲染代码曾以253根真实公开日线生成SVG，但这不代替正式页面的视觉/交互检查。

未新增/运行自动化测试套件，也未执行渗透测试或宣称安全认证。财务SQLite当前不是整体加密数据库，需要系统磁盘与备份加密配合。

## 静态审计

保存原始strict报告。该扫描器只认HTML onclick/Vue属性，无法理解本项目ES modules中document点击委托或ID绑定事件，会把有真实处理函数的按钮标为actionless。不得为消除此类误报添加空onclick；报告不替代运行时检查。


## 最终补充

- 重启后匿名ai/status仍401，/.env返回404，不受信Host返回400，跨站Origin登录请求403。
- DESIGN.md lint为0 errors / 0 warnings；strict静态扫描15条均为actionless-button规则，属于事件绑定识别限制，原始报告已保存。
- 浏览器viewport能力调用没有改变实际934×984视口（DOM尺寸与截图均确认），已恢复默认尺寸；本轮登录页窄屏视觉检查未完成，不以同尺寸截图冒充手机结果。
- 正常HTTP入口的初始化截图已保存，不含用户名、密码、绑定密钥或恢复码。

- 最终服务再次确认health/status正常、匿名个股详情和TOTP二维码均401、ENV文件404。MFA提升与重新验证会轮换会话/CSRF，未通过本人初始化前不宣称完整链路已验证。
