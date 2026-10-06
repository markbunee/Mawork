"""模板库领域模型（横切能力 E3）：建表 SQL、scope 常量与内置模板种子。

统一存放各模块的模板，一处维护、多处复用：
- daily / weekly / monthly：文本大纲，套用时插入正文；
- task：任务表列预设，content 为列定义 JSON 数组
  （形如 [{"label":"负责人","ftype":"text","options":[]}]）。

系统内置模板（builtin=1）不可删除，用户自建模板可增删改。
"""

import json

# ---------------------------------------------------------------------------
# scope 常量
# ---------------------------------------------------------------------------
SCOPE_DAILY = "daily"
SCOPE_WEEKLY = "weekly"
SCOPE_MONTHLY = "monthly"
SCOPE_TASK = "task"

SCOPES = [SCOPE_DAILY, SCOPE_WEEKLY, SCOPE_MONTHLY, SCOPE_TASK]

SCOPE_LABELS = {
    SCOPE_DAILY: "日报",
    SCOPE_WEEKLY: "周报",
    SCOPE_MONTHLY: "月报",
    SCOPE_TASK: "任务表",
}

DEFAULT_SCOPE = SCOPE_DAILY


def _cols(items: list[dict]) -> str:
    return json.dumps(items, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 内置模板种子（scope, name, content）
# ---------------------------------------------------------------------------
PRESET_TEMPLATES: list[tuple[str, str, str]] = [
    (
        SCOPE_DAILY,
        "标准日报",
        "## 今日完成\n- \n\n## 明日计划\n- \n\n## 问题与阻塞\n- \n\n## 今日感想\n",
    ),
    (
        SCOPE_DAILY,
        "极简日报",
        "**完成**\n- \n\n**计划**\n- \n",
    ),
    (
        SCOPE_WEEKLY,
        "标准周报",
        "## 本周进展\n- \n\n## 数据概览\n- \n\n## 下周计划\n- \n\n## 复盘与改进\n- \n",
    ),
    (
        SCOPE_MONTHLY,
        "标准月报",
        "## 本月目标达成\n- \n\n## 关键结果\n- \n\n## 下月计划\n- \n\n## 复盘\n- \n",
    ),
    (
        SCOPE_TASK,
        "标准计划表",
        _cols([]),
    ),
    (
        SCOPE_TASK,
        "项目跟踪",
        _cols(
            [
                {"label": "负责人", "ftype": "text", "options": []},
                {"label": "优先级", "ftype": "select", "options": ["高", "中", "低"]},
                {"label": "风险", "ftype": "select", "options": ["低", "中", "高"]},
            ]
        ),
    ),
    (
        SCOPE_TASK,
        "学习计划",
        _cols(
            [
                {"label": "科目", "ftype": "text", "options": []},
                {"label": "预计时长", "ftype": "text", "options": []},
                {"label": "掌握程度", "ftype": "select", "options": ["了解", "熟悉", "精通"]},
            ]
        ),
    ),
]


# ---------------------------------------------------------------------------
# 建表 SQL
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scope      TEXT    NOT NULL,               -- daily / weekly / monthly / task
    name       TEXT    NOT NULL,               -- 模板名
    content    TEXT    NOT NULL DEFAULT '',    -- 正文（task 时为列定义 JSON）
    builtin    INTEGER NOT NULL DEFAULT 0,     -- 1=系统内置（不可删除）
    created_at TEXT    DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT    DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_templates_scope ON templates(scope);
"""
