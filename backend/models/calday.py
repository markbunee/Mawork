"""日历文本格领域模型：常量与建表 SQL。

日历里每一天都是一块可直接输入的文本方格：
- 回车分行，每行是一条 line；
- line 分「文本」与「任务」两种，任务可点选完成 / 未完成；
- 行有来源标记：
  - manual      用户在日历格子里直接输入的（默认）；
  - daily_plan  由前一天日报「三、明日工作计划」自动写入的任务行，
                真源在日报，日历里只展示与勾选，重新保存日报时按真源重建。
- 任务行不再写进日报 Markdown（日报已入库），只在日报「查看 / 导出」时
  注入到当日「一、今日工作内容」段开头展示。
"""

# line 类型
KIND_TEXT = "text"
KIND_TASK = "task"
KIND_OPTIONS = [KIND_TEXT, KIND_TASK]

# 行来源
SOURCE_MANUAL = "manual"
SOURCE_PLAN = "daily_plan"

# 任务行的完成前缀（注入日报 / 导出用）
DONE_PREFIX = "已完成-"
TODO_PREFIX = "未完成-"

# ---------------------------------------------------------------------------
# 建表 SQL
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
-- 日历每一天的文本行
CREATE TABLE IF NOT EXISTS calendar_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL,               -- YYYY-MM-DD
    sort_order  INTEGER NOT NULL DEFAULT 0,     -- 行序
    kind        TEXT    NOT NULL DEFAULT 'text',-- text / task
    content     TEXT    NOT NULL DEFAULT '',    -- 行文字
    done        INTEGER NOT NULL DEFAULT 0,     -- 任务行是否已完成
    source      TEXT    NOT NULL DEFAULT 'manual',    -- manual / daily_plan
    source_ref  TEXT    NOT NULL DEFAULT '',          -- 来源：daily_plan 时为源日报日期
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_calday_date ON calendar_lines(date);
-- 注：source / source_ref 的复合索引由 db._migrate_calday 在加列后创建

-- 月度计划：日历上方的一整块自由文本，按月一个键
CREATE TABLE IF NOT EXISTS calendar_month_notes (
    month       TEXT PRIMARY KEY,               -- YYYY-MM
    content     TEXT NOT NULL DEFAULT '',
    updated_at  TEXT DEFAULT (datetime('now', 'localtime'))
);

-- 周计划：日历左侧一列（周一旁边），按该周周一日期一个键
CREATE TABLE IF NOT EXISTS calendar_week_notes (
    week_start  TEXT PRIMARY KEY,               -- YYYY-MM-DD（该周周一）
    content     TEXT NOT NULL DEFAULT '',
    updated_at  TEXT DEFAULT (datetime('now', 'localtime'))
);
"""
