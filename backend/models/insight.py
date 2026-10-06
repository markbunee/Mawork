"""目标 KPI 领域模型：建表 SQL（insight.db）。

两张表：
- goals：目标定义（起始值 / 目标值 / 当前值 / 截止日 / 分类 / 单位）；
- goal_logs：推进记录，每次更新一条，带推进后快照 value。
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,                -- 目标名
    category    TEXT    NOT NULL DEFAULT '',     -- 分类：存钱 / 读书 / 减重 / 专注…
    metric      TEXT    NOT NULL DEFAULT '',     -- 单位：元 / 本 / 公斤 / 小时…
    start_value REAL    NOT NULL DEFAULT 0,      -- 起始值
    target      REAL    NOT NULL DEFAULT 0,      -- 目标值
    current     REAL    NOT NULL DEFAULT 0,      -- 当前值
    deadline    TEXT    NOT NULL DEFAULT '',     -- YYYY-MM-DD
    note        TEXT    NOT NULL DEFAULT '',
    archived    INTEGER NOT NULL DEFAULT 0,      -- 0 进行中 / 1 已归档
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_goals_archived ON goals(archived);

CREATE TABLE IF NOT EXISTS goal_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id    INTEGER NOT NULL,
    log_date   TEXT    NOT NULL DEFAULT (date('now', 'localtime')),
    delta      REAL    NOT NULL DEFAULT 0,      -- 本次推进量
    value      REAL    NOT NULL DEFAULT 0,      -- 推进后的当前值快照
    note       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_goal_logs_goal ON goal_logs(goal_id, log_date);

-- 关键结果（OKR 的 KR，横切能力 E7）：一个目标下挂若干 KR
-- weight 用于把多个 KR 加权汇总成目标进度；week 用于周计划联动（YYYY-Www，可空）
CREATE TABLE IF NOT EXISTS key_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id     INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    title       TEXT    NOT NULL,
    metric      TEXT    NOT NULL DEFAULT '',
    start_value REAL    NOT NULL DEFAULT 0,
    target      REAL    NOT NULL DEFAULT 0,
    current     REAL    NOT NULL DEFAULT 0,
    weight      REAL    NOT NULL DEFAULT 1,
    week        TEXT    NOT NULL DEFAULT '',
    deadline    TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_krs_goal ON key_results(goal_id);
CREATE INDEX IF NOT EXISTS idx_krs_week ON key_results(week);
"""

# 目标分类建议项（前端下拉参考，非强校验）
GOAL_CATEGORIES = ["存钱", "读书", "减重", "专注", "写作", "运动", "学习", "其他"]
