"""文章业务逻辑：按 Markdown 一级标题切块、读写、新建。

存储模型：一个年份一个文件（如 workspaces/2026/Article.md），
文件内以「# 标题」作为每篇文章的分隔标题。
定位用标题文本（假设标题唯一）。
"""

import re
from pathlib import Path

from .. import config

# 一级标题正则：# 标题
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$")


def article_file(year: str) -> Path:
    """返回某年的文章文件路径。"""
    return config.WORKSPACES_DIR / year / "Article.md"


def split_articles(text: str) -> list[dict]:
    """按 # 一级标题切块，返回 [{title, heading, body}]。

    - title：标题正文（不含 # ）
    - heading：完整标题行（含 # ）
    - body：正文（不含标题行）
    """
    lines = text.splitlines()
    blocks: list[dict] = []
    current = None
    for line in lines:
        m = HEADING_RE.match(line.strip())
        if m:
            if current is not None:
                blocks.append(current)
            current = {"title": m.group(1).strip(), "heading": line.strip(), "body": []}
        else:
            if current is not None:
                current["body"].append(line)
    if current is not None:
        blocks.append(current)

    for b in blocks:
        while b["body"] and not b["body"][0].strip():
            b["body"].pop(0)
        while b["body"] and not b["body"][-1].strip():
            b["body"].pop()
        b["body"] = "\n".join(b["body"])
    return blocks


def render_block(heading: str, body: str) -> str:
    body = body.strip("\n")
    return f"{heading}\n\n{body}\n" if body else f"{heading}\n\n"


def list_articles(year: str) -> list[dict]:
    """列出某年全部文章的标题列表（目录）。"""
    f = article_file(year)
    if not f.exists():
        return []
    blocks = split_articles(f.read_text(encoding="utf-8"))
    return [{"title": b["title"]} for b in blocks]


def get_article(year: str, title: str) -> dict | None:
    """获取某篇（按标题定位）。找不到返回 None。"""
    f = article_file(year)
    if not f.exists():
        return None
    for b in split_articles(f.read_text(encoding="utf-8")):
        if b["title"] == title:
            return {"title": b["title"], "heading": b["heading"], "body": b["body"]}
    return None


def upsert_article(year: str, title: str, body: str) -> dict:
    """新建或更新一篇。标题存在则替换正文，不存在则追加到文件末尾。"""
    f = article_file(year)
    f.parent.mkdir(parents=True, exist_ok=True)

    heading = f"# {title}"
    new_block = render_block(heading, body)

    if f.exists():
        text = f.read_text(encoding="utf-8")
        blocks = split_articles(text)
        if any(b["title"] == title for b in blocks):
            out = [
                new_block if b["title"] == title else render_block(b["heading"], b["body"])
                for b in blocks
            ]
            result = "\n".join(x.strip("\n") for x in out if x.strip("\n")) + "\n"
            f.write_text(result, encoding="utf-8")
        else:
            f.write_text(text.rstrip("\n") + "\n\n" + new_block, encoding="utf-8")
    else:
        f.write_text(new_block, encoding="utf-8")

    return {"title": title, "ok": True}


def delete_article(year: str, title: str) -> bool:
    """删除一篇。返回是否删除成功。"""
    f = article_file(year)
    if not f.exists():
        return False
    text = f.read_text(encoding="utf-8")
    blocks = split_articles(text)
    if not any(b["title"] == title for b in blocks):
        return False
    out = [render_block(b["heading"], b["body"]) for b in blocks if b["title"] != title]
    result = "\n".join(x.strip("\n") for x in out if x.strip("\n")) + "\n"
    f.write_text(result, encoding="utf-8")
    return True
