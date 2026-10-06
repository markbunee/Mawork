"""全局搜索：跨模块只读聚合检索（横切能力 E1）。

检索范围（全部只读，不写任何库）：
- daily.db      日报正文
- articles      workspaces/{year}/Article.md（按 # 标题切块）
- accounting.db 交易备注 / 分类
- planpool.db   任务标题 / 备注 / 一级计划
- timer.db      计时器名称 / 备注
- resources     workspaces 下 .md/.txt 文件（文件名 + 内容）

返回按模块分组的统一结构，每项携带前端跳转所需的 route 与 query。
"""

from pathlib import Path

from .. import config, db, guard
from ..services import articles as art

# 搜索扫描的硬上限：最多扫描的文件数 / 单文件读取上限（按可用内存动态封顶）
SEARCH_MAX_FILES = 300


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _like(q: str) -> str:
    return f"%{q}%"


def _snippet(text: str, q: str, radius: int = 36) -> str:
    """取关键词首次出现位置前后片段，用 … 截断。"""
    idx = text.lower().find(q.lower())
    if idx < 0:
        return text[: radius * 2].strip()
    start = max(0, idx - radius)
    end = min(len(text), idx + len(q) + radius)
    s = text[start:end].replace("\n", " ").strip()
    return ("…" if start > 0 else "") + s + ("…" if end < len(text) else "")


# ---------------------------------------------------------------------------
# 各模块检索
# ---------------------------------------------------------------------------
def _search_daily(conn, q: str, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT date, body FROM daily_entries WHERE body LIKE ? ORDER BY date DESC LIMIT ?",
        (_like(q), limit),
    ).fetchall()
    return [
        {
            "id": r["date"],
            "title": r["date"],
            "subtitle": "日报",
            "snippet": _snippet(r["body"] or "", q),
            "route": "/daily",
            "query": {"date": r["date"]},
        }
        for r in rows
    ]


def _search_accounting(conn, q: str, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, kind, category, category2, note, date FROM transactions "
        "WHERE note LIKE ? OR category LIKE ? OR category2 LIKE ? "
        "ORDER BY date DESC LIMIT ?",
        (_like(q), _like(q), _like(q), limit),
    ).fetchall()
    out = []
    for r in rows:
        sub = f"{r['date']} · {r['category']}"
        if r["category2"]:
            sub += f" / {r['category2']}"
        out.append(
            {
                "id": r["id"],
                "title": ((r["note"] or "").strip().split("\n")[0] or "（无备注）"),
                "subtitle": sub,
                "snippet": _snippet(r["note"] or "", q),
                "route": "/accounting",
                "query": {},
            }
        )
    return out


def _search_planpool(conn, q: str, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, level1, title, note FROM tasks "
        "WHERE title LIKE ? OR note LIKE ? OR level1 LIKE ? "
        "ORDER BY id DESC LIMIT ?",
        (_like(q), _like(q), _like(q), limit),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"] or "（无标题）",
            "subtitle": r["level1"] or "未分类",
            "snippet": _snippet(r["note"] or "", q),
            "route": "/planpool",
            "query": {},
        }
        for r in rows
    ]


def _search_timer(conn, q: str, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, type, title, note FROM timers "
        "WHERE title LIKE ? OR note LIKE ? ORDER BY id DESC LIMIT ?",
        (_like(q), _like(q), limit),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"] or "未命名计时",
            "subtitle": f"计时 · {r['type']}",
            "snippet": _snippet(r["note"] or "", q),
            "route": "/timer",
            "query": {},
        }
        for r in rows
    ]


def _search_articles(q: str, limit: int) -> list[dict]:
    """按标题与正文匹配（数据源为 articles.db 的入库文章）。"""
    out: list[dict] = []
    ql = q.lower()
    for a in art.all_articles_for_index():
        body = a.get("content") or ""
        if ql in (a["title"] + "\n" + body).lower():
            out.append(
                {
                    "id": f"{a['year']}:{a['title']}",
                    "title": a["title"],
                    "subtitle": f"文章 · {a['year']}",
                    "snippet": _snippet(body, q),
                    "route": "/articles",
                    "query": {"year": a["year"], "title": a["title"]},
                }
            )
            if len(out) >= limit:
                return out
    return out


def _search_resources(q: str, limit: int) -> list[dict]:
    """扫描 workspaces 下 .md/.txt 文件（跳过 Article.md 与隐藏目录），按文件名 + 内容匹配。"""
    out: list[dict] = []
    root = config.data_dir()
    if not root.exists():
        return out
    ql = q.lower()
    files: list[tuple[str, Path]] = []
    read_limit = guard.max_file_read_bytes()
    scanned = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".md", ".markdown", ".txt"):
            continue
        if p.name == "Article.md":
            continue
        rel_parts = p.relative_to(root).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        # 单文件过大 / 扫描数超限 → 跳过，避免把整个磁盘读进内存
        if p.stat().st_size > read_limit or scanned >= SEARCH_MAX_FILES:
            continue
        scanned += 1
        rel = "/".join(rel_parts)
        files.append((rel, p))
    for rel, p in files:
        name_hit = ql in rel.lower()
        snippet = ""
        if not name_hit:
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if ql not in content.lower():
                continue
            snippet = _snippet(content, q)
        out.append(
            {
                "id": rel,
                "title": p.name,
                "subtitle": rel,
                "snippet": snippet or "文件名匹配",
                "route": "/resources",
                "query": {"path": rel},
            }
        )
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# 聚合入口
# ---------------------------------------------------------------------------
def global_search(q: str, limit: int = 8) -> dict:
    q = (q or "").strip()
    if not q:
        return {"q": q, "total": 0, "groups": []}

    groups: list[dict] = []
    total = 0

    # 数据库类模块：逐个独立连接，单模块异常不影响其余
    _db_specs = [
        ("daily", config.DAILY_DB, _search_daily),
        ("accounting", config.ACCOUNTING_DB, _search_accounting),
        ("planpool", config.PLANPOOL_DB, _search_planpool),
        ("timer", config.TIMER_DB, _search_timer),
    ]
    for module, db_path, fn in _db_specs:
        try:
            with db.open_conn(db_path) as conn:
                items = fn(conn, q, limit)
        except Exception:
            items = []
        if items:
            groups.append({"module": module, "label": _MODULE_LABELS[module], "items": items})
            total += len(items)

    # 文件类模块
    for module, fn in (("articles", _search_articles), ("resources", _search_resources)):
        try:
            items = fn(q, limit)
        except Exception:
            items = []
        if items:
            groups.append({"module": module, "label": _MODULE_LABELS[module], "items": items})
            total += len(items)

    return {"q": q, "total": total, "groups": groups}


_MODULE_LABELS = {
    "daily": "日报",
    "accounting": "记账",
    "planpool": "日程",
    "timer": "计时",
    "articles": "文章",
    "resources": "资料",
}
