# PRD：MaWork — Personal AI Work OS（个人 AI 工作操作系统）

| 项目 | 内容 |
|---|---|
| 文档版本 | v1.0（草案） |
| 撰写日期 | 2026-08-27 |
| 产品阶段 | 0 → 1（MVP 前） |
| 目标发布 | Phase 1 MVP：6 周内自用可用 |
| 产品负责人 | 本人（独立开发 + AI Coding Agent 协作） |

---

## 1. 问题陈述（Problem Statement）

个人知识工作者（产品经理 / 独立开发者 / 超级个体）的工作数据——日程、日报、项目、文章、记账——散落在 Markdown、Excel、截图等各个角落，无法形成可被分析的结构化历史；导致：

1. **复盘靠记忆**：无法回答"我过去三个月为什么总完不成计划"这类问题，AI 直接生成答案只会胡说。
2. **AI 工具互为孤岛**：Claude Code / Codex / WorkBuddy / Pi 等强 Agent 各自为战，都不了解"我过去一年做了什么"，每次都要重建上下文。
3. **行业级痛点**：每个业务产品做 AI 都在重复造 Agent（Prompt / Memory / Tools / 权限 / UI），而 Agent 能力本身又在快速迭代，绑定单家即落后。

**不解决的代价**：个人侧——计划完成率持续偏低、职业成长（对标 JD）缺乏数据支撑；产品侧——错过"Agent-ready 业务能力层"这一新兴生态位。

**核心假设（本 PRD 最需要验证的一条）**：
> 把个人真实工作数据结构化为 Agent 可读、可调、可执行的环境后，现有最强 Agent（无需自研）即可完成高质量的复盘、规划与执行闭环。

## 2. 产品定位

> **一个极简的 Personal Work OS：把个人数据、知识和目标结构化为 Agent 可理解、可调用、可执行的能力，让用户直接利用现有最强 Agent 完成复盘、规划与实际工作，而不必为每个业务场景重新构建 Agent。**

一句话架构：

```
记录 → 沉淀 → 复盘 → 规划 → 执行（外部 Agent）→ 记录（飞轮）
```

四层模型：

| 层 | 职责 | 说明 |
|---|---|---|
| Layer 1 Data | 个人行为数据 | TimeTable / Daily / Project / Articles / Keyword / Accounting |
| Layer 2 Knowledge | 个人知识 | 本地文件夹 / Markdown / PDF / Excel / URL / 外接知识库 |
| Layer 3 Intelligence | 复盘与规划 | Review Engine / Goals & JD 分析 / Planning Engine |
| Layer 4 Agents | 执行 | Agent Gateway → Pi / Codex / WorkBuddy / Claude Code |

**Agent 是可替换的，业务能力是自己的。** 系统不绑定单一 Agent；Agent 越强，产品越强。

## 3. 目标（Goals）

| # | 目标 | 衡量方式 |
|---|---|---|
| G1 | 日常工作 100% 数字化沉淀 | 日报、日程、记账均写入系统，连续 30 天不断档 |
| G2 | 数据主权 | 全部数据以本地 Markdown / SQLite 存储，可随时整体迁出，无锁定 |
| G3 | 跑通 Agent 闭环（核心假设验证） | Pi 通过 Agent Gateway 读取 Context Pack → 调用业务能力 → 写回数据 → 返回结果，全链路 1 次成功 |
| G4 | 高频自用 | 周活跃 ≥ 5 天，日均打开 ≥ 3 次 |
| G5 | 复盘提速 | 生成一份有数据支撑的月度复盘报告 ≤ 5 分钟（含人工确认） |

## 4. 非目标（Non-Goals）

| 非目标 | 排除理由 |
|---|---|
| 多用户 / 协作 / 云端同步 | V1 是个人单机产品，云端引入鉴权与隐私复杂度，无收益 |
| 自研 Agent Runtime | 与核心战略相悖——产品是"Agent 的最佳业务环境"，不是"又一个 Agent" |
| 移动端 App | 网页端优先；移动端不改变核心假设验证 |
| 向量数据库 / 复杂 RAG 基础设施 | SQLite + FTS5 起步即可支撑个人数据量，先验证再升级 |
| 通用笔记 / 知识库编辑器（对标语雀） | 编辑器只是数据入口，不是产品价值核心，避免陷入红海 |
| 内置大模型聊天入口（chat-first UI） | AI 应"无处不在但不打扰"，不做 What can I help you with 式首页 |

## 5. 用户画像与用户故事

### 5.1 用户画像

- **P1 记录者（主用户，即本人）**：每天产生日程、日报、记账、项目进展的知识工作者，要求录入极快、保存即落盘。
- **P2 求职者**：有明确目标 JD（如 AI Product Manager），需要用历史数据证明能力并找出 Gap。
- **P3 Agent（机器用户，一等公民）**：Pi / Codex / WorkBuddy / Claude Code，通过 Capability Protocol 消费本系统。**把 Agent 当作用户来设计，是本产品与传统 PRD 最大的差异。**

### 5.2 用户故事

**数据层（P1 记录者）**
- US-01：作为记录者，我想打开网页就能以 Markdown 在线编辑并 Ctrl+S 保存，数据即时写回本地文件，这样我不需要学习任何新工具。
- US-02：作为记录者，我想按月浏览全年日历（左右切换月份），格子显示日期并写入当日记录，这样我能直观看到时间分布。
- US-03：作为记录者，我想用表格视图（一个月一个子表，Excel 格式）查看同一份数据，这样便于批量整理与对齐。
- US-04：作为记录者，我想每天写一篇日报（Markdown 存储、自动加载），这样复盘时有原始事实。
- US-05：作为记录者，我想加载 Project 文件夹中的年度计划 Markdown，这样计划与执行在同一系统。
- US-06：作为记录者，我想存放和浏览大量文章，并直接加载 Keyword 文件夹，这样资料有统一入口。
- US-07：作为记录者，我想记账时只选大类 + 填一句说明，并看到月度 / 年度收支与大类占比，这样记账摩擦最小。
- US-08：作为记录者，我想通过 SQL 查询数据并导出为 Markdown，这样任何分析都不受预设视图限制。

**知识层（P1/P2）**
- US-09：作为记录者，我想把本地文件夹 / PDF / URL / 已有知识库接入系统并建立统一索引，这样提问时系统能检索真实资料而非编造。
- US-10：作为求职者，我想用自然语言向系统提问"我过去三个月为什么总完不成计划"，得到基于日报 + 日历 + 项目 + 历史计划的量化答案。

**智能层（P2 求职者）**
- US-11：作为求职者，我想粘贴目标 JD，系统抽取技能要求并与我的历史数据做证据匹配，输出能力匹配度与 Gap 清单。
- US-12：作为求职者，我想让系统把 Gap 自动转化为下季度 / 下月计划草案，经我确认后写入 Project 与 TimeTable。

**Agent 层（P3 Agent + P1）**
- US-13：作为 Agent，我想通过统一的 Capability Protocol（calendar.create / project.update / knowledge.search 等）读写本系统，这样我不需要了解前端实现。
- US-14：作为 Agent，我想在执行任务前获得一份结构化 Context Pack（目标 / 项目 / 近期工作 / 日历 / 知识 / JD / 历史完成率），这样我不必到处找数据。
- US-15：作为记录者，我想让系统把"制定下月计划"这类任务派发给 Pi / Codex / WorkBuddy 中的一家执行，结果回写系统，这样我复用最强 Agent 而不用自己干。
- US-16：作为记录者，我想在高风险写入（修改计划、删除数据）前收到确认提示（Human-in-the-Loop），这样 Agent 不会误伤我的数据。

**体验层**
- US-17：作为记录者，我想要一个像素小马桌宠，点击后给出基于真实数据的主动建议（如"3 个计划连续延期，要不要重排下周？"），这样 AI 有温度地主动出现。
- US-18：作为记录者，我想在极简首页一眼看到：当前目标进度、今日安排、一条 AI Insight，没有多余按钮和边框。

## 6. 功能需求（按 MoSCoW / P0-P2 分级）

### P0 — Phase 1 MVP（没有它产品不成立）

**M1 工作台骨架**
- 指定根文件夹启动加载；目录即导航。
- 极简 Web UI（Vue + FastAPI + SQLite）；留白、少颜色、少按钮、少边框。
- Markdown 在线编辑器：保存按钮与 Ctrl+S 均触发写回源文件（双向同步，外部改动可感知）。
- 验收：Given 编辑某 .md 文件，When Ctrl+S，Then 磁盘文件内容在 1s 内更新且无冲突提示；Given 外部修改文件，When 切回页面，Then 显示最新内容。

**M2 TimeTable（日历 + 表格双视图）**
- `2026_TimeTable/` 文件夹：日历视图按月渲染全年，左右切换月份，格子含日期并可写入记录（Markdown 存储）；表格视图一个月一个子表（Excel 存储），与日历视图关联同一数据源。
- 验收：12 个月均可切换；同一记录在两个视图数据一致。

**M3 Daily 日报**
- 按日期存储的 Markdown，自动按天加载、新建、检索。

**M4 Project 年度计划**
- 加载 Project 文件夹内年度计划 Markdown，支持编辑与进度标注。

**M5 Articles / Keyword**
- Articles 文件夹：大量文章的加载、列表、阅读；Keyword 文件夹：Markdown 直接加载展示。

**M6 Accounting 记账**
- 记一笔 = 选大类 + 输入说明（+金额）；月度 / 年度收入支出汇总；各大类占比可视化（涨红跌绿不适用，此处用中性色系）。
- 验收：Given 录入一笔支出，When 打开月度报表，Then 汇总与占比即时更新。

**M7 SQL → Markdown 导出**
- 内置 SQL 控制台查询 SQLite，结果一键导出 Markdown 表格。

**M8 Agent 闭环技术验证（Spike，与 M1-M7 并行）**
- 薄适配层：`FastAPI → Pi Adapter → pi --mode rpc`，验证"Agent 读取 Context → 调用能力 → 修改数据 → 返回结果"完整闭环一次跑通。
- 验收：Pi 基于 Context Pack 生成一份结构化周报草案并写回系统（或输出为文件），全程无人工拼上下文。

### P1 — Phase 2（知识层）

**M9 Knowledge 多源接入与索引**
- 知识源：本地文件夹 / Markdown / PDF / Excel / URL / 已有知识库连接器。
- Pipeline：Parser → Chunking → SQLite FTS5 索引（先不做向量库）。
- 业务数据（Operational Data）与知识（Knowledge）严格分库分目录。

**M10 Ask（RAG 问答）**
- 基于知识库 + 业务数据的检索问答；答案附引用来源。
- 验收：Given 提问"过去三个月计划完成情况"，Then 回答包含真实统计数字（计划数 / 完成 / 延期 / 取消）而非泛泛而谈。

**M11 Dashboard 与 AI Insight**
- 极简首页：当前目标进度条、今日事项、单条 AI Insight；各模块内嵌 ✨ 轻量 AI 入口（如日历页提示"过去 4 周同类任务平均耗时 2h，是否调整下午安排"）。

### P2 — Phase 3（智能层）

**M12 Review Engine 复盘引擎**
- Context Builder 汇聚 Daily + TimeTable + Project + Articles + 目标 + 历史计划，交由 Agent 生成结构化复盘（summary / achievements / problems / patterns / risks / recommendations），人工确认后存档。

**M13 Goals & JD 分析**
- JD 技能抽取 → 历史数据证据匹配 → 能力匹配度评分 → Gap 清单 → **Gap 自动转化为计划**（写入 Project / TimeTable）。

**M14 Planning Engine**
- 年度 → 季度 → 月度 → 周计划的层级化生成；输入 = 历史事实 + 知识库 + 目标 + 外部要求 + 时间约束 + 历史完成率；输出为 Plan Proposal，经 Human Review 后 Apply。

### P2 — Phase 4（Agent 层）

**M15 Agent Gateway（完整版）**
- AgentProvider 统一接口：capabilities / create_task / send_context / execute / stream / cancel / get_result。
- Pi Adapter（RPC）、WorkBuddy Adapter、Codex Adapter（CLI/API）；统一任务协议（goal / context / inputs / constraints / expected_output / permissions）。
- 权限分级与审计日志：所有 Agent 写操作留痕，高风险操作需人工确认。

**M16 Pixel Pony 桌宠**
- 桌面像素小马，点击弹出基于真实数据的主动建议（"要不要我帮你重排下周？"），一键派发 Agent。

### P3 — 明确不做 / 远期
- 多端同步、团队协作、商业化开放平台、自研 Agent、向量库（预留接口，数据量触顶再上）。

## 7. 三大协议（架构级需求，写入代码层约束）

1. **Data Protocol**：定义 Goal / Project / Task / Daily / Calendar / Knowledge / Transaction 的数据结构与存储约定（Markdown + SQLite 双轨）。
2. **Capability Protocol**：业务能力以动词命名暴露给 Agent——`calendar.list/create/update/delete`、`project.list/get/create/update/archive`、`daily.get/create/update/search`、`knowledge.search/get/sources`、`goal.list/get/create/update`、`accounting.summary/list/create`、`plan.apply`。
3. **Agent Protocol**：Context → Tool Discovery → Tool Call → Result → Next Action 的交互约定，含 Context Pack 规范与权限模型。

## 8. 产品设计原则

**Agent-Native Product Principles**
1. Agent Agnostic — 不绑定单一 Agent。
2. Capability First — 业务能力优先于 Agent。
3. Context First — Agent 执行前必获得结构化 Context（Context Pack）。
4. Human in the Loop — 高风险写入必须可确认。
5. Agent Replaceable — 替换 Agent 不改业务逻辑（Adapter / 防腐层）。
6. Open by Default — 优先 CLI / RPC / HTTP 等开放接入。
7. UI Minimal — 用户无需理解 Agent 内部机制。

**极简 UI 原则**：留白、少颜色、少按钮、少边框；AI 不是大入口而是"无处不在但不打扰"（✨ 式轻交互）；首页安静克制（Today / 3 things / 一条 Insight / 右下角 🐴）。

## 9. 成功指标

**先行指标（上线后 1-4 周）**
| 指标 | 目标 | 测量方式 |
|---|---|---|
| 数据沉淀率 | 连续 30 天日报不断档 | Daily 表记录数 |
| 编辑器保存成功率 | ≥ 99%，冲突率 ≤ 1% | 保存接口日志 |
| Agent 闭环成功率（Spike 后） | 单次任务端到端成功 ≥ 80% | Gateway 任务日志 |
| 周活跃天数 | ≥ 5 天 | 本地访问日志 |

**滞后指标（1-3 个月）**
| 指标 | 目标 |
|---|---|
| 个人计划完成率 | 基线（现状约 68%）→ +10pp |
| 月度复盘报告生成时间 | ≤ 5 分钟 |
| Ask 问答引用真实数据比例 | ≥ 90% 回答含可溯源引用 |
| Gap→计划转化 | 至少 1 次完整 JD 对标并产出季度计划 |

## 10. 风险与开放问题

| # | 开放问题 | 需要谁回答 | 阻塞性 |
|---|---|---|---|
| Q1 | Pi RPC 的 stdin/stdout JSON-RPC 在 Windows 下的稳定性与长会话保持 | 工程验证 | 阻塞 M8 Spike |
| Q2 | Markdown（人类可读）与 SQLite（机器可查）双轨的一致性策略：以谁为准、何时同步 | 架构决策 | 阻塞 M1 |
| Q3 | WorkBuddy / Codex 的接入方式与权限边界（Connector vs CLI） | 调研 | 非阻塞 |
| Q4 | Excel 子表与日历视图同源数据的双向绑定实现方案 | 工程 | 非阻塞 |
| Q5 | 复盘结论的准确性评估标准（如何避免 AI 统计幻觉：先 SQL 后 LLM） | 产品+工程 | 非阻塞 |

**主要风险**：① Agent 闭环假设不成立（缓解：M8 提前至 Phase 1 并行验证，失败则产品退化为纯工作台，仍可用）；② 范围蔓延做成大而全笔记软件（缓解：非目标清单 + 每 PR 必须对应本 PRD 条目）；③ 单人开发带宽（缓解：能力分层，Phase 1 全部为成熟技术栈）。

## 11. 时间线考虑

- 无硬性外部截止日期；以"自用可用"为唯一上线标准。
- 关键顺序约束：**数据沉淀必须先于智能层**（Agent 再聪明，不知道你过去一年干了什么也没用）。
- 详细排期与优先级打分见配套文档《路线图优先级报告》。
