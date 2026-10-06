# MaWork 开发交接文档

> 面向接手的 AI / 开发者。本文档记录**已完成功能、待完成功能、关键约定与踩坑记录**。
> 最后更新：2026-09-21（多用户改造：账号体系 + 数据隔离 + 申请审批）
> 上一阶段工作日志：`.workbuddy/memory/2026-09-17.md`、`2026-09-18.md`、`2026-09-21.md`

---

## 0. 一句话现状

MaWork 是「个人 AI 工作操作系统」，9 个模块。已完成 **移动端视觉重构 + 样式分层重构 + 功能升级 Phase A/B/C/D**（日报 / 记账 / 日程 / **复盘中心**）。
**当前构建、类型检查、后端临时库断言、真实服务 API 联调 均通过**。
**Phase E：横切能力已全部完成**（E1 全局搜索 / E2 日程↔计时联动 / E3 模板库 / E4 提醒通知 / E5 导出备份 / E6 标签中台 / E7 目标 OKR）。
**多用户已支持**：账号体系（申请 → 管理员审批 → 登录）+ 每人独立数据空间，见 §3.7。
下一步为 **Phase F：双端体验打磨**（浏览器 / 真机逐页走查，补齐此前从未做过的目视验证）。

---

## 1. 项目概览

### 1.1 是什么

`PRD_Personal_AI_Work_OS.md`（项目根）是产品文档。9 个模块：

| 模块 | 路由 | 视图 | 说明 |
|---|---|---|---|
| 日历 | `/home` | `HomeView.vue` | 月历 + 单日详情 + 概览卡 |
| 日报 | `/daily` | `DailyView.vue` | Markdown 日记，**已升级** |
| 日程 | `/planpool` | `PlanpoolView.vue` | Excel 式任务表，**已升级** |
| 记账 | `/accounting` | `AccountingView.vue` | 收支/资产/预算，**已升级** |
| 资料 | `/resources` | `ResourcesView.vue` | 文件资料 |
| 文章 | `/articles` | `ArticlesView.vue` | 收藏文章 |
| AI 报告 | `/analysis` | `AnalysisView.vue` | **已升级为复盘中心**（概览/趋势/目标/复盘/报告库），见 Phase D |
| 计时 | `/timer` | `TimerView.vue` | 倒计时/正计时/耗时统计 |
| 习惯 | `/habit` | `HabitView.vue` | 红色主题，打卡 |

### 1.2 技术栈

- **前端**：Vue 3.5 + Vite + TypeScript + Element Plus 2.14 + ECharts 6 + markdown-it 14
- **后端**：FastAPI + SQLite（**每模块一个独立 db 文件 × 每个用户一套**）+ slowapi 限流 + JWT **多账号**鉴权
  （密码 PBKDF2-SHA256 20 万轮 + 随机盐，仅用标准库 `hashlib`，**无新增依赖**）
- **部署**：Docker Compose（`docker-compose.yml`：backend + frontend/nginx）
- **PWA**：已有 manifest / icon（`frontend/public/`）

### 1.3 后端数据文件（`backend/config.py`）

```
workspaces/
├── users.db               # 全局账号库（不属于任何用户）
└── users/u{uid}/          # 每个用户一整套独立数据
    ├── accounting.db      # 记账
    ├── planpool.db        # 日程任务 + 自定义列 + 日历文本格 + 习惯
    ├── daily.db           # 日报（唯一真源）
    ├── timer.db           # 计时
    ├── insight.db         # 目标 KPI（Dashboard 是只读跨库聚合，不落此库）
    ├── templates.db       # 模板库（E3）
    └── 2026/ 2027/ Core/ mawork-review/   # 日报 md、资料、报告库
```

> 全新部署时会自动播种首个管理员：`MAWORK_ADMIN_USER` / `MAWORK_ADMIN_PASSWORD`
> / `MAWORK_ADMIN_PHONE`（默认 `admin / mawork123`，**生产必须覆盖**）。
> 另有 `MAWORK_DATA_DIR`（换数据目录）、`MAWORK_MULTI_USER=0`（退回单用户模式）。

---

## 2. 环境与开发约定（**必读，否则会踩坑**）

### 2.1 前端依赖在 workspace 根目录 ⚠️

根 `D:\Desktop\Project_Group\package.json` 用 npm workspaces 包含 `Mawork/frontend`。
**依赖装在 `D:\Desktop\Project_Group\node_modules`，`Mawork/frontend/node_modules` 是空的。**
所以命令要在 `Mawork/frontend/` 下跑，`vite` / `vue-tsc` 从根 `.bin` 解析。

```bash
cd D:/Desktop/Project_Group/Mawork/frontend
npm run build-only     # vite build，最快的编译验证
npm run type-check     # vue-tsc --build
npm run dev            # 开发服务器
```

### 2.2 后端本地可跑（Phase D 已验证）✅

本地 Python 环境**已装 fastapi + uvicorn**，可直接起服务做 API 联调：

```bash
cd D:/Desktop/Project_Group/Mawork
MAWORK_LOG_DIR=/tmp/mawork_logs python -m uvicorn backend.main:app --host 127.0.0.1 --port 8011
curl http://127.0.0.1:8011/api/health          # -> {"ok":true}
# 需要鉴权的接口：先登录取 JWT
TOKEN=$(curl -s -X POST http://127.0.0.1:8011/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"mawork123"}' | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8011/api/insight/dashboard?from=2026-09-14&to=2026-09-20"
```

> ⚠️ 本地 `Mawork/workspaces/` **就是真实数据目录**（`workspaces.local.bak.*` 只是备份）。
> 起服务会跑一遍 `init_db` 的幂等迁移、并可能新建缺失的库文件。写操作前先确认。

**不想动真实数据的场景**，仍用临时库脚本（同时覆盖所有 db 路径，调用 service 层函数直接 print / assert）：

```python
import tempfile
from pathlib import Path
from backend import db, config

tmp = Path(tempfile.mkdtemp())
config.WORKSPACES_DIR = tmp
config.ACCOUNTING_DB = tmp / "accounting.db"
config.DB_PATH = config.ACCOUNTING_DB   # services/accounting.py 走 db.get_conn() 默认值
config.PLANPOOL_DB = tmp / "planpool.db"
config.DAILY_DB = tmp / "daily.db"
config.TIMER_DB = tmp / "timer.db"
config.INSIGHT_DB = tmp / "insight.db"

db.init_db()
# ... 调用 service 函数并 print / assert
```

多点数据时会 `import shutil; shutil.rmtree(tmp)`。
运行：`cd D:/Desktop/Project_Group/Mawork && <python> tmp_test.py`（用完 `rm` 删掉临时脚本）。
临时脚本**不要留在仓库里**。

### 2.3 FastAPI 路由声明顺序 ⚠️

**静态路径必须声明在路径参数之前**，否则会被吞掉。已踩过的坑：

- `daily.py`：`/search`、`/tags` 必须在 `/{year}` 之前
- `accounting.py`：`/budgets/status` 必须在 `/budgets/{bid}` 之前；`/recurring/apply` 同理
- `insight.py`：`/review` 是静态路径（**当前无路径参数路由，但将来加 `/goals/{gid}` 之类时，必须先声明 `/review`**）
- `user.py`：`/applications` 系列必须写在 `/{uid}` 系列之前

新增接口时务必检查。

### 2.4 CSS 分层约定（**重要，别破坏**）

引入顺序在 `frontend/src/styles/main.css`，不可随意改动：

```
tokens.css            ← 第一，全部 CSS 变量
  ↓
base.css              ← 全局重置 + 桌面布局 + 通用按钮
  ↓
<module>.css          ← 各模块：桌面规则 + 本模块的 @media ≤768px 就近维护
  ↓
mobile.css            ← 最后，移动端外壳（顶栏/胶囊 Tab/弹层）+ 跨模块基建
```

- **改配色/字号/间距/圆角/阴影 → 只动 `tokens.css`**（桌面 `:root` + 移动端 `--m-*` 令牌）
- **改某模块 → 动对应的 `<module>.css`**（含它自己的移动端块）
- **改顶栏 / 底部 Tab / 弹层 → `mobile.css`**
- 移动端断点统一 `768px`。`useIsMobile.ts` 是 JS 侧判断。

### 2.5 其他已知约定

- `habit.css` **必须在 main.css 内引入**（不要在 `main.ts` 里额外 import，否则会盖掉移动端规则——这是修过的 bug）
- 移动端输入框统一 `16px`，规避 iOS 聚焦自动缩放（`.pp-excel` / `.tm-task-table` 密集表格例外）
- 移动端页面顶层容器若桌面是 `flex` 行布局，**必须在媒体查询里改成 `flex-direction: column`**（见 2.6）

### 2.6 ⚠️ 高危坑：拆分时丢 `flex-direction: column`

样式分层重构时，脚本曾把 `.daily` / `.resources` / `.articles` 的移动端规则误写成只有 `height: auto`，
**丢掉了 `flex-direction: column; gap: 14px`** → 这三个页在手机上仍是桌面行布局，左右并排错乱。

**规则：任何移动端覆盖块，只要桌面主容器是 `flex`（行），就一定要写全 `flex-direction: column; gap; height: auto`。**
`home / accounting / habit / timer / planpool` 主容器桌面本就是 column，无此问题。

---

## 3. 已完成功能

### 3.1 基础设施：移动端视觉重构 ✅

**目标**：把「缩水的桌面布局」改造成真正的移动 App。

- `App.vue`：移动端顶栏（标题 + 日期星期 + 头像，毛玻璃 + 刘海安全区）、**悬浮胶囊 Tab 栏**（62px 高 / 36px 圆角 / 5 项：日历·日报·日程·记账·更多）、「更多」宫格弹层（资料/文章/AI报告/计时/习惯）、账户弹层（退出登录）。
- 旧 `.bottom-tab` / `.drawer-*` 组件与样式**已彻底删除**，无死代码。
- 配色：主色 `#7a4e2d`（浓缩咖啡/暖陶土），底色 `#f5f2ec`，卡片改「白底 + 柔和投影」。
- 语义色沿用项目既有约定（**不要自创**）：正向/收入绿 `#3f6b45`、负向/支出赭 `#b4553f`、习惯红 `#c0392b`。
- 移动端顶部标题**全站锁定 18px**。

**验证**：build + type-check 通过；preview 冒烟 200；产物含 `.m-tabbar-pill`，旧 `bottom-tab` 清零。
**未做**：真机 / 浏览器移动模拟逐页视觉确认。

### 3.2 基础设施：样式分层重构 ✅

- 新增 `tokens.css`（全站唯一样式变量源）
- `mobile.css` 收敛为「移动端外壳 + 跨模块基建」
- 各模块移动端规则就近迁回各自文件
- `main.css` 重写引入顺序并写明维护约定
- **修复 3 个页面（daily/resources/articles）的竖排回归**（见 2.6）

**验证**：写了全量比对脚本（旧/新整体构建产物，抽取 `@media(width<=768px)` 块逐声明 diff），确认无语义丢失。

### 3.3 Phase A：日报升级 ✅

**能力**

1. **关键词搜索**：顶部搜索框（防抖 300ms），正文 + 标题全文匹配，结果列表 `<mark>` 命中高亮，点击跳转日期
2. **标签系统**：`#标签` 从后端按年聚合，chips 点选过滤日期树
3. **完整 Markdown 编辑器**：
   - 工具栏：标题 / 加粗 / 斜体 / 列表 / 待办 / 引用 / 代码 / 链接 / 分割线 / 表格（选区包裹或行前缀切换）
   - **桌面端左写右预览分屏实时渲染**；手机端「编辑 / 预览」切换
4. **元信息**：字号统计 + 连续写作天数（streak）+ 当前标签
5. **模板**：日报三段式 / 周报（套用前 confirm 防覆盖）

**改动文件**

| 层 | 文件 | 内容 |
|---|---|---|
| 后端 | `backend/services/daily.py` | `search_daily(year, q)`（LIKE + 上下文片段 `_make_snippet`）、`list_tags(year)` |
| 后端 | `backend/routers/daily.py` | `GET /api/daily/search`、`GET /api/daily/tags`（**声明在 `/{year}` 之前**） |
| 前端 | `src/api/daily.ts` | `searchDaily` / `listTags` / `DailySearchResult` |
| 前端 | `src/views/DailyView.vue` | 重写（659 行） |
| 前端 | `src/styles/daily.css` | 搜索/标签/工具栏/分屏/元信息 + 移动端响应式 |

> 注意：原移动端顶部只读预览已移除（与编辑器自带预览重复），手机上统一走「写日报 FAB → 弹层」。

### 3.4 Phase B：记账科学化 ✅

**能力（全部向后兼容，旧数据不丢）**

1. **多级分类**：一级 + 二级分类树（`CATEGORY_TREE`）。支出：餐饮→午饭/晚饭/聚餐…、交通→公交地铁/打车/加油…、居住/购物/学习/医疗/娱乐/人情/其他；收入：职业/投资/项目/其他 + 下挂子类。录入表单「类型 → 一级 → 二级」级联。
2. **多账户资产负债**：`accounts` 表取代旧的 `deposit/saving` 两个数字。可建任意账户（现金/银行卡/支付宝/微信/其他）。净资产 = 账户合计 + 累计净收入 − 未收回垫付。
3. **预算 + 超支预警**：月度总预算 + 分类预算，进度条 + 百分比，超支时顶部红色预警条。
4. **周期账**：模板（类型/分类/金额/每月几号）+「生成本月」批量生成，**幂等**（同月不重复）。

**改动文件**

| 层 | 文件 | 内容 |
|---|---|---|
| 后端 | `models/accounting.py` | `CATEGORY_TREE`、`accounts` / `budgets` / `recurring` 表、`transactions.category2` |
| 后端 | `services/accounting.py` | 账户 CRUD、`accounts_total`、`balance()` 改聚合、`budget_status`、预算 CRUD、周期账 CRUD + `apply_recurring` |
| 后端 | `routers/accounting.py` | `/accounts` `/budgets` `/budgets/status` `/recurring` `/recurring/apply`；`/meta` 返回级联映射 |
| 后端 | `db.py` | `_migrate_accounting` 幂等迁移：加 `category2` 列；`deposit/saving` → 账户 |
| 前端 | `src/api/accounting.ts` | Account / Budget / Recurring 类型与接口 |
| 前端 | `components/accounting/TransactionForm.vue` | 二级分类级联 |
| 前端 | `components/accounting/TransactionList.vue` | 显示二级标签 |
| 前端 | `views/AccountingView.vue` | 重写（498 行）：资产表 / 预算面板 / 周期账面板 |
| 前端 | `styles/accounting.css` | 新面板样式 + 移动端响应式 |

**⚠️ 已知简化**：账户模型是「期初余额快照 + 流水算净资产」，**单笔交易未关联到具体账户扣减**。若需「每笔支出自动从某账户扣」，要再加一层账户流水。

### 3.5 Phase C：日程 Excel 表打磨 ✅

**能力**

1. **灵活列模型**：列可自由**增 / 删 / 重排 / 改名 / 改类型 / 显隐**
   - 列类型（`ColumnType`）：`text` / `date` / `number` / `select` / `check`
   - 内置 7 列（`level1/title/progress/completion/note/start_date/end_date`）存在 `tasks` 表；**自定义列走 EAV**（`task_cells` 表，`{col_key: value}`），内置 key 自动忽略
2. **多视图**：表格 / 看板（按状态分组）/ 日历 三视图切换
3. **筛选 + 排序 + 分组**：关键词（含自定义字段）、状态、一级计划筛选；点列头排序（升降序切换）；按一级计划分组折叠
4. **预设列模板**：内置「标准计划表 / 项目跟踪 / 周计划」，一键套用
5. **保留**：Excel 列标（A/B/C…）、内联编辑、自动保存、xlsx 导出（已纳入自定义列）

**改动文件**

| 层 | 文件 | 内容 |
|---|---|---|
| 后端 | `models/planpool.py` | `task_columns` / `task_cells` / `task_templates` 三张表 |
| 后端 | `services/planpool.py` | 默认列种子、列 CRUD、`set_columns_order`、`upsert_cells`、模板列表/套用；`list_tasks` 合并 `fields`；`export_excel` 动态列 |
| 后端 | `routers/planpool.py` | `/columns`(GET/POST)、`/columns/order`、`/columns/{cid}`(PUT/DELETE)、`/tasks/{tid}/cells`、`/templates`、`/templates/apply` |
| 后端 | `db.py` | `_migrate_planpool` 内初始化列种子与模板 |
| 前端 | `src/api/planpool.ts` | `Column` / `ColumnType` / `Template` 类型与接口 |
| 前端 | `components/planpool/TaskTable.vue` | 重写为动态表格（17111 字节） |
| 前端 | `components/planpool/TaskBoard.vue` | **新增**，看板视图 |
| 前端 | `components/planpool/TaskCalendar.vue` | **新增**，日历视图 |
| 前端 | `components/planpool/ColumnManager.vue` | **新增**，列管理抽屉 |
| 前端 | `views/PlanpoolView.vue` | 重写（182 行），整合全部能力 |
| 前端 | `styles/planpool.css` | 新增看板/日历/筛选/列管理样式 + 移动端响应式 |

**本次收尾修复**：`TaskTable.vue:287` 残留类型错误 —— `c.ftype !== 'note'` 改为 `c.key !== 'note'`
（`ColumnType` 不含 `'note'`，应为判断内置列 key）。修完 build + type-check 全绿。

**验证**：临时库跑通默认列种子 / 增列 / 显隐 / 重排 / 自定义单元格读写 / 内置列忽略 / 模板套用 / xlsx 导出；前端 build + type-check 通过。

---

### 3.6 Phase D：复盘中心（量化 + 质化 + 复盘闭环）✅

**核心决策**：新增后端 `insight` 模块做**跨库只读聚合**（`/api/insight/dashboard?from&to` 一次返回全部指标），
而不是让前端去拉全年日报正文再本地算。

**能力**

1. **时间维度切换**：今日 / 本周 / 本月 / 本季 / 本年 预设 + 自定义起止日期 + 前后翻页
2. **量化卡（6 张）**：收支结余、专注时长、任务完成率、习惯达标率、日报篇数（含连续天数）、复盘完成度
   —— 每张卡带**环比**涨跌角标（后端多取一份「上一等长区间」做基准）
3. **质化卡（6 块）**：主题标签（按频次权重排版）、支出结构、习惯达标、专注 Top、预算与资产、写作用字与结构完整度
4. **趋势图（4 图，ECharts 6）**：收支柱 + 净额线、专注小时柱、任务完成柱 + 习惯达标率线、日报字数面积图（移动端重排）
5. **目标 KPI**：CRUD + 进度环（conic-gradient）+ 推进打卡 + 推进记录 + 归档
   —— **支持反向目标**（减重：起始值 > 目标值时自动反向算百分比）
6. **自动复盘**：周 / 月 / 季 / 年四种范围，用真实数据生成 Markdown（总览表 + 分模块明细 + 5 条提问引导），
   可编辑后**一键保存到报告库**（复用既有 `/api/analysis` 的 md 文件存储）
7. **`AnalysisView` 升级**：从「文档管理」→「复盘中心」（概览 / 趋势 / 目标 / 复盘 / 报告库 5 Tab）
8. **HomeView 联动**：日历上方新增「本周概览」条 + 「复盘中心 →」入口

**改动文件**

| 层 | 文件 | 内容 |
|---|---|---|
| 后端 | `config.py` | 新增 `INSIGHT_DB = workspaces/insight.db` |
| 后端 | `models/insight.py` **新增** | `goals` / `goal_logs` 建表 SQL |
| 后端 | `services/insight.py` **新增** | `dashboard`（跨库聚合 6 块）、目标 CRUD + `checkin_goal`（含反向进度）、`review(scope, anchor)`、`_range_of` |
| 后端 | `routers/insight.py` **新增** | `/dashboard`、`/goals`(CRUD)、`/goals/{gid}/checkin`、`/goals/{gid}/logs`、`/review` |
| 后端 | `db.py` | `init_db` 增加 insight 库初始化 |
| 后端 | `main.py` | `insight.router` 加入受保护路由列表 |
| 后端 | `models/accounting.py` | **修复阻断 bug**：补回缺失的 `REIMBURSE_STATUSES`（见下方「已知问题」） |
| 前端 | `src/api/insight.ts` **新增** | Dashboard / Goal / ReviewResult 类型 + 接口 + `fmtSec` / `fmtMoney` |
| 前端 | `src/utils/dateRange.ts` **新增** | `RangePreset`、`computeRange`、`previousRange`、`shiftAnchor`、`eachDay`（复盘中心与首页共用） |
| 前端 | `src/views/AnalysisView.vue` | 重写为复盘中心容器（时间维度条 + 5 Tab） |
| 前端 | `components/analysis/OverviewTab.vue` **新增** | 量化卡 + 质化面板 |
| 前端 | `components/analysis/TrendTab.vue` **新增** | 4 张 ECharts 趋势图 |
| 前端 | `components/analysis/GoalsPanel.vue` **新增** | 目标 CRUD / 推进 / 进度环 |
| 前端 | `components/analysis/ReviewPanel.vue` **新增** | 自动复盘生成 → 编辑 → 存库 |
| 前端 | `components/analysis/ReportTree.vue` **新增** | 原「文档管理」逻辑抽出（文件树 + md 编辑/预览） |
| 前端 | `src/styles/analysis.css` **新增** | 桌面 + `@media ≤768px` 就近维护；已在 `main.css` 引入 |
| 前端 | `src/views/HomeView.vue` + `styles/home.css` | 新增「本周概览」条 + 复盘中心入口 |
| 前端 | `src/views/App.vue` | `/analysis` 导航项更名：name `统计` / title `复盘中心` / icon `📊`（path 不变） |

**⚠️ 顺手修掉的阻断性既有 bug**：`routers/accounting.py` 引用了 `models/accounting.py` 里**不存在的
`REIMBURSE_STATUSES`**，导致 `import backend.main` 直接 ImportError、**后端根本起不来**（Phase B 迁移遗留，
报销事件化后交易自身不再有「已报销」分类）。已在 models 补 `REIMBURSE_STATUSES = ["待报销"]`。

**数据口径备忘**（改这块前先看）

- `transactions.amount` 存的是**分**，读出统一过 `_cents_to_yuan`
- 任务归属区间：`end_date` → `start_date` → `created_at[:10]`（无完成日期字段，用结束日期做代理）
- 习惯达标：复用 `habit.expected_on` 按频率算应打卡天数
- 复盘完成度 = 三段（今日工作 / 问题反馈 / 明日计划）齐全的日报占比
- 预算只在「单一自然月区间」返回，跨月区间为 `null`

**已知简化**

- 目标 KPI 是「目标 + 手动推进」，**没有自动从其它模块同步**（如「存钱」不会自动读记账余额）。要自动联动需再加 goal_source 配置。
- 「同比」工具函数 `yearAgoRange` 已备好，但 UI 目前只用了「环比」，没做同比面板。

---

---

### 3.7 多用户改造（账号体系 + 数据隔离 + 申请审批）✅

**核心机制：`config` 动态库路径 + 请求级用户上下文**

各 service 里写死的 `config.ACCOUNTING_DB` **一行都没改**，靠两件事自动按用户分流：

1. `backend/ctx.py`：`ContextVar` 存当前用户 id（零依赖，避免循环导入）；
2. `backend/config.py` 的 PEP 562 `__getattr__`：6 个 `*_DB` + `USERS_DB` + `USERS_DIR`
   全部**运行时**解析 → `config.ACCOUNTING_DB` 自动变成
   `workspaces/users/u{uid}/accounting.db`。
3. `auth.require_auth` **必须写成 `async def`**！同步依赖会被 FastAPI 丢进线程池执行，
   线程池用 `copy_context`，里面设置的 ContextVar 传不回请求上下文（踩过才知道）。
   写成 async 后设置的用户 id 会被后续代码继承，含线程池里的同步端点。

**账号与权限规则（按需求落地）**

| 事项 | 实现 |
|---|---|
| 成员申请 | 登录页「申请账号」提交 **用户名 + 手机号 + 密码**（无需登录，按 IP 限流 5/分钟） |
| 审批 | 管理员在「用户管理」通过后**才真正建号**；审批前不产生任何账号 |
| 重置密码 | 途径一：同用户名 + **同手机号**再次提交申请 → 判定为 `kind='reset'`，管理员通过后密码更新（手机号不符直接拒绝，防冒改） |
| | 途径二：管理员「重置密码」→ 生成 12 位临时密码，**明文只在本次响应出现一次**，不落库不写日志 |
| 密码可见性 | 任何接口返回的账号信息都剔除 `pwd_hash` / `salt`（`_public()` 统一过滤），管理员也看不到 |
| 删除用户 | 账号行 + 该用户整个数据目录一并清除；不能删自己、不能删最后一个管理员 |
| 停用 | `status=disabled` 后令牌即刻失效，数据保留 |
| 数据隔离 | 每人一整套 db + 文件目录，互不可见；备份/导出/搜索/标签也只覆盖自己的空间 |

**改动文件**

| 层 | 文件 | 内容 |
|---|---|---|
| 后端 | `ctx.py` **新增** | 用户上下文 ContextVar |
| 后端 | `config.py` | `data_dir()` / `db_path()` / `user_dir()` / `__getattr__` 动态路径；`USERS_DB`、`MAWORK_MULTI_USER`、`MAWORK_DATA_DIR`、`ADMIN_PHONE` |
| 后端 | `scope.py` **新增** | `ensure_user_storage`（建目录+建表+`.inited` 标记）、`delete_user_storage`、`in_user` 上下文管理器 |
| 后端 | `models/user.py` **新增** | `users` / `user_applications` / `user_meta` 建表；用户名/手机号/密码规则常量 |
| 后端 | `services/user.py` **新增** | PBKDF2 哈希与校验、申请/审批、重置密码、建号/停用/改角色/删除、`ensure_admin_seeded` |
| 后端 | `routers/user.py` **新增** | `/api/user/*`（管理员）：申请列表 / 通过 / 驳回、成员列表、直接建号、重置密码、停用、改角色、删除 |
| 后端 | `routers/auth.py` | login 走多账号（返回 uid/role）、`/me`、`/apply` 成员申请 |
| 后端 | `auth.py` | token 载荷加 uid/role；`require_auth`(async) + `require_admin` |
| 后端 | `db.py` | `init_db()` 拆为 `init_global()`(users.db) + `init_user(uid)` + `init_current()`；启动时**遍历所有用户**跑一遍，保证 schema 升级对所有人生效 |
| 后端 | 文件型路径 | `resources.py` 的 `ROOT` 常量改 `_root()` 函数；`ai_analysis.py`、`articles.py`、`daily.py`、`search.py`、`tag.py` 的 `WORKSPACES_DIR` → `data_dir()`；`backup.py` 的 `init_db()` → `init_current()` |
| 后端 | `main.py` | 注册 `user.router` |
| 运维 | `scripts/migrate_multiuser.py` **新增（独立脚本，不入系统代码）** | 见下方「存量数据迁移」 |
| 前端 | `api/user.ts` **新增** | 用户管理接口与类型 |
| 前端 | `api/auth.ts` / `utils/auth.ts` | login 保存 uid/role；新增 `applyMember`；`isAdmin()` |
| 前端 | `views/LoginView.vue` | 新增「申请账号 / 重置密码」模式（用户名 + 手机号 + 新密码） |
| 前端 | `views/UserManageView.vue` **新增** | 申请审批 + 成员列表 + 直接建号 + 重置密码 + 停用/改角色/删除 |
| 前端 | `router/index.ts` | 新增 `/users`（不进侧边栏与胶囊 Tab） |
| 前端 | `App.vue` | 账户弹层显示「管理员/成员」；**管理员才显示「用户管理」入口**（桌面顶栏 + 手机账户弹层） |
| 前端 | `styles/user.css` **新增** + `base.css` + `login.css` | 管理页样式（含移动端）、顶栏入口、登录页模式切换 |

**存量数据迁移（一次性，务必先停服务）**

```bash
cd Mawork
MAWORK_ADMIN_USER=admin MAWORK_ADMIN_PASSWORD=强密码 MAWORK_ADMIN_PHONE=138xxxxxxxx \
  python scripts/migrate_multiuser.py            # 先 --dry-run 演练，再去掉该参数实跑
```

流程：① 整包备份到 `Mawork/backups/*.zip` → ② 建/复用管理员作为数据归属人
→ ③ 把根目录的业务库与文件搬进 `workspaces/users/u{uid}/` → ④ 跑一次建表迁移并写标记。

- **幂等**：已打 `migrated_from_single` 标记即跳过；判定不只看「有没有账号」——
  若服务在迁移前启动过会播种出管理员 + 空库，此时根目录仍有旧库 → 仍判定为未迁移（已处理）。
- **回滚**：删掉 `workspaces/users/` 与 `workspaces/users.db`，把备份 zip 解开覆盖回去。

**验证**：临时库跑通 11 组断言（初始化/登录/申请→建号/数据隔离/改密/防抢注/重置密码/停用/删号清数据/管理员保护/入参校验）；
迁移脚本在假数据目录上端到端跑通并确认二次运行跳过。

**已知简化**

- 用户之间**不共享任何数据**，也没做跨用户汇总报表。
- 没有邮箱/短信验证，手机号仅作改密校验凭证（规则：6–20 位数字/+-()）。
- 令牌 12 小时有效；停用/删号后旧令牌最长 12 小时内仍可通过校验（除非重启改密钥）。

---

## 4. 待完成功能

### 4.1 Phase E：横切能力 ✅ **已全部完成（E1–E7）**

多数**需要后端**：

1. ~~**全局搜索**：跨日报 / 资料 / 文章 / 记账备注 / 任务一处搜~~ ✅ **已实现**（后端 `services/search.py` + `routers/search.py`；前端顶栏 / 移动端搜索弹层，支持 `Ctrl/⌘+K`，结果按模块分组跳转；日报/文章/资料支持精确深链）
2. ~~**标签中台**：全模块统一标签~~ ✅ **已实现**（`services/tag.py` 派生聚合：日报正文 / 文章正文 / 任务标题与备注的 #tag，统一标签云 + 点标签看跨模块条目；不扫描资料库 md，因 `#` 是标题语法噪声过大）
3. ~~**提醒通知**：习惯、账单日、任务截止、目标节点~~ ✅ **已实现**（派生，无独立存储；`services/reminder.py` 聚合 习惯待打卡 / 日程逾期任务 / 今日账单日 / 逾期目标，前端顶栏 + 移动端铃铛入口带数量角标，`ReminderPanel` 按模块分组跳转）
4. ~~**模板库**：日报 / 周报 / 月报 / 任务表（日报与日程已各有雏形，可统一）~~ ✅ **已实现**（统一库 `templates.db` + `services/template.py`；四种 scope：日报/周报/月报为文本大纲、任务表为列定义 JSON；日报页与列管理均接入统一模板库，可自建/删除）
5. ~~**数据导出 / 备份**：全量 JSON / Excel 导出 + 导入恢复~~ ✅ **已实现**（`services/backup.py` 按库动态整表导出；`import_all` 为「覆盖恢复」语义、字段对齐兼容 schema 漂移；前端顶栏/移动端 💾 入口，导出 JSON 下载 + 从文件恢复）
6. **目标 OKR 模块**：目标 → 关键结果 → 周计划联动
7. ~~**日程 ↔ 计时联动**：从日程一键开始计时~~ ✅ **已实现**（timer 表新增 `source_type`/`source_ref`；日程任务行「⏱ 开始计时」一键创建正计时并跳转；计时卡片显示来源徽标可跳回）

### 4.2 Phase F：双端体验持续打磨 ⬜（贯穿）

- 所有新功能桌面 / 移动响应式（桌面表格 ↔ 移动卡片）
- 统一空状态、加载态
- 图表移动适配（ECharts 重排）
- **当前唯一未做的部分**：A–E 各阶段都只做了编译 / 逻辑 / API 层验证，**从未在浏览器或真机逐页目视确认**。

#### Phase F 走查清单（桌面 + 移动端移动模拟各过一遍）

**通用框架**
- [ ] 顶栏：🔍 搜索 / 🔔 提醒（角标）/ 💾 备份 三个入口在窄屏是否拥挤、换行或溢出
- [ ] 侧边栏导航、底部胶囊 Tab 栏、「更多」弹层
- [ ] 登录后首屏；退出登录

**既有页面**
- [ ] 日历、日报、日程（表格/看板/日历三视图）、记账、资料、文章、复盘中心、计时、习惯
- [ ] **重点**：Phase D 遗留的图表高度、横向滚动 Tab、目标进度环渲染（从未目视过）

**本轮新增 UI（E1–E7）**
- [ ] 全局搜索弹层（`Ctrl/⌘+K`）：分组结果、关键词高亮、上下键选择、回车跳转
- [ ] 搜索结果深链：日报 `?date`、文章 `?year&title`、资料 `?path` 是否精准落地
- [ ] 提醒面板：角标数量、分组、点击跳转
- [ ] 备份面板：导出下载、从文件恢复
- [ ] 模板库：日报页「模板库…」、列管理「模板库…」（套用后列顺序是否正确）
- [ ] 标签中台：标签云换行、点标签后跨模块条目
- [ ] OKR：目标「关键结果」弹层（加权汇总、进度条）、顶部「本周关键结果」

**多用户相关**
- [ ] 登录页「申请账号 / 重置密码」模式切换（手机端键盘不遮挡、16px 不缩放）
- [ ] 用户管理页：申请审批列表、成员列表在手机上是否变成卡片竖排、操作按钮换行
- [ ] 临时密码弹窗（复制按钮在微信内置浏览器是否可用，不可用要有兜底提示）
- [ ] 管理员账户弹层出现「用户管理」入口，普通成员不出现

**走查方式**：本地 `npm run dev` 起 5174，用浏览器 DevTools 移动模拟（iPhone/Android 两种宽度）逐页过；有条件再补真机（含微信内置浏览器）。

---

## 5. 关键文件地图

```
Mawork/
├── PRD_Personal_AI_Work_OS.md      # 产品文档
├── docker-compose.yml              # 部署
├── HANDOFF.md                      # ← 本文档
├── .workbuddy/memory/              # 工作日志（2026-09-17 / 09-18 / 09-21）
├── scripts/
│   └── migrate_multiuser.py        # ★ 独立运维脚本：存量数据迁到多用户（不进系统代码）
├── backend/
│   ├── ctx.py                      # ★ 请求级用户上下文（ContextVar，零依赖）
│   ├── scope.py                    # ★ 用户数据空间：建目录/建表/删目录
│   ├── config.py                   # 路径常量（★ __getattr__ 动态解析）+ 鉴权配置
│   ├── db.py                       # 建表 + 幂等迁移；init_global / init_user / init_db
│   ├── auth.py                     # JWT（含 uid/role）+ require_auth(★ async) + require_admin
│   ├── main.py                     # FastAPI 入口，注册 routers
│   ├── models/                     # accounting / planpool / habit / insight / user 建表 SQL
│   ├── routers/                    # 每模块一个路由文件（insight = 复盘中心，user = 用户管理）
│   └── services/                   # 业务逻辑层（insight = 跨库只读聚合；user = 账号与审批）
└── frontend/src/
    ├── App.vue                     # 外壳：顶栏 + 胶囊 Tab + 弹层
    ├── router/index.ts             # 路由表（9 模块 + /login + /users）
    ├── api/                        # 各模块 client（accounting/daily/planpool/insight/user...）
    ├── views/                      # 11 个视图（含 UserManageView 用户管理）
    ├── components/
    │   ├── accounting/             # TransactionForm / TransactionList / SummaryCharts
    │   ├── planpool/               # TaskTable / TaskBoard / TaskCalendar / ColumnManager
    │   ├── analysis/               # TreeNode / OverviewTab / TrendTab / GoalsPanel / ReviewPanel / ReportTree
    │   ├── home/CalendarDayEditor.vue
    │   └── timer/                  # TimerCard / TimerForm / TimerStats
    ├── styles/
    │   ├── tokens.css              # ★ 唯一样式变量源
    │   ├── main.css                # ★ 引入顺序 + 维护约定
    │   ├── mobile.css              # 移动端外壳 + 跨模块基建
    │   ├── analysis.css            # 复盘中心（含移动端）
    │   ├── user.css                # 用户管理（含移动端）
    │   ├── base.css                # 桌面布局 + 通用按钮（含顶栏入口 .topbar-link）
    │   └── <module>.css            # 各模块（桌面 + 自己那块的移动端）
    └── utils/                      # auth.ts（含 uid/role/isAdmin）/ useIsMobile.ts / dateRange.ts
```

---

## 6. 验证清单（每次改完必跑）

```bash
# 前端
cd D:/Desktop/Project_Group/Mawork/frontend
npm run build-only     # 必须通过
npm run type-check     # 必须通过（历史上多次在这里抓到残留错误）

# 后端（语法）
cd D:/Desktop/Project_Group/Mawork/backend
<python> -m py_compile routers/*.py services/*.py models/*.py db.py

# 后端（逻辑）→ 用临时库脚本，见 2.2

# 后端（API 联调）→ 本地可直接起，见 2.2
cd D:/Desktop/Project_Group/Mawork
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8011
```

**产物抽查**（确认新功能真的打包进去了）：

```bash
cd frontend/dist/assets
grep -o "关键字" *.js *.css | wc -l
```

**静态产物冒烟**（dist 起来给个 200）：起 `python -m http.server --directory dist` 后 `curl -o /dev/null -w "%{http_code}"`。

**未验证项（重要）**：A/B/C/D 四期都**没有做真机或浏览器移动模拟的逐页视觉确认**。
Phase D 的 API 已用真实数据跑通，但以下还需要目视：图表高度与移动端重排、横向滚动 Tab、
目标进度环（conic-gradient）渲染、复盘报告 Markdown 排版。

---

## 7. 给接手者的建议路径

1. **先跑一遍验证清单**，确认基线全绿（当前应为全绿）
2. **本地起服务**（见 2.2），做一轮浏览器移动模拟逐页走查——这是当前最大的空白：
   Phase C 的日程三视图、Phase D 的复盘中心都没目视过
3. **再开 Phase E（横切能力）**：先出方案（哪些能力优先级高、要不要动数据模型），给用户确认后再动代码
4. 每个 Phase 完成后：`build-only` + `type-check` + 后端临时库断言 + API 联调 + 记忆日志

---

## 8. 用户偏好（协作方式）

- 修改过程另记于 **`CHANGELOG.md`**（问题 → 方案 → 改动文件 → 验证），本文档只记「当前是什么样」

## 8.5 性能优化 / 结构治理 / 清理（2026-09-19）

详细过程见 `CHANGELOG.md`，此处只留结论：

| 项 | 结论 |
|---|---|
| element-plus | 全量 `app.use(ElementPlus)` → **按需引入**（4 组件 + 2 命令式 API）。主包 JS **855→321 KB**、CSS **455→180 KB**，首屏省约 **810 KB**；中文 locale 改由 `main.ts` 用 `ElConfigProvider` 包裹保留 |
| echarts | 新增 `utils/echarts.ts` 的 `loadEcharts()`（缓存 + 共享 Promise）统一按需加载；`TrendTab` 无数据时不加载 |
| 日报预览 | 每字符全量渲染 Markdown → **250ms 防抖**（切换日期仍同步渲染） |
| 后端结构 | `db.open_conn()` 上下文管理器 + `services/common.py::group_by_module()`，收敛 4 个 service 重复的开关连接与分组样板 |
| 清理 | 39 个构建缓存（`__pycache__` / `node_modules/.vite`）从 git 索引移除并清出磁盘；探测脚本 `_probe.py` / `_tmp_*.py` 已全部删除 |
| E7 补全 | 前端接入 `keyResultsByWeek`，「目标」面板顶部展示「本周关键结果 · YYYY-Www」，消除死代码 |

**当前约定**：新增横切能力时，数据库连接一律用 `db.open_conn()`；跨模块分组一律用 `group_by_module()`。

- 中文交流，沟通直接
- **「轮流执行」**：六块任务按 A→B→C→D→E→F 顺序依次做，不要来回问
- **先出点子 / 方案，再动代码**（尤其新功能）
- 每阶段交付后希望看到**改动文件清单 + 验证结果 + 未验证项说明**
- 重视**双端都是最佳状态**、使用方便、灵活度与自由度

---

## 9. 开发日志（2026-09-18 续 · Phase E 启动）

### E1 全局搜索（已实现）
- 后端：`backend/services/search.py`（`global_search` 跨 daily/accounting/planpool/timer 库 + articles/资料 文件，按模块分组返回 route+query）、`backend/routers/search.py`（`GET /api/search`，受保护路由）。
- 前端：`frontend/src/api/search.ts`、`frontend/src/components/GlobalSearch.vue`（顶栏 + 移动端入口 + `Ctrl/⌘+K`，关键词高亮、键盘上下选择/回车跳转）、`frontend/src/styles/search.css`。
- 深链：`ArticlesView` 支持 `?year&title`、`ResourcesView` 支持 `?path`、`DailyView` 原已支持 `?date`；点击结果精准跳转。

### E2 日程 ↔ 计时联动（已实现）
- 后端：`models/timer.py` 新增 `source_type`/`source_ref` 列；`db.py` 新增幂等迁移 `_migrate_timer`；`services/timer.py::create_timer` 接收并落库；`routers/timer.py::TimerIn` 增加字段。
- 前端：`api/timer.ts` 增加字段；`TaskTable.vue` 任务行「⏱ 开始计时」一键创建正计时并跳转 `/timer`；`TimerCard.vue` 显示「来自日程任务 #id」徽标可跳回。

### 验证
- 前端：`npm run type-check` ✅、`npm run build-only` ✅。
- 后端：`python -m py_compile` ✅（全部模块）。
- **后端临时库端到端断言 ✅（已补跑）**：
  - E1 全局搜索：跨 daily / articles / accounting / planpool / resources / timer 六模块均命中，深链 `route + query` 正确（如日报 `/daily?date=2026-09-19`）。
  - E3 模板库：`templates.db` 建库成功，内置种子 7 条。
  - E4 提醒通知：聚合命中 习惯 / 日程 / 目标，路由分别为 `/habit`、`/planpool`、`/analysis`。
  - E5 备份：导出 → 清库 → 恢复往返一致（`tasks`、`daily_entries` 均还原为 1 条）。
  - E6 标签中台：跨模块聚合正确（`#效率` 日报 2 + 日程 1 = 3；`#读书` 日报 1 + 文章 1 = 2），点标签返回的条目 route/query 正确。
  - E7 OKR：`key_results` 表随 `init_db` 建出；加权汇总正确（KR1 权重 2 完成 50% + KR2 权重 1 完成 100% → 66.7%）；`by_week` 返回 KR 并带出目标名；更新后 rollup 同步为 100%；删除目标级联删除 KR。
- **仍未做**：浏览器 / 真机双端目视走查（搜索弹层交互、文章与资料深链展开、提醒与备份面板的移动端布局、模板库套用后列顺序）。

### 本地真实服务联调（已跑通）
用 WSL 的 `py312torch222` 环境（`/home/a3195/miniforge3/envs/py312torch222`，Python 3.12.13，依赖齐全）启动后端：

```bash
cd Mawork
/home/a3195/miniforge3/envs/py312torch222/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

结果（全部 200）：

| 能力 | 接口 | 结果 |
|---|---|---|
| 健康检查 | `GET /api/health` | `{"ok":true}`，`init_db` 完成 |
| E1 全局搜索 | `GET /api/search?q=工作` | total=11，命中日报正文 |
| E2 计时联动 | `POST /api/timer/timers`（带 `source_type/source_ref`）→ `DELETE` | 落库并返回 source 字段，清理成功 |
| E3 模板库 | `GET /api/template/list[?scope=]` | 7 条内置种子 |
| E4 提醒通知 | `GET /api/reminder/list` | total=8，含习惯分组 |
| E5 备份导出 | `GET /api/backup/export` | counts: accounting 228 / planpool 159 / daily 318 / timer 2 / insight 0 / templates 7 |
| E6 标签中台 | `GET /api/tag/list` | total=3（均来自文章） |
| E7 OKR | `GET /api/insight/goals`、`/key_results/by_week` | 空数据正常返回 |

**联调中修复的真实 bug**：`main.py` 的 `_protected` 列表引用了 `backup.router`，但 `from .routers import (...)` 里漏了 `backup`，导致服务启动直接 `NameError`。此前只做静态检查与临时库断言无法发现（临时库只 import services，不 import main），**本地起服务才暴露**。已补上导入。

### E4 提醒通知（已实现）
- 后端：`backend/services/reminder.py`（`get_reminders` 派生聚合：习惯待打卡 / 日程逾期任务 / 今日账单日 / 逾期目标，按模块分组返回 route+query）、`backend/routers/reminder.py`（`GET /api/reminder/list`，受保护路由）。
- 前端：`frontend/src/api/reminder.ts`、`frontend/src/components/ReminderPanel.vue`、`frontend/src/styles/reminder.css`；`App.vue` 顶栏 + 移动端铃铛入口带数量角标，点击展开分组提醒并可跳转到对应模块。
- 设计为**纯派生、无新存储**，风险最低。

### E3 模板库（已实现）
- 后端：新增 `workspaces/templates.db`（`config.TEMPLATES_DB`）；`models/template.py`（`templates` 表 + scope 常量 + 内置种子：标准日报/极简日报/标准周报/标准月报 + 任务表列预设）、`services/template.py`（幂等种子 + 增删改查，内置模板不可删）、`routers/template.py`（`GET/POST/PUT/DELETE /api/template`）；`db.py` 的 `init_db` 初始化并写入种子。
- 联动：planpool 新增 `apply_columns_json`（服务 + `POST /api/planpool/templates/apply_json`），供统一库套用「任务表」列预设；原 `apply_template(name)` 改为复用它。
- 前端：`api/template.ts`、`components/TemplatePicker.vue`（支持多 scope、预览、套用、自建/删除）、`styles/template.css`；`DailyView` 接入（日报/周报/月报）、`components/planpool/ColumnManager.vue` 接入（任务表列预设）。

### E5 数据导出 / 备份（已实现）
- 后端：`backend/services/backup.py`（按库动态枚举整表导出，不写死表名；导入为「覆盖恢复」语义，只写两表共有列以兼容 schema 漂移）、`backend/routers/backup.py`（`GET /api/backup/export`、`POST /api/backup/import`，受保护）。
- 前端：`api/backup.ts`、`components/BackupPanel.vue`、`styles/backup.css`；`App.vue` 顶栏 + 移动端 💾 入口，支持导出 JSON 下载与从文件恢复（恢复前有二次确认）。
- 仅覆盖 SQLite 数据；workspaces 下的资料文件不入库，需在面板中提示用户另行备份。

### E6 标签中台（已实现）
- 后端：`backend/services/tag.py`（派生聚合，沿用日报 `_TAG_RE` 保证全站 #tag 语义一致；来源为 日报正文 / 文章正文 / 任务标题与备注）、`backend/routers/tag.py`（`GET /api/tag/list`、`GET /api/tag/items`，受保护）。
- 不扫描资料库 md：markdown 的 `#` 是标题语法，按 #tag 解析会把标题误判为标签。
- 前端：`api/tag.ts`、`components/TagPanel.vue`（标签云，字号随次数递增；点标签展开跨模块条目并可跳转）、`styles/tag.css`；`DailyView` 标签区新增「🏷 标签中台」入口。

### E7 目标 OKR（已实现，Phase E 收官）
- 后端：`models/insight.py` 新增 `key_results` 表（goal_id 外键级联删除；`weight` 权重、`week` 周计划联动、`deadline`）；`services/insight.py` 新增 KR 全套逻辑（`create/update/delete/list_key_results`、`goal_rollup` 加权汇总、`list_key_results_by_week` 周计划联动）；`routers/insight.py` 新增 `GET/POST /goals/{gid}/key_results`、`PUT/DELETE /key_results/{kid}`、`GET /key_results/by_week`。
- 前端：`api/insight.ts` 新增 KR 类型与函数；`components/analysis/GoalsPanel.vue` 每个目标新增「关键结果」按钮与 KR 弹层（进度条、加权汇总、增删改、周计划字段）；`styles/analysis.css` 新增 KR 样式。
- 说明：目标自身的 `current` 仍可手动推进（Phase D 既有能力），KR 的 `pct` 为「目标整体推进度」的补充视角，二者互不覆盖。

---

## 9. 性能 / 过载保护 / 公网数据安全加固（2026-09-20）

> 目标：**不写死任何机器规格**。所有保护都基于运行时真实测量（Linux `/proc`），
> 机器越大越宽松、越小越早熔断；两条铁律——① 服务器不因过载崩；② 单个超大请求拖不垮。

### 9.1 自适应过载保护（新增 `backend/guard.py`）

三个 ASGI 中间件，在 `main.py` 注册（由外到内：Guard → MaxBody → SecurityHeaders → CORS）：

| 中间件 | 作用 | 自适应逻辑 |
|---|---|---|
| `GuardMiddleware` | 并发上限 + 压力软熔断（503） | 并发上限 = `max(8, cpu数×MAWORK_GUARD_CONC_PER_CPU)`；压力判定读 `/proc/meminfo`（可用内存 < 总量 10% **或** < 绝对地板 100MB）或 `/proc/loadavg`（1min 负载 > cpu数×1.5）。重路由（search/resources/backup/analysis）在压力下优先被拦，轻路由（登录/日报/计时）保留 |
| `MaxBodySizeMiddleware` | 单请求体上限（413） | 上限 = `min(MAWORK_GUARD_MAX_BODY, 可用内存×MAWORK_GUARD_BODY_MEM_FRAC)`，硬上限默认 10MB，任何机器都不可能一个请求吃光内存 |
| `SecurityHeadersMiddleware` | 安全响应头 | `nosniff` / `X-Frame-Options: DENY` / `Referrer-Policy` / `Permissions-Policy` 常开；`HSTS`(`MAWORK_HSTS`)、严格 `CSP`(`MAWORK_CSP`) 可开关，避免误伤现有前端 |

`GET /api/health` 豁免并发计数，并回报实时指标：`in_flight / concurrency_cap / mem_available_mb / mem_total_mb / loadavg_1 / rss_mb`，便于监控是否触发护栏。

### 9.2 内存爆炸点封堵

- `resources/content`：单文件读取按 `guard.max_file_read_bytes()` 动态封顶，超限返回 413（不再整文件读进内存）。
- `services/search.py`：搜索扫描最多 `SEARCH_MAX_FILES=300` 个文件，单文件超 `max_file_read_bytes()` 跳过；文章/资料读取均受同一上限约束。
- `resources/tree`：目录树递归深度限制 `MAX_TREE_DEPTH=8`，防异常深目录递归爆栈/内存。

### 9.3 SQLite 性能 PRAGMA（`db.py` 的 `get_conn`）

开 `journal_mode=WAL` + `synchronous=NORMAL` + `busy_timeout=5000` + `cache_size=-8000` + `temp_store=MEMORY`。
WAL 是关键：把「写锁整库」变为「写锁单行」，降低低核数下写冲突雪崩风险（与机器大小无关，必做）。

### 9.4 公网数据安全

- `config.py` 新增 `MAWORK_REQUIRE_STRONG_SECRET`：启动自检，若 `MAWORK_SECRET` 为默认值或 <16 位、或 `MAWORK_ADMIN_PASSWORD` 为弱值 → 打 CRITICAL 告警；该开关为 1 时直接拒绝启动。
- 新增 `.env.example`（仓库此前缺失）：含强密钥占位、`MAWORK_CORS_ORIGINS`、`MAWORK_REQUIRE_STRONG_SECRET`、护栏参数注释、生成命令。
- CORS 默认仅 localhost（已安全），服务器需设真实域名。
- 文档/OpenAPI 默认关闭（`MAWORK_ENABLE_DOCS=0`）。

### 9.5 构建 / 部署加固（Dockerfile）

- `backend/Dockerfile`：uvicorn 加 `--workers 1 --limit-max-requests 2000 --timeout-keep-alive 20 --backlog 128`（单 worker 保内存、定期回收防泄漏）。并发/内存硬保护仍由应用层 guard 负责。
- `frontend/Dockerfile`：`NODE_OPTIONS=--max-old-space-size=768` + `npm run build-only`（跳过 `vue-tsc` 类型检查，省内存，避免低配服务器构建 OOM）；注释给出「本地构建 dist 再拷服务器」的零 node 工具链替代方案。

### 9.6 验证

- `py_compile` 全绿；`import backend.main` 成功（116 routes）。
- guard 单测（dev 16核/8GB 机）：硬上限 10MB 生效、并发上限 64、压力判定随 cpu/内存自适应、heavy 路由识别正确。
- 真实服务需 `docker compose up -d --build` 后 `curl /api/health` 看 `guard` 字段确认。


