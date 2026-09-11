"""日报领域模型：常量与建表 SQL。

日报已从 Markdown 文件迁移到 daily.db，数据库是唯一真源：
- daily_entries   一行一篇日报，date 唯一，body 保存用户手写的完整正文
  （正文按「一、今日工作内容 / 二、问题反馈 / 三、明日工作计划」切段）；
- daily_sections  把每篇正文切成段落，section_key 做归一化
  （标题写法不统一，如「三、明天工作计划」也归入 plan），供结构查询与导出；
- 日历任务行（calendar_lines）是独立的另一份真源，不再写进日报正文，
  只在「日报查看 / 导出」时注入到今日工作内容段开头；
- 「三、明日工作计划」段的条目会在保存日报时自动写入次日的 calendar_lines
  （source='daily_plan'），实现"明日待办自动出现在日历里"。

历史遗留的 workspaces/{year}/daily.md（或 Daily.md）在启动时一次性导入后
不再参与读写。
"""

# 段落归一化键
KEY_WORK = "work"      # 今日工作内容
KEY_ISSUE = "issue"    # 问题反馈
KEY_PLAN = "plan"      # 明日工作计划
KEY_OTHER = "other"    # 其它 / 自定义段落

KEYS_ORDER = [KEY_WORK, KEY_ISSUE, KEY_PLAN, KEY_OTHER]

# 默认三段模板（新日报 / 空日报用）
DEFAULT_SECTIONS = [
    {"heading": "一、今日工作内容", "key": KEY_WORK, "body": ""},
    {"heading": "二、问题反馈", "key": KEY_ISSUE, "body": ""},
    {"heading": "三、明日工作计划", "key": KEY_PLAN, "body": ""},
]

# 段标题正则：一、xxx / 二、（xxx） / 3、xxx
SECTION_TITLE_RE = "^[一二三四五六七八九十百]{1,3}、"
# 日报标题正则（兼容 YYYY.M.D 与 YYYY.MM.DD、半角全角冒号）
DAILY_HEADING_RE = r"^##\s*日报_.*?[：:]\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\s*$"

# 原文件里承载日历任务的段落，注入 / 归一化时用
WORK_SECTION = "一、今日工作内容"
PLAN_SECTION = "三、明日工作计划"

# ---------------------------------------------------------------------------
# 建表 SQL
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS daily_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL UNIQUE,      -- YYYY-MM-DD
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    heading     TEXT    NOT NULL DEFAULT '',  -- ## 日报_马炫轩：2026.09.02
    body        TEXT    NOT NULL DEFAULT '',  -- 用户手写正文（各段落拼接）
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_daily_date  ON daily_entries(date);
CREATE INDEX IF NOT EXISTS idx_daily_year  ON daily_entries(year);

CREATE TABLE IF NOT EXISTS daily_sections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id    INTEGER NOT NULL REFERENCES daily_entries(id) ON DELETE CASCADE,
    sort_order  INTEGER NOT NULL DEFAULT 0,   -- 段落顺序
    heading     TEXT    NOT NULL DEFAULT '',  -- 原文标题（含序号，如「一、今日工作内容」）
    section_key TEXT    NOT NULL DEFAULT 'other', -- work / issue / plan / other
    body        TEXT    NOT NULL DEFAULT ''   -- 该段正文
);

CREATE INDEX IF NOT EXISTS idx_daily_sections ON daily_sections(entry_id, sort_order);
"""
