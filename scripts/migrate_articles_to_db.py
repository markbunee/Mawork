#!/usr/bin/env python3
"""把旧的「按年份单个 Article.md 文件」迁移进 articles.db（每篇一条记录）。

★ 这是**一次性运维脚本**，不属于系统运行时代码：
  - 不放在 backend/ 里，运行时代码不会 import 它；
  - 只做一件事：扫描 workspaces 下所有 Article.md，按一级标题（# 标题）切块，
    把每篇作为一条记录写入对应用户的 articles.db，并尽量从正文首行抽取日期。

执行前**建议停掉 MaWork 服务**（避免 SQLite WAL 未落盘导致数据不全）。

用法（在 Mawork/ 目录下）：
    python scripts/migrate_articles_to_db.py            # 演练：只打印将要导入的文章
    python scripts/migrate_articles_to_db.py --apply    # 真正写入

幂等：同一 (year, title) 已存在则跳过，重复执行不会重复入库。
"""

import argparse
import re
import sys
from pathlib import Path

# 让脚本可以直接 `python scripts/migrate_articles_to_db.py` 跑（把 Mawork/ 加入搜索路径）
MAWORK_DIR = Path(__file__).resolve().parent.parent
if str(MAWORK_DIR) not in sys.path:
    sys.path.insert(0, str(MAWORK_DIR))

from backend.db import open_conn  # noqa: E402
from backend.models.articles import SCHEMA_SQL  # noqa: E402

# 一级标题正则：# 标题（# 后必须有空格）
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$")
# 日期识别：YYYY年MM月DD日 / MM月DD日（缺年用文件夹年份）/ YYYY-MM-DD
DATE_FULL_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
DATE_MD_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")
DATE_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _log(msg: str) -> None:
    print(msg, flush=True)


def find_article_files() -> list[tuple[Path, str]]:
    """返回 [(article.md 路径, year), ...]，覆盖多用户与单用户两种布局。"""
    from backend import config

    ws = config.WORKSPACES_DIR
    found: list[tuple[Path, str]] = []

    # 多用户：workspaces/users/u{uid}/{year}/Article.md
    users_dir = ws / "users"
    if users_dir.is_dir():
        for ud in sorted(users_dir.iterdir()):
            if not (ud.is_dir() and ud.name.startswith("u") and ud.name[1:].isdigit()):
                continue
            for yd in sorted(ud.iterdir()):
                if yd.is_dir() and yd.name.isdigit() and (yd / "Article.md").is_file():
                    found.append((yd / "Article.md", yd.name))

    # 单用户：workspaces/{year}/Article.md（根目录下直接是年份文件夹）
    for yd in sorted(ws.iterdir()):
        if yd.is_dir() and yd.name.isdigit() and (yd / "Article.md").is_file():
            found.append((yd / "Article.md", yd.name))

    return found


def parse_blocks(text: str) -> list[dict]:
    """按一级标题切块，返回 [{title, date, content}]。"""
    blocks: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        m = HEADING_RE.match(line.strip())
        if m:
            if current is not None:
                blocks.append(current)
            current = {"title": m.group(1).strip(), "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current is not None:
        blocks.append(current)

    out: list[dict] = []
    for b in blocks:
        # 去掉首尾空行
        lines = b["lines"]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        content = "\n".join(lines).strip("\n")

        # 抽取日期：优先正文首行里的「YYYY年MM月DD日」，其次「MM月DD日」（用文件夹年），
        # 再次 ISO 日期；都无则日期留空。
        date = ""
        year_hint = ""
        date_line = lines[0] if lines else ""
        fm = DATE_FULL_RE.search(date_line)
        if fm:
            date = f"{int(fm.group(1)):04d}-{int(fm.group(2)):02d}-{int(fm.group(3)):02d}"
        else:
            mm = DATE_MD_RE.search(date_line)
            if mm:
                # 年份稍后由调用方按文件夹年份补全
                date = f"__YEAR__-{int(mm.group(1)):02d}-{int(mm.group(2)):02d}"
            else:
                im = DATE_ISO_RE.search(date_line)
                if im:
                    date = f"{int(im.group(1)):04d}-{int(im.group(2)):02d}-{int(im.group(3)):02d}"
        out.append({"title": b["title"], "date": date, "content": content})
    return out


def import_file(article_file: Path, year: str, apply: bool) -> int:
    """把一个 Article.md 解析后写入其对应的 articles.db。返回导入条数。"""
    # 文章库与 Article.md 同级归属：多用户是 users/u{uid}/articles.db，
    # 单用户是 workspaces/articles.db —— 即 Article.md 的「祖父目录」下的 articles.db。
    db_path = article_file.parent.parent / "articles.db"
    blocks = parse_blocks(article_file.read_text(encoding="utf-8"))

    count = 0
    with open_conn(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        for b in blocks:
            date = b["date"]
            if date.startswith("__YEAR__-"):
                date = year + date[len("__YEAR__"):]
            ex = conn.execute(
                "SELECT 1 FROM articles WHERE year = ? AND title = ?", (year, b["title"])
            ).fetchone()
            if ex:
                _log(f"    ⏭ 已存在，跳过：[{year}] {b['title']}")
                continue
            if apply:
                conn.execute(
                    "INSERT INTO articles "
                    "(year, date, title, content, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))",
                    (year, date, b["title"], b["content"]),
                )
                count += 1
            _log(f"    {'＋' if apply else '·'} 导入：[{year}] {b['title']}  (date={date or '—'})")
        if apply:
            conn.commit()
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description="Article.md → articles.db 迁移")
    ap.add_argument("--apply", action="store_true", help="真正写入；不加则只演练")
    args = ap.parse_args()

    files = find_article_files()
    if not files:
        _log("未找到任何 Article.md，无需迁移。")
        return 0

    _log("=" * 64)
    _log("MaWork 文章迁移：Article.md → articles.db")
    _log("=" * 64)
    _log(f"模式：{'写入' if args.apply else '演练（加 --apply 才真正写入）'}")
    total = 0
    for f, year in files:
        _log(f"\n{f}")
        total += import_file(f, year, args.apply)
    _log("\n" + "=" * 64)
    _log(f"完成。共{'导入' if args.apply else '将要导入'} {total} 篇文章。")
    if not args.apply:
        _log("确认无误后执行：python scripts/migrate_articles_to_db.py --apply")
    _log("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
