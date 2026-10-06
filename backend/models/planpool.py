"""日程任务领域模型：状态常量与建表 SQL。

状态三态（用户手动维护，不做任何基于日期的自动流转）：
- 未完成   进行中   已完成

设计约定：
- 「一级计划」（level1）是分类列，「任务名」（title）是其下的具体任务；
- 日 / 周 / 月度计划类型已移除，月计划与周计划改由日历模块的独立文本承担；
- 完成度是用户手填的 0-100 整数，与状态互不联动（完全交由用户修改）；
- 计划页即一张极简 Excel 网格表，按结束日期排序。
"""

# 进度状态常量
PROGRESS_TODO = "未完成"
PROGRESS_DOING = "进行中"
PROGRESS_DONE = "已完成"

PROGRESS_OPTIONS = [PROGRESS_TODO, PROGRESS_DOING, PROGRESS_DONE]

DEFAULT_PROGRESS = PROGRESS_TODO

# 完成度取值范围
COMPLETION_MIN = 0
COMPLETION_MAX = 100
DEFAULT_COMPLETION = 0


# ---------------------------------------------------------------------------
# 建表 SQL
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level1      TEXT    NOT NULL DEFAULT '',              -- 一级计划（分类）
    title       TEXT    NOT NULL DEFAULT '',              -- 任务名
    progress    TEXT    NOT NULL DEFAULT '未完成',         -- 未完成/进行中/已完成（用户手动维护）
    completion  INTEGER NOT NULL DEFAULT 0,                -- 完成度 0-100（用户手动维护）
    note        TEXT    DEFAULT '',                        -- 备注
    start_date  TEXT    DEFAULT '',                        -- YYYY-MM-DD
    end_date    TEXT    DEFAULT '',                        -- YYYY-MM-DD
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_start ON tasks(start_date);
CREATE INDEX IF NOT EXISTS idx_tasks_end   ON tasks(end_date);

-- 列定义：灵活列模型（取代固定 7 列）。
--   builtin=1 为内置列，其值与 tasks 核心列一一对应，不可删、可重排/隐藏；
--   builtin=0 为自定义列，其值存于 task_cells。
--   ftype ∈ text | date | number | select | check
--   options 仅 select 用，JSON 数组字符串
--   position 决定显示顺序；pinned 列固定在左侧（行号之后）
CREATE TABLE IF NOT EXISTS task_columns (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    key      TEXT    NOT NULL UNIQUE,        -- 内置列=核心列名；自定义列=c{id}
    label    TEXT    NOT NULL,
    ftype    TEXT    NOT NULL DEFAULT 'text',
    options  TEXT    DEFAULT '',              -- select 的选项 JSON
    position INTEGER NOT NULL DEFAULT 0,
    pinned   INTEGER NOT NULL DEFAULT 0,      -- 1=固定在行号之后
    builtin  INTEGER NOT NULL DEFAULT 0,
    visible  INTEGER NOT NULL DEFAULT 1
);

-- 自定义列的值（EAV），内置列不在此表
CREATE TABLE IF NOT EXISTS task_cells (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id  INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    col_key  TEXT    NOT NULL,
    value    TEXT    DEFAULT '',
    UNIQUE (task_id, col_key)
);

CREATE INDEX IF NOT EXISTS idx_task_cells_task ON task_cells(task_id);

-- 预设列模板（可一键套用，重建自定义列）
CREATE TABLE IF NOT EXISTS task_templates (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT    NOT NULL,
    builtin  INTEGER NOT NULL DEFAULT 1,       -- 1=系统内置模板（不可删）
    columns_json TEXT NOT NULL                  -- 自定义列定义 JSON 数组
);
"""
