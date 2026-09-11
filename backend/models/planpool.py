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
"""
