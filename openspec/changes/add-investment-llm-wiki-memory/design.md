## Context

项目是 FastAPI + MySQL 的本地投研/模拟交易工作台，DeerFlow 通过私有 Unix socket 运行。当前 `app/deerflow_worker.py` 关闭 DeerFlow memory、使用每次研究的 `run_id` 作为 thread ID，并只拼接请求传入的少量历史。`prototype/app.js` 把聊天 session 保存在浏览器 localStorage；`ai_research_runs` 保存研究运行而不是完整、可靠的跨会话历史。账户设置目前是个人资料/安全弹窗。本文只定义待实施的 OpenSpec change，不声称功能已经落地。

参考 OpenClaw 的[分层记忆](https://docs.openclaw.ai/concepts/memory-architecture)、[每日整理与晋升](https://docs.openclaw.ai/concepts/dreaming)和[带时间衰减的检索](https://docs.openclaw.ai/concepts/memory-search)：将小而稳定的核心信息与按日增长的经历分开；晋升由带来源的候选经过门槛和合并；近期 daily 在召回中获得更高权重。本项目的投资记忆还要区分“用户说过的话”和“可核验的金融事实”。

## Goals / Non-Goals

**Goals:**

- 每个用户拥有私有、可浏览、可备份的 llm-wiki；任何 session 都能看到同一用户的有效记忆。
- 逐日落盘原始会话和摘要；当天跨 session 共享摘要，跨天只通过 daily 与派生条目召回。
- 每日自动、手动和补档都可重试、可溯源、可重算；短期事项可在满足条件后抽象为长期偏好。
- 账号设置管理原始 session 最多 30 天、归档记忆最多 365 天的保留期。
- 记忆影响研究重点和个性化建议，但不充当行情、持仓、收益或交易授权的权威源。

**Non-Goals:**

- 不让模型直接遍历文件系统或读取历史原始 session 文件。
- 不自动扩大账户读取、模拟/实盘下单权限；本次不接入实盘。
- 不把 llm-wiki 当作行情库、研报原文库或完整交易审计库。
- 不保证模型对历史自然语言的每次抽象都正确；支持用户更正和来源回查。

## Decisions

### 1. 服务端拥有会话与记忆状态，Markdown 是可读投影

以 MySQL 保存用户设置、session/message ID、消息时间/来源、归档任务水位、记忆条目元数据、来源关系和文件 manifest。用户 wiki 放在共享持久卷 `DATA_DIR/llm-wiki/users/<opaque-owner-id>/`；`opaque-owner-id` 由服务端 ID 映射生成，不接受客户端路径。逐轮消息用按天 JSONL 写入，wiki 其余内容为 Markdown。MySQL 元数据负责并发、幂等和可查询的状态；Markdown 文件可导出阅读，但 `index.md`、`log.md`、`readme.md` 由服务端统一维护。

目录约定如下；**所有实际创建的目录**，包括日期目录，均含三份小写的约定文件：

```text
llm-wiki/users/<owner>/
  index.md  log.md  readme.md
  sessions/
    index.md  log.md  readme.md
    YYYY-MM-DD/
      index.md  log.md  readme.md
      <session-id>.jsonl
      <session-id>.summary.md
  daily/
    index.md  log.md  readme.md
    YYYY-MM-DD/
      index.md  log.md  readme.md
      report.md                 # provisional 或 final，带版本和来源水位
  short-term/
    index.md  log.md  readme.md
    <memory-id>.md
  long-term/
    index.md  log.md  readme.md
    <memory-id>.md
```

`index.md` 是条目导航、标签、日期与摘要，支持从根目录逐层定位；`log.md` 记录无正文的创建、修订、晋升、失效和清理事件；`readme.md` 解释该目录的层级、写入者、召回和保留规则。每份记忆正文使用结构化 front matter：`id`、`owner`、`tier`、`status`、`created_at`、`last_grounded_at`、`expires_at`、`source_refs`、`provenance`、`confidence`、`supersedes`、`content_hash`。日志和索引中的个人内容同样受保留/删除传播约束。

**备选方案：**仅把文件当数据库，难以处理并发归档和幂等；仅存 MySQL，用户要求的可阅读 llm-wiki 目录无法成立。采用数据库控制面加原子文件投影。

### 2. 会话与日界线

这里的“投研 session”是应用对话 ID，与登录 Cookie session 不同。前端创建对话时由服务端发 ID；每条消息有服务端时间、客户端幂等 ID、角色、来源类、关联 run ID。服务端保存用户输入与展示给用户的 Agent 回复；工具原始负载、密钥、完整账户快照不写入 session 日志。长对话跨午夜时按消息 `Asia/Shanghai` 日期拆入对应日目录，session ID 不变。每轮完成后更新该日 session 摘要；摘要只包含可追溯的主题、明确偏好、计划、决策、未完成问题和来源消息 ID，不复制长段对话。

当天跨 session 召回先读 provisional daily；若最新消息尚未进入 daily，则读当天其他 session 的**摘要**作为补充。当前 session 可用自身最近几轮原文维持对话连贯。昨天及更早的原始 session 与摘要仅对归档/用户查看可用，不进入投研 Agent 的检索工具。原始 JSONL 路径从不作为 MCP、Skill 或模型工具参数暴露。

**备选方案：**直接把其他 session 原文塞进提示词，成本、隐私面和旧市场信息污染都更高；只等夜间归档又无法满足当天跨会话共享。

### 3. daily 归档作业、手动动作和失效重算

计划时间是每天 03:00 Asia/Shanghai，归档前一自然日。作业由独立调度器或服务端定时任务驱动，状态键为 `(owner_id, local_date, input_watermark)`，状态为 `queued → running → validated → published`，失败可到 `retry_wait`，超过预算到 `degraded` 并告警。启动时扫描缺档日期补跑。手动归档使用同一作业管道；对当天产出 `provisional` 版本，后续消息提高水位，夜间生成 `final`。晚到、编辑或删除消息触发受影响日期的重算。

归档流程：读取当天**全部** session 日记录和逐日摘要 → 分块生成候选事件 → 用程序校验每条候选的 `session_id/message_id`、时间、来源和引用片段 → 合并重复主题与矛盾 → 生成 daily 报告 → 生成/刷新 short-term 候选 → 长期晋升评估 → 写临时文件、校验哈希和 manifest → 原子替换报告及索引 → 提交发布水位。模型只负责摘要和抽象；它的每一条可召回断言都必须能回指有效消息或已核验的系统结果。模型失败时发布标明 `degraded` 的确定性摘要，不虚构观点。

报告包含当日主题、用户表达的偏好、研究/操作建议与用户决策的区别、仍待处理事项、相反证据/矛盾、来源引用和归档状态。没有消息的日期仅记录空状态，不生成伪报告。日报是主要历史检索单元；归档过程本身可以读原文，普通投研 Agent 只能读发布后的报告与派生条目。

### 4. 短期/长期判定与晋升

| 层级 | 内容 | 典型寿命与更新 |
| --- | --- | --- |
| 当日 session 摘要 | 同日其他对话的最新主题 | 当天热上下文；原始和摘要最多 30 天 |
| Daily | 一天的可追溯经过与结论 | 每日归档；最多 365 天；召回主来源 |
| Short-term | 近期具体标的关注、临时计划、待办、当前假设 | 有到期/完成条件；以近期为主，受归档期限限制 |
| Long-term | 稳定投资目标、经常使用的分析方法、风格、风险偏好、经验原则 | 抽象且跨情境；有明确来源、版本与复核时间，最长不超过归档期限 |

分类先做硬过滤：仅用户明确表达和经项目数据层验证的操作结果可支持偏好/经验；网页、研报、MCP、Skill、模型自述和未验证的投资结论不得冒充用户偏好。明确说“以后/长期/默认”的用户陈述可直接成为 `explicit` 长期记忆，用于只读建议的个性化；它不等于账户读取或交易授权。其他具体新信息先入短期。跨至少 **2 个自然日、3 个不同用户会话**、主题相近且无未解决矛盾的短期条目，可形成概括性 `inferred` 长期条目；跨不同问题的复现、基础程度和抽象程度提高候选得分。低频但用户明确标为基本原则的内容无需等频率门槛。数值事实、一次性情绪和短期市场判断不因高频而晋升为长期事实。

`inferred` 长期条目可辅助研究排序和措辞，但不能作为仓位、止损或交易权限的确定约束；要影响这类约束需用户明确确认。每条晋升保留支持/反对来源、归纳句和 `explicit/inferred/confirmed/superseded` 状态。后续用户更正优先，系统对旧条目做 supersede，不静默重写历史。候选晋升前重新检查实时来源是否仍存在，删除或过期来源不参与。召回次数只能用作排序信号，不因“被 Agent 自己反复引用”而自行强化为真实偏好。

**备选方案：**所有短期内容自动升级会把重复错误固化；所有长期项都要求额外确认则会丧失自动整理价值。采用带状态的自动抽象、明确偏好即刻可用、交易相关约束确认的分级路径。

### 5. 召回顺序、预算与冲突

`get_investment_memory(owner_id, query, as_of)` 先按 owner、状态、过期、时间和来源类别做硬过滤，再做关键词/语义混合召回与去重。服务端固定注入小型用户核心档案；相关召回优先近 3 日 daily 和当日摘要，随后 short-term，再补充较旧 daily 和 long-term。默认最多 10 个片段、约 2,000 tokens；一个主题的重复片段合并。daily 采用 14 日半衰期、short-term 采用 21 日半衰期；long-term 不做日衰减但受 `last_grounded_at` 和保留期限约束。相近相关度且同等来源权威时，短期权重高于长期。可记录命中率、误召回和 token 成本后调参。

强制优先级是：**用户最新明确更正/确认 > 可核验账户及市场事实 > 已确认记忆 > 未确认推断**。因此“短期优先”不能覆盖用户明确的长期风险边界，也不能覆盖现时账本。冲突双方连同来源返回，Agent 在本次建议中注明冲突；需要更新长期规则时给用户可审阅的修订入口。结果只给摘要片段和逻辑来源引用，不给历史 session 原文或任意文件路径。

### 6. 保留、删除与账户设置

每账户两项设置：`session_retention_days` 默认 30、范围 1–30；`archive_retention_days` 默认 365、范围 1–365。账号设置显示期限、最近归档状态、最早可读日期、手动归档、记忆查看/更正/删除。原始消息与 session 摘要按消息所属本地日期过期；daily、short-term 和 long-term 按最近有效用户来源或用户再次确认的 `last_grounded_at` 计算到期，**普通检索命中、模型复述和归档重跑不延长寿命**。缩短期限触发后台清理并立即阻止到期内容再被召回；异步删除文件、索引、缓存和只含该来源的派生条目。备份/恢复按同一留存策略处理，恢复后先重放清理再开放检索。

清理前补跑仍在期限内的缺档；如果归档一直失败，到原始期限时仍删除原始记录并记录可见缺口，不能无限延长 30 天上限。用户删除某一 session 时，服务端删除原始记录并撤销只由其支持的派生内容；其他来源仍支持的摘要重算。安全审计可留下不含聊天正文的最小删除事件，wiki `log.md` 中的个人化元数据也按期限清理。已删除内容不得从搜索索引或缓存复活。

### 7. DeerFlow 边界和授权

向 DeerFlow 注册窄接口 `get_investment_memory`、`get_memory_entry`（只读已发布条目）和可选 `propose_memory_correction`；运行时从已认证请求获得 `owner_id`，不能由模型填写。工具默认不提供原始 session 文件、任意路径、SQL 或 wiki 写入。归档服务使用独立内部权限，不继承 Agent 的普通研究工具权限。读取账户仍沿用 `include_account/account_id` 的本轮显式授权；记忆不会传递或扩大这一授权。模拟交易仍走既有 Broker 风控与授权路径。

模型输出中关于价格、财务、持仓和订单的事实必须从行情/研究/账本工具重新获取并标注数据时点；记忆引用只支持“你此前说过/我们曾讨论”，不能证明当前市场事实。

### 8. API 与兼容迁移

建议 API：`POST /api/v1/ai/sessions`、`GET /api/v1/ai/sessions`、`GET /api/v1/ai/sessions/{id}`、`DELETE /api/v1/ai/sessions/{id}`；`GET/PATCH /api/v1/ai/memory/settings`、`POST /api/v1/ai/memory/archive`、`GET /api/v1/ai/memory/archive-jobs/{id}`、`GET /api/v1/ai/memory/entries`、`PATCH/DELETE /api/v1/ai/memory/entries/{id}`。所有接口从认证上下文定 owner；修改保留期限、手动归档和删除须通过现有 CSRF/安全审计路径。新的研究请求接收服务端 session ID 与客户端消息幂等 ID，渐进兼容旧 `history` 字段，但不能再依赖它完成归档。

浏览器现有 localStorage 会话只能在用户选择“导入旧会话”后提交服务端；不能把已有 `ai_research_runs` 冒充完整会话。可把旧研究记录作为 `legacy_partial` 参考资料导入，保留不完整标记，不自动晋升为用户偏好。旧版前端可暂读原 API；服务端会话上线后把 localStorage 降为临时缓存，并让“删除会话”真正调用服务端删除。

## Risks / Trade-offs

- **错误归纳成投资风格** → 来源类别、跨日/跨会话门槛、`inferred` 状态、用户可见更正；交易相关约束需用户确认。
- **新会话看不到刚结束的其他会话** → 每轮更新逐日摘要；provisional daily 滞后时从当天摘要补召回，并暴露更新时间。
- **原始记录过期早于补档成功** → 期限前自动补档、降级摘要和明确缺口，仍执行 30 天硬上限。
- **文件与 MySQL 状态分叉** → 作业水位、临时写入、哈希校验、原子发布、启动修复和幂等重放。
- **记忆泄露或提示注入** → 服务端 owner 过滤、封闭路径、原文不入普通工具、来源标注、内容当数据处理、私有文件权限和备份隔离。
- **召回挤占模型上下文或偏向旧错误信息** → 片段上限、时间衰减、来源优先级、冲突展示和对市场/账户事实的实时复核。

## Migration Plan

1. 建表、建立服务端 session 和每用户目录；先双写服务端与原浏览器缓存，对所有目录三文件和 owner 隔离做负面测试。
2. 接入逐日 session 摘要、provisional daily 与只读记忆检索；先 shadow 模式评测召回，不改变现有建议。
3. 启用夜间/手动归档、短期候选、长期晋升和账户设置；补齐删除/期限/恢复测试后开放对 Agent 注入。
4. 让前端以服务端 session 为准，提供旧本地记录的显式导入；观察归档缺口和错误召回，再停用旧 `history` 作为跨会话来源。

回滚时关闭记忆工具和归档调度，保留服务端原始会话与 wiki 供导出/恢复；保留期限及用户删除请求仍由独立清理作业执行，不能因功能开关而停掉。

## Open Questions

- 首版是否给用户开放可下载的 wiki 整体导出；本规格要求可浏览和可备份，导出格式可在实施前补充。
- 现有账号是本地单 owner；未来多用户部署是否需要密钥级别的独立加密。首版先做 owner 隔离、权限与备份隔离。
- 归档模型与投研模型是否共用配置。无论选型，归档失败都必须有不编造内容的降级路径。
