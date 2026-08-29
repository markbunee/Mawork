"""日程任务领域模型：进度常量、配色映射与建表 SQL。

进度四态（用户确认，不要"待定"）：
- 完成   未完成   进行中   搁置

颜色要求低饱和、颜色不要太深，配合米白底极简文艺风。
"""

# 进度状态常量
PROGRESS_DONE = "完成"
PROGRESS_TODO = "未完成"
PROGRESS_DOING = "进行中"
PROGRESS_ON_HOLD = "搁置"

PROGRESS_OPTIONS = [PROGRESS_DONE, PROGRESS_TODO, PROGRESS_DOING, PROGRESS_ON_HOLD]

# 手动状态（用户显式设定，不受日期自动流转影响）
MANUAL_PROGRESS = {PROGRESS_DONE, PROGRESS_ON_HOLD}

# 配色：text 前景色 / bg 背景色（低饱和）
PROGRESS_COLORS = {
    PROGRESS_DONE: {"text": "#6F8F6B", "bg": "#EDF3EC"},     # 鼠尾草绿
    PROGRESS_TODO: {"text": "#B57F77", "bg": "#F9EFED"},     # 陶土粉
    PROGRESS_DOING: {"text": "#5A7184", "bg": "#E9EFF3"},    # 雾霭蓝
    PROGRESS_ON_HOLD: {"text": "#9A948B", "bg": "#F2F0EC"},  # 暖中性灰
}


# ---------------------------------------------------------------------------
# 建表 SQL
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level1      TEXT    NOT NULL DEFAULT '',              -- 一级任务
    level2      TEXT    NOT NULL DEFAULT '',              -- 二级任务
    progress    TEXT    NOT NULL DEFAULT '未完成',         -- 完成/未完成/进行中/搁置（原始状态）
    note        TEXT    DEFAULT '',                        -- 备注
    start_date  TEXT    DEFAULT '',                        -- YYYY-MM-DD
    end_date    TEXT    DEFAULT '',                        -- YYYY-MM-DD
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_start ON tasks(start_date);
CREATE INDEX IF NOT EXISTS idx_tasks_end   ON tasks(end_date);
CREATE INDEX IF NOT EXISTS idx_tasks_level1 ON tasks(level1);

-- 每日打卡表：跨时间段任务的每日打卡记录
CREATE TABLE IF NOT EXISTS task_checkins (
    task_id     INTEGER NOT NULL,
    date        TEXT    NOT NULL,               -- YYYY-MM-DD
    PRIMARY KEY (task_id, date),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
"""
