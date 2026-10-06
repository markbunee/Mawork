"""习惯培养领域模型：建表 SQL。

两张表：
- habits：习惯定义（名称、坚持理由、频率、起始日、是否归档）；
- habit_logs：每日打卡记录，按 (habit_id, log_date) 唯一，幂等。

习惯数据随日历一起落在 planpool.db，便于首页日历联动。
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS habits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,                       -- 习惯名
    reason      TEXT NOT NULL DEFAULT '',            -- 为什么要坚持（感受坚持的力量）
    emoji       TEXT NOT NULL DEFAULT '🔴',          -- 图标
    freq_type   TEXT NOT NULL DEFAULT 'daily',       -- daily | weekdays | custom
    freq_days   TEXT NOT NULL DEFAULT '',            -- custom: "1,3,5"（1=周一 … 7=周日）
    start_date  TEXT NOT NULL DEFAULT (date('now')), -- 培养起始日 YYYY-MM-DD
    archived    INTEGER NOT NULL DEFAULT 0,          -- 0 进行中 / 1 已归档
    created_at  TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS habit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id    INTEGER NOT NULL,
    log_date    TEXT NOT NULL,                       -- YYYY-MM-DD
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(habit_id, log_date)
);
CREATE INDEX IF NOT EXISTS idx_habit_logs_date ON habit_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_habit_logs_habit ON habit_logs(habit_id);
"""
