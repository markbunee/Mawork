"""横切能力 E6：标签中台（跨模块统一标签聚合，派生、无独立存储）。

标签来源（沿用日报既有的 #tag 语义，保证全站一致）：
- daily      日报正文
- articles   文章正文（按 # 标题切块后的正文）
- planpool   任务标题与备注

不扫描资料库（resources）的 md 文件：markdown 的 `#` 是标题语法，
按 #tag 解析会把标题误判为标签，噪声过大。

对外提供两个能力：
- list_tags()：全站标签云（标签 + 总次数 + 各模块次数）
- tag_items(tag)：某标签下的全部条目（带 route + query 供前端跳转）
"""

from .. import config, db
from .daily import _TAG_RE
from . import articles as art
from .common import group_by_module


def _scan() -> list[dict]:
    """扫描全部来源，返回扁平的「标签 × 条目」列表。"""
    items: list[dict] = []

    # 1) 日报
    with db.open_conn(config.DAILY_DB) as conn:
        rows = conn.execute("SELECT date, body FROM daily_entries ORDER BY date DESC").fetchall()
    for r in rows:
        for t in _TAG_RE.findall(r["body"] or ""):
            items.append(
                {
                    "tag": t,
                    "module": "daily",
                    "module_label": "日报",
                    "title": r["date"],
                    "subtitle": "日报",
                    "route": "/daily",
                    "query": {"date": r["date"]},
                }
            )

    # 2) 文章（数据源为 articles.db 的入库文章）
    for a in art.all_articles_for_index():
        for t in _TAG_RE.findall(a.get("content") or ""):
            items.append(
                {
                    "tag": t,
                    "module": "articles",
                    "module_label": "文章",
                    "title": a["title"],
                    "subtitle": f"文章 · {a['year']}",
                    "route": "/articles",
                    "query": {"year": a["year"], "title": a["title"]},
                }
            )

    # 3) 日程任务
    with db.open_conn(config.PLANPOOL_DB) as conn:
        rows = conn.execute("SELECT id, level1, title, note FROM tasks ORDER BY id DESC").fetchall()
    for r in rows:
        text = (r["title"] or "") + " " + (r["note"] or "")
        for t in _TAG_RE.findall(text):
            items.append(
                {
                    "tag": t,
                    "module": "planpool",
                    "module_label": "日程",
                    "title": r["title"] or "未命名任务",
                    "subtitle": r["level1"] or "未分类",
                    "route": "/planpool",
                    "query": {},
                }
            )

    return items


def list_tags() -> dict:
    """全站标签云：按出现次数降序。"""
    agg: dict[str, dict] = {}
    for it in _scan():
        e = agg.setdefault(
            it["tag"], {"tag": it["tag"], "count": 0, "modules": {}}
        )
        e["count"] += 1
        e["modules"][it["module"]] = e["modules"].get(it["module"], 0) + 1
    tags = sorted(agg.values(), key=lambda x: (-x["count"], x["tag"]))
    return {
        "total": len(tags),
        "occurrences": sum(t["count"] for t in tags),
        "tags": tags,
    }


def tag_items(tag: str) -> dict:
    """某标签下的全部条目（跨模块），按模块分组。"""
    key = (tag or "").strip().lower()
    hits = [it for it in _scan() if it["tag"].lower() == key] if key else []
    return {
        "tag": (tag or "").strip(),
        "total": len(hits),
        "groups": group_by_module(hits),
    }
