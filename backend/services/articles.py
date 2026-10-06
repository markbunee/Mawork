"""文章业务逻辑：文章以「每篇一条记录」存入 articles.db。

字段：year / date / title / content(markdown) / created_at / updated_at。
同一 year 内 title 唯一；编辑标题时若与现有标题不同则视为「改名」（迁移记录）。

相比旧实现（按年份单个 Article.md、文件内 # 标题切块），入库后：
- 支持按 year / date 维度聚合，便于复盘检索；
- 改写为整行 UPDATE，不再重写整个文件，避免并发相互覆盖。
"""

from .. import config
from ..db import open_conn

# 索引类全量扫描的自我保护上限（仅影响搜索 / 标签的覆盖范围，不动数据）
INDEX_MAX_ARTICLES = 300
INDEX_MAX_CONTENT_BYTES = 4 * 1024 * 1024  # 正文合计 4 MiB


def list_articles(year: str) -> list[dict]:
    """列出某年全部文章（目录）。"""
    with open_conn(config.ARTICLES_DB) as conn:
        rows = conn.execute(
            "SELECT id, year, date, title, updated_at "
            "FROM articles WHERE year = ? ORDER BY date DESC, id DESC",
            (year,),
        ).fetchall()
        return [dict(r) for r in rows]


def all_articles_for_index() -> list[dict]:
    """供搜索 / 标签聚合使用的文章列表（含正文）。

    文章已入库为「每篇一条记录」，不再从 Article.md 解析。
    返回字段：year / title / content。

    带正文全量载入会随文章数线性吃内存（长文尤其明显），
    故设双重预算，对齐 search.SEARCH_MAX_FILES 的自律做法：
    条数封顶 + 正文合计字节封顶。超出的部分**静默截断**，
    只影响搜索/标签的覆盖范围，不影响任何用户数据。
    """
    with open_conn(config.ARTICLES_DB) as conn:
        rows = conn.execute(
            "SELECT year, title, content FROM articles "
            "ORDER BY year DESC, updated_at DESC LIMIT ?",
            (INDEX_MAX_ARTICLES,),
        ).fetchall()
    out: list[dict] = []
    budget = INDEX_MAX_CONTENT_BYTES
    for r in rows:
        content = r["content"] or ""
        if budget <= 0:
            break
        out.append({
            "year": r["year"],
            "title": r["title"],
            "content": content[:budget],
        })
        budget -= len(content)
    return out


def get_article(year: str, title: str) -> dict | None:
    """获取某篇（按 year + title 定位）。找不到返回 None。"""
    with open_conn(config.ARTICLES_DB) as conn:
        r = conn.execute(
            "SELECT * FROM articles WHERE year = ? AND title = ?", (year, title)
        ).fetchone()
        return dict(r) if r else None


def upsert_article(
    year: str,
    title: str,
    content: str,
    date: str = "",
    new_title: str | None = None,
) -> dict:
    """新建或更新一篇。

    - 标题作为 year 内唯一键；new_title 非空且与 title 不同表示改名。
    - 改名时若目标标题已被别的文章占用，抛出 ValueError（路由转 409）。
    """
    eff = (new_title or title).strip()
    if not eff:
        raise ValueError("标题不能为空")

    with open_conn(config.ARTICLES_DB) as conn:
        cur = conn.execute(
            "SELECT id FROM articles WHERE year = ? AND title = ?", (year, eff)
        ).fetchone()
        same = conn.execute(
            "SELECT id FROM articles WHERE year = ? AND title = ?", (year, title)
        ).fetchone()
        if cur and (not same or cur["id"] != same["id"]):
            raise ValueError("标题已存在")

        if same:
            conn.execute(
                "UPDATE articles SET title = ?, content = ?, date = ?, "
                "updated_at = datetime('now','localtime') WHERE id = ?",
                (eff, content, date, same["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO articles "
                "(year, date, title, content, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))",
                (year, date, eff, content),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM articles WHERE year = ? AND title = ?", (year, eff)
        ).fetchone()
        return dict(row)


def delete_article(year: str, title: str) -> bool:
    """删除一篇。返回是否删除成功。"""
    with open_conn(config.ARTICLES_DB) as conn:
        r = conn.execute(
            "SELECT id FROM articles WHERE year = ? AND title = ?", (year, title)
        ).fetchone()
        if not r:
            return False
        conn.execute("DELETE FROM articles WHERE id = ?", (r["id"],))
        conn.commit()
        return True



