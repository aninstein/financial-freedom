# 朱红主题改版记录（2026-10-26）

- 共享 CSS token 为主题来源，DESIGN.md 同步镜像；暖黑底、朱红主按钮、暖白文字、浅朱红链接，柔和红色选中态及弹窗标题。
- 清理旧青绿品牌色，包括导航、标签、推荐卡片、对话输入框、折线图、侧栏及登录页。模型状态标签改用 accent 命名。
- 行情使用独立 market-up / market-down：报价、板块、涨跌家数和 K 线统一红涨绿跌；错误/危险动作不受行情语义影响。
- 修正 K 线读数粗体覆盖涨跌色的选择器；主按钮 hover 继续保持朱红背景。

## 检查记录

- node --check：app.js、ui.js、stock.js 通过。未新增或执行测试套件。
- designmd lint DESIGN.md：0 errors / 0 warnings。
- strict UI 静态审计：15 条既有 affordance.actionless-button 报告；扫描器不能识别事件委托与 JS 按 ID 绑定的处理器，本次未修改这些行为，原始输出见 red-theme-audit.json。审计不算通过。
- 旧品牌色搜索：原青绿主色及绿色选中背景已移除。
- 浏览器刷新实际应用：初始化页主按钮计算色 rgb(184,62,50)，文字 rgb(255,245,241)，主色 #f47b68；视口宽934px与页面 scrollWidth 一致。
- 截图：private-initialization-red.png。当前应用停在首次账户初始化页，受保护的聊天/行情/弹窗尚未进行登录后视觉核验；这些页面使用已改动的共享样式。未绕过登录或创建账户。

## 静态对比度（正文尺寸，WCAG公式）

- primary button: 5.19:1
- accent text: 6.64:1
- muted text: 7.52:1
- rise: 6.88:1
- fall: 8.59:1
