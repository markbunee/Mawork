"""文章领域模型：建表 SQL。

文章从「按年份单个 Article.md 文件」迁移为「每篇一条记录」的关系表，
便于按 year / date 维度聚合、做复盘检索与编辑。

字段说明：
- year      所属年份（YYYY），按文件夹年份归属，复盘按年聚合用
- date      文章实际日期（YYYY-MM-DD），可空；由正文首行日期或用户填写
- title     标题（同一 year 内唯一）
- content   Markdown 正文
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    year        TEXT    NOT NULL,                       -- YYYY
    date        TEXT    NOT NULL DEFAULT '',            -- YYYY-MM-DD（可空）
    title       TEXT    NOT NULL,
    content     TEXT    NOT NULL DEFAULT '',            -- Markdown 正文
    created_at  TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(year, title)
);

CREATE INDEX IF NOT EXISTS idx_articles_year ON articles(year);
CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date);
"""
