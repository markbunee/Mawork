# MaWork — Personal AI Work OS

> 一个极简的个人 AI 工作操作系统：把日程、日报、记账、任务、资料等个人数据结构化，让当前最强的 AI Agent 能直接读取、分析与回写，完成**复盘 → 规划 → 执行**的闭环。
>
> 核心理念：**Agent 是可替换的，业务能力是自己的。**

## 1. 项目简介

个人工作数据（日报、日程、项目、记账、文章）往往散落在 Markdown、Excel、截图各处，无法形成可被分析的结构化历史，导致"复盘靠记忆"、AI 每次都要重建上下文。

MaWork 的做法是把这些数据结构化为 Agent 可读、可调、可执行的环境：

```
记录 → 沉淀 → 复盘 → 规划 → 执行 → 记录（飞轮）
```

四层架构：

| 层 | 职责 | 当前状态 |
|---|---|---|
| Layer 1 Data | 个人行为数据（日报 / 日程 / 记账 / 文章） | 已实现 |
| Layer 2 Knowledge | 个人知识（本地文件夹 / Markdown / PDF / Excel） | 资料库浏览已实现，索引检索待建 |
| Layer 3 Intelligence | 复盘与规划引擎 | 通过 `mawork-review` skill 实现 |
| Layer 4 Agents | 外部 Agent 执行（Pi / Codex / Claude Code） | 规划中 |

设计原则：Agent Agnostic（不绑定单一 Agent）、Capability First（业务能力优先）、Context First（执行前必给结构化上下文）、Human in the Loop（高风险写入需确认）、UI Minimal（留白、少按钮、少边框）。

## 2. 已实现功能

前端共 7 个页面，均对应后端独立模块：

| 页面 | 路由 | 功能 |
|---|---|---|
| 日历 | `/home` | 整月日历，每个日期格都是可直接输入的文本方格：回车换行、高度自适应、一键刷成任务、点方框切换完成 / 未完成；任务行自动出现在当日日报页顶部（已完成-内容 / 未完成-内容）；格内显示当日净收支 |
| 日报 | `/daily` | 入库管理（`daily.db`）：按年 / 月分组；Markdown 编辑、**失焦 / 停顿自动保存**（Ctrl+S 手动保存亦可）；支持**代码 / 预览**切换与整年 **导出**；当日「来自日历」任务顶部展示；「三、明日工作计划」自动写入**次日日历** |
| 日程 | `/planpool` | 极简 Excel 网格表（任务 / 状态 / 完成度 / 备注 / 开始 / 结束）；默认当前月；按结束日期排序；状态与完成度完全手动维护，不按日期自动流转、不配色 |
| 记账 | `/accounting` | 收支录入（类型 + 分类 + 金额 + 说明）；月度 / 年度汇总；分类占比图表；资产卡片 |
| 文章 | `/articles` | 文章列表与标题 / 正文编辑 |
| 资料库 | `/resources` | 浏览 `workspaces/` 本地文件树；Markdown 在线渲染、PDF 内嵌预览 |
| AI 报告分析 | `/analysis` | 读取 `workspaces/{year}/analysis/` 下的复盘与计划报告；在线编辑保存；支持**代码 / 预览**切换 |

日历文本行数据另存于 `planpool.db` 的 `calendar_lines` 表（详见「数据存放」）。

## 3. 技术栈

**前端**：Vue 3 + TypeScript + Vite + Vue Router + Element Plus + ECharts + markdown-it

**后端**：Python + FastAPI + uvicorn + pydantic + openpyxl

**数据**：SQLite（`accounting.db` 记账、`planpool.db` 日程任务）+ Markdown 文件。全部数据存于本地，无云端依赖。

## 4. 目录结构

```
Mawork/
├── backend/                    # FastAPI 后端
│   ├── main.py                 # 入口：挂载路由、CORS、/api/health
│   ├── config.py               # 路径与常量（workspaces 目录、两个数据库）
│   ├── db.py                   # 数据库初始化
│   ├── routers/                # 业务模块（见下）
│   ├── models/                 # 数据模型
│   ├── services/               # 业务逻辑
│   └── requirements.txt
├── frontend/                   # Vue 3 前端
│   └── src/
│       ├── views/              # 7 个页面
│       ├── components/         # 复用组件
│       ├── api/                # 后端接口封装
│       ├── router/index.ts     # 路由表
│       └── styles/main.css     # 全局样式（含 .md-body Markdown 渲染样式）
├── workspaces/                 # 全部个人数据（本地、可整体迁出）
│   ├── {year}/                 # 年份目录：Article.md、analysis/ AI 报告
│   ├── Core/                   # 年度计划与综合管理（md / pdf / xlsx）
│   ├── mawork-review/          # AI 复盘与规划 skill
│   ├── accounting.db           # 记账数据库
│   ├── planpool.db             # 日程任务 + 日历文本格
│   └── daily.db                # 日报数据库（唯一真源）
├── start.sh                    # WSL2 一键启动脚本
└── PRD_Personal_AI_Work_OS.md  # 产品需求文档
```

后端路由模块：`daily`（日报）、`ai_analysis`（分析报告读写）、`accounting`（记账）、`planpool`（日程任务）、`articles`（文章）、`resources`（资料库）。

## 5. 快速开始

### 方式一：一键脚本（推荐，WSL2）

```bash
cd /mnt/d/Desktop/Project_Group/Mawork
./start.sh
```

脚本会自动激活 conda 环境、加载 Node、释放被占用的端口、启动前后端。

启动参数集中在 `start.sh` 顶部配置区，按需修改：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CONDA_ENV` | `py312torch222` | Python 环境名 |
| `NODE_VERSION` | `v22.23.1` | Node 版本（nvm） |
| `BACKEND_PORT` | `8001` | 后端端口 |
| `FRONTEND_PORT` | `5174` | 前端端口 |

启动完成后：

- 前端 → http://localhost:5174
- 后端 → http://localhost:8001（API 文档 http://localhost:8001/docs）
- 停止 → `Ctrl + C`（脚本会自动清理子进程）

### 方式二：手动启动

后端（**必须在 `Mawork/` 目录下启动**，`backend` 作为包被导入）：

```bash
cd /mnt/d/Desktop/Project_Group/Mawork
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
```

前端（依赖由仓库根目录的 npm workspaces 统一管理）：

```bash
# 在仓库根目录 Project_Group/ 下
npm install          # 只需执行一次
npm run dev:mawork
```

或进入前端目录单独运行：

```bash
cd Mawork/frontend && npm install && npm run dev -- --port 5174
```

构建生产包：`npm run build:mawork`（仓库根目录）。

## 6. 数据存放与数据主权

所有数据以**本地 Markdown + SQLite** 存放于 `workspaces/`，无云端、无锁定，可随时整体拷贝、备份或用 Git 托管。

| 数据 | 位置 |
|---|---|
| 日报 | `workspaces/daily.db`（`daily_entries` + `daily_sections`，可按需导出 Markdown） |
| 日程任务 | `workspaces/planpool.db`（`tasks` 表） |
| 日历文本行 | `workspaces/planpool.db`（`calendar_lines`，含 daily_plan 自动任务来源） |
| 记账 | `workspaces/accounting.db` |
| 年度计划与历史复盘 | `workspaces/Core/{year}年综合管理/` |
| AI 复盘 / 计划报告 | `workspaces/{year}/analysis/` |

路径常量统一定义在 `backend/config.py`，新增数据文件请从这里取路径，不要硬编码。

## 7. AI 复盘与规划（mawork-review skill）

`workspaces/mawork-review/` 是一套面向 AI Coding Agent 的 skill，让 Agent 直接读取你的真实数据来完成复盘与规划，而不是凭印象编造。

三条工作流：

| 工作流 | 触发示例 | 产物 |
|---|---|---|
| 数据问答 | "8月干了什么""本月花了多少钱""X 任务进度" | 直接回答，附数据来源 |
| 复盘（周 / 月 / 季 / 年） | "月度复盘""季度总结" | 七步法报告 → `workspaces/{year}/analysis/{周期}/` |
| 计划与预测 | "下月计划""年度计划""预测一下" | 承接复盘、时间预算、预测标注 → `workspaces/{year}/analysis/计划/` |

取数脚本：统一入口 `scripts/mawork_query.py`，子命令 `daily / tasks / accounting / context / stats`（只读库）。

用法（在支持 skill 的 Agent 中直接说，例如）：

```
@mawork-review 帮我做 2026 年 9 月的月度复盘，报告存到 workspaces/2026/analysis/月度复盘/
```

生成的报告可在前端「AI 报告分析」页面查看与二次编辑。

## 8. 路线图

依据 `PRD_Personal_AI_Work_OS.md` 的分期规划，当前已完成 P0 阶段主体（工作台骨架、日报、日程任务、记账、文章、资料库、报告读写）：

- **Phase 2 知识层**：多源接入（PDF / Excel / URL）与 SQLite FTS5 索引；基于知识库 + 业务数据的 Ask 问答（答案附引用来源）
- **Phase 3 智能层**：Review Engine 复盘引擎、目标与 JD 能力对标分析、Planning Engine（年度 → 季度 → 月度 → 周层级计划生成）
- **Phase 4 Agent 层**：Agent Gateway（统一 Capability Protocol，适配 Pi / Codex / Claude Code）、权限分级与审计、Pixel Pony 桌宠

明确不做：多用户协作与云端同步、自研 Agent Runtime、移动端 App、向量数据库（数据量触顶后再评估）。

## 9. 开发约定

- **后端加模块**：在 `backend/routers/` 新建路由文件，然后在 `backend/main.py` 用 `app.include_router(...)` 挂载。
- **前端加页面**：在 `frontend/src/views/` 新建 View → 在 `frontend/src/router/index.ts` 注册路由 → 在 `App.vue` 侧边栏加入口。
- **路径与常量**：统一走 `backend/config.py`（`BASE_DIR`、`WORKSPACES_DIR`、`ACCOUNTING_DB`、`PLANPOOL_DB`）。
- **Markdown 渲染**：复用全局 `.md-body` 样式与 `markdown-it`（配置 `{ html: false, linkify: true }`），新增预览区直接套用，无需另写样式。
- **接口联调**：后端启动后访问 http://localhost:8001/docs 查看自动生成的 API 文档。

## 10. 相关文档

- `PRD_Personal_AI_Work_OS.md` — 完整产品需求文档（问题陈述、用户故事、MoSCoW 优先级、三大协议设计、成功指标与风险）
