"""计时器领域模型：四种模式常量与建表 SQL。

计时器类型（统一一张 timers 表，以 type 区分）：
- countdown       倒计时：到 target_at 还有多久（实时计算，不落耗时）
- countup         正计时：从累计秒 + 当前运行段计时；开始/停止产生 time_logs 耗时记录
- countdown_days  倒数日：距离 target_at（日期）还有几天（实时计算）
- countup_days    正数日：从 start_at（日期）起已过去几天（实时计算）

设计约定：
- 计划名(title) 与备注(note) 为所有模式共有；
- 仅「正计时」会产生 time_logs 耗时记录，供日/周/月统计；
- 倒计时/倒数日/正数日为计划与提醒，不产生耗时统计；
- source_type / source_ref 用于跨模块联动（如日程任务一键开始计时）。
"""

# 计时器类型
TYPE_COUNTDOWN = "countdown"
TYPE_COUNTUP = "countup"
TYPE_COUNTDOWN_DAYS = "countdown_days"
TYPE_COUNTUP_DAYS = "countup_days"

TIMER_TYPES = [TYPE_COUNTDOWN, TYPE_COUNTUP, TYPE_COUNTDOWN_DAYS, TYPE_COUNTUP_DAYS]

TYPE_LABELS = {
    TYPE_COUNTDOWN: "倒计时",
    TYPE_COUNTUP: "正计时",
    TYPE_COUNTDOWN_DAYS: "倒数日",
    TYPE_COUNTUP_DAYS: "正数日",
}

DEFAULT_TYPE = TYPE_COUNTUP

# 运行状态（主要服务于正计时的运行控制）
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_FINISHED = "finished"

STATUS_OPTIONS = [STATUS_ACTIVE, STATUS_PAUSED, STATUS_FINISHED]
DEFAULT_STATUS = STATUS_ACTIVE


# ---------------------------------------------------------------------------
# 建表 SQL
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS timers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT    NOT NULL DEFAULT 'countup',
    title           TEXT    NOT NULL DEFAULT '',
    note            TEXT    DEFAULT '',
    target_at       TEXT    DEFAULT '',
    start_at        TEXT    DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'active',
    running_since   TEXT    DEFAULT '',
    accumulated_sec INTEGER NOT NULL DEFAULT 0,
    source_type     TEXT    NOT NULL DEFAULT '',
    source_ref      TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT    DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_timers_type   ON timers(type);
CREATE INDEX IF NOT EXISTS idx_timers_status ON timers(status);

-- 耗时日志：统计来源（仅正计时产生）
CREATE TABLE IF NOT EXISTS time_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timer_id      INTEGER,
    title         TEXT    DEFAULT '',
    note          TEXT    DEFAULT '',
    start_at      TEXT    DEFAULT '',
    end_at        TEXT    DEFAULT '',
    duration_sec  INTEGER NOT NULL DEFAULT 0,
    day           TEXT    DEFAULT '',
    week          TEXT    DEFAULT '',
    month         TEXT    DEFAULT '',
    created_at    TEXT    DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_logs_day   ON time_logs(day);
CREATE INDEX IF NOT EXISTS idx_logs_week  ON time_logs(week);
CREATE INDEX IF NOT EXISTS idx_logs_month ON time_logs(month);
CREATE INDEX IF NOT EXISTS idx_logs_timer ON time_logs(timer_id);
"""
