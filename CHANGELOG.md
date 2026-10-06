# MaWork 修改日志

> 记录每次代码修改的**过程**：问题定位 → 方案 → 改动文件 → 验证结果。
> 与 `HANDOFF.md` 同步更新（`HANDOFF.md` 记「当前是什么样」，本文件记「怎么改过来的」）。

格式约定：每个条目包含「问题 / 方案 / 改动文件 / 验证」，便于回溯与回滚。

---

## 2026-09-19 性能优化 / 内存优化 / 结构治理

### 1. 主包体积：element-plus 全量引入 → 按需引入

- **问题**：`main.ts` 里 `import ElementPlus from 'element-plus'` + `app.use(ElementPlus)` + `import 'element-plus/dist/index.css'`，把 element-plus 的 **60+ 组件与整套 CSS（约 455KB）** 全部打进主包。而全项目实际只用到 4 个模板组件与 2 个命令式 API。首屏为此多下载约 800KB。
- **方案**：
  - 只引入用到的组件：`ElDialog` / `ElDatePicker` / `ElInput` / `ElInputNumber`，逐个 `app.use()` 注册；
  - 命令式 API `ElMessage` / `ElMessageBox` 在 20+ 文件里被直接调用，其样式在 `main.ts` 统一引入；
  - 各组件样式走 `element-plus/es/components/<x>/style/css`（**该入口会自动带上依赖**，如 `dialog` 会引入 `base` + `overlay`，已核实）；
  - 中文 locale 原靠 `app.use(ElementPlus, { locale })` 传递，改为在 `main.ts` 用 `ElConfigProvider` 包一层渲染 App，避免为保留 locale 而被迫全量注册。
- **改动文件**：`frontend/src/main.ts`
- **验证**：
  - 主包 JS **855 KB → 321 KB**（-62%）；主包 CSS **455 KB → 180 KB**（-60%）；首屏合计省约 **810 KB**。
  - 构建无报错；对产物 CSS 静态校验 `.el-dialog` / `.el-message` / `.el-message-box` / `.el-date-picker` / `.el-input` / `.el-input-number` / `.el-overlay` **全部存在**，确认按需引入未漏样式。

### 2. echarts：静态引入 → 统一按需加载器

- **问题**：`TimerStats.vue` / `TrendTab.vue` / `SummaryCharts.vue` 三处都 `import * as echarts from 'echarts'`。echarts 约 1.1MB，虽已被路由拆成独立 chunk，但**只要进入对应页面就会立刻下载**，即使该页无数据或用户不看图。
- **方案**：新增 `frontend/src/utils/echarts.ts` 提供 `loadEcharts()`，内部用「缓存 + 共享 Promise」保证多个图表组件只加载一次；三个组件改为 `await loadEcharts()`，并用 `disposed` 标记防止异步加载完成前组件已卸载导致的无效 init。`TrendTab.renderAll()` 更是在**无数据时不加载**，省掉 1MB+ 下载。
- **改动文件**：`frontend/src/utils/echarts.ts`（新增）、`components/timer/TimerStats.vue`、`components/analysis/TrendTab.vue`、`components/accounting/SummaryCharts.vue`
- **验证**：构建通过；echarts 仍为独立 chunk（1098 KB）但不再是进入页面即加载，仅图表真正渲染时才拉取。

### 3. 日报预览：每次按键全量渲染 Markdown → 250ms 防抖

- **问题**：`DailyView.vue` 里 `const rendered = computed(() => md.render(body.value))`，编辑日报时**每敲一个字符就同步全量渲染一次 Markdown**，长文档下输入明显卡顿。
- **方案**：改为 `ref` + `watch` 防抖（250ms）。切换日期属于程序化赋值（`loadingContent` 期间），此时**同步渲染**，避免预览滞后一拍。
- **改动文件**：`frontend/src/views/DailyView.vue`
- **验证**：`type-check` 通过；输入时渲染次数从「每字符 1 次」降为「停止输入 250ms 后 1 次」。

### 4. 后端结构治理：收敛重复的「开关连接」与「按模块分组」样板

- **问题**：`search` / `reminder` / `tag` / `backup` 四个 service 里到处重复
  `conn = db.get_conn(...); try: ... finally: conn.close()`，
  且 `reminder` / `tag` 各自手写了一遍「按 module 分组」逻辑——样板多、易漏关连接、维护成本高。
- **方案**：
  - `db.py` 新增 `open_conn()` 上下文管理器，统一负责关闭；
  - 新增 `services/common.py` 提供 `group_by_module(items)`，三处分组逻辑收敛为一处。
- **改动文件**：`backend/db.py`（新增 `open_conn`）、`backend/services/common.py`（新增）、`services/tag.py`、`services/reminder.py`、`services/search.py`、`services/backup.py`
- **验证**：`py_compile` 通过；临时库回归全绿（标签 `#效率`=2、`#读书`=2；提醒命中 习惯/日程；备份导出→清库→恢复往返一致；搜索命中 2）；**真实服务重启后 9 个接口全部 200，返回数据与重构前完全一致**（search total 11 / reminder 8 / templates 7 / backup counts 相同），确认无回归。

### 5. 清理：把构建缓存从版本控制中移除

- **问题**：`__pycache__`（含 310/312/313 三个版本的 .pyc）与 `frontend/node_modules/.vite/deps` **共 39 个文件被提交进了 git**。`.gitignore` 其实已写全规则，但对「已跟踪文件」无效。
- **方案**：`git rm -r --cached` 仅移出索引，**磁盘文件保留**（不影响运行），后续由 `.gitignore` 持续忽略。
- **改动文件**：仅 git 索引（无源码改动）
- **验证**：`git ls-files | grep -cE "__pycache__|node_modules"` 由 39 → **0**；磁盘缓存仍在，服务正常。

### 6. 补齐 E7「周计划联动」并消除死代码

- **问题**：`api/insight.ts` 里的 `keyResultsByWeek()` 无人调用（死代码），而它正是 E7 要求的「目标 → 关键结果 → **周计划联动**」缺失的最后一环——后端 `GET /key_results/by_week` 已实现并验证，但前端没有入口。
- **方案**：`GoalsPanel.vue` 加载目标时一并拉取本周 KR，在面板顶部展示「本周关键结果 · YYYY-Www」（含所属目标名与进度）。
- **改动文件**：`frontend/src/api/insight.ts`（`KeyResult` 补 `goal_title` / `goal_category`）、`components/analysis/GoalsPanel.vue`、`styles/analysis.css`
- **验证**：`type-check` + `build-only` 通过；`GET /api/insight/key_results/by_week` 真实服务返回 200（`week=2026-W38`）。

### 7. 发版缓存：SPA 路由页被缓存导致「微信里刷新不到新版本」

- **问题**：`nginx.conf` 只对 `location = /index.html` 设了 `no-cache`。但访问 `/daily`、`/home` 这类路由时，命中的是 `location /`（由 `try_files` 回退到 index.html）——**nginx 的 `add_header` 不会跨 location 继承**，所以这些路由页**完全没有禁用缓存头**。微信内置浏览器（尤其 iOS WKWebView）又常无视 `no-cache` 强缓存 HTML，表现为发版后用户仍停在旧版本；若旧 hashed 资源已被清理，还会白屏。
- **方案**：
  - `location /` 内重复声明禁用缓存头（`no-store, no-cache, must-revalidate` + `Pragma` + `Expires`），覆盖 SPA 回退；
  - `index.html` 头部补 `Cache-Control` / `Pragma` / `Expires` 三个 meta；
  - `/assets/` 维持 1 年 immutable 长缓存（文件名带内容 hash，内容变则文件名变，安全）。
- **改动文件**：`frontend/nginx.conf`、`frontend/index.html`
- **验证**：配置已改；**注意容器部署需 `docker compose build` 前端镜像才会带上新 nginx.conf**。

### 8. Phase F 双端目视走查：正式立为待办（尚未执行）

- **问题**：A–E 全部只做了编译 / 类型 / 接口层验证，**从未在浏览器或真机逐页目视确认**，是项目当前唯一未做部分。
- **方案**：在 `HANDOFF.md` 的 4.2 节写成**可执行清单**（通用框架 / 既有页面 / E1–E7 新增 UI 三类，含重点项），供后续逐项勾选。
- **改动文件**：`HANDOFF.md`
- **验证**：清单已落地，走查本身待执行（需人在浏览器里看，非自动化可替代）。

### 9. 性能 / 过载保护 / 公网数据安全加固（不写死机器规格）

- **问题**：原架构没有任何过载保护——`resources/content` 整文件读内存、`search` 用 `rglob` 扫全盘并整文件读、任意大小的 `backup/import` 请求都能进来；2核2G 类小机器上一个大请求或并发就可能 OOM 把容器打崩。且默认弱密钥/弱密码、缺 `.env.example`、无安全响应头。
- **方案**（核心：所有阈值运行时测量，按机器大小自适应，不假设"2核2G"）：
  - 新增 `backend/guard.py`，三个 ASGI 中间件：`GuardMiddleware`（并发上限 = `max(8, cpu×N)` + 压力软熔断，读 `/proc/meminfo`、`/proc/loadavg` 实时判定，重路由优先 503、轻路由保留）、`MaxBodySizeMiddleware`（单请求体上限 = `min(硬上限, 可用内存×比例)`，硬上限 10MB）、`SecurityHeadersMiddleware`（nosniff/X-Frame-Options/Referrer-Policy 常开，HSTS/CSP 可开关）。
  - `/api/health` 豁免并发并回报实时指标（in_flight / 内存 / 负载 / RSS），便于监控是否触发护栏。
  - 内存爆炸点封堵：`resources/content` 单文件读取按可用内存封顶（超限 413）；`search` 限制扫描文件数(300)与单文件大小；`resources/tree` 递归深度限制 8。
  - `db.py` 开启 SQLite `WAL + synchronous=NORMAL + busy_timeout + cache_size + temp_store`（降低低核写锁雪崩）。
  - 启动弱凭据自检（`MAWORK_REQUIRE_STRONG_SECRET=1` 时弱密钥/弱密码直接拒绝启动）；新增仓库缺失的 `.env.example`。
  - `backend/Dockerfile` uvicorn 加 `--workers 1 --limit-max-requests 2000 --timeout-keep-alive 20 --backlog 128`；`frontend/Dockerfile` 加 `NODE_OPTIONS=--max-old-space-size=768` + `npm run build-only`（跳过 vue-tsc，避免低配服务器构建 OOM）。
- **改动文件**：`backend/guard.py`（新）、`backend/config.py`、`backend/main.py`、`backend/db.py`、`backend/routers/resources.py`、`backend/services/search.py`、`backend/Dockerfile`、`frontend/Dockerfile`、`.env.example`（新）、`HANDOFF.md`、`CHANGELOG.md`
- **验证**：`py_compile` 全绿；`import backend.main` 成功（116 routes）；guard 单测在 16核/8GB 开发机上确认硬上限 10MB 生效、并发上限 64、压力判定随 cpu/内存自适应、heavy 路由识别正确；真实服务需 `docker compose up -d --build` 后 `curl /api/health` 核对 `guard` 字段。
