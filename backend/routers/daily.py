"""日报路由：读写字盘上的 Markdown 日报文件。"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config

router = APIRouter(prefix="/api/daily", tags=["daily"])

# 日报标题正则：## 日报_马炫轩：2026.08.25
HEADING_RE = re.compile(r"^##\s*日报_.*?[：:]\s*(\d{4}\.\d{2}\.\d{2})\s*$")
# 一级标题正则：月份/复盘分组标题
MONTH_RE = re.compile(r"^#\s+(.+?)\s*$")


def daily_file(year: str) -> Path:
    return config.WORKSPACES_DIR / year / "daily.md"


def split_daily_tree(text: str) -> list[dict]:
    """按一级标题 + 二级标题解析为分组树。

    结构：
    # 06月
    ## 日报_马炫轩:2026.06.07
    ...
    # 06月工作复盘&07月工作指导
    正文（无日期）
    ...
    返回：[{title, dates: [date,...]}]，title 为一级标题文本。
    """
    groups: list[dict] = []
    current_group = None
    current_date = None

    for line in text.splitlines():
        s = line.strip()
        m1 = MONTH_RE.match(s)
        if m1:
            current_group = {"title": m1.group(1).strip(), "dates": []}
            groups.append(current_group)
            current_date = None
            continue
        m2 = HEADING_RE.match(s)
        if m2 and current_group is not None:
            date = m2.group(1)
            if date not in current_group["dates"]:
                current_group["dates"].append(date)
            current_date = date
            continue

    return groups


def split_daily(text: str) -> list[dict]:
    """按 ## 标题切块，返回 [{date, heading, body}]。"""
    lines = text.splitlines()
    blocks: list[dict] = []
    current = None
    for line in lines:
        m = HEADING_RE.match(line.strip())
        if m:
            if current is not None:
                blocks.append(current)
            current = {"date": m.group(1), "heading": line.strip(), "body": []}
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


@router.get("/years")
def list_years():
    """列出含日报文件的年份文件夹。"""
    if not config.WORKSPACES_DIR.exists():
        return {"years": []}
    years = []
    for d in sorted(config.WORKSPACES_DIR.iterdir(), reverse=True):
        if d.is_dir() and (d / "daily.md").exists():
            years.append(d.name)
    return {"years": years}


@router.get("/{year}")
def list_daily(year: str):
    """返回按一级标题分组的日报树。"""
    f = daily_file(year)
    if not f.exists():
        return {"year": year, "groups": []}
    groups = split_daily_tree(f.read_text(encoding="utf-8"))
    return {"year": year, "groups": groups}


@router.get("/{year}/{date}")
def get_daily(year: str, date: str):
    f = daily_file(year)
    if not f.exists():
        raise HTTPException(status_code=404, detail="日报文件不存在")
    for b in split_daily(f.read_text(encoding="utf-8")):
        if b["date"] == date:
            return {"date": date, "heading": b["heading"], "body": b["body"]}
    raise HTTPException(status_code=404, detail="该日期无日报")


class DailyPayload(BaseModel):
    body: str = ""


@router.put("/{year}/{date}")
def upsert_daily(year: str, date: str, payload: DailyPayload):
    f = daily_file(year)
    f.parent.mkdir(parents=True, exist_ok=True)

    heading = f"## 日报_{config.AUTHOR}：{date}"
    new_block = render_block(heading, payload.body)

    if f.exists():
        text = f.read_text(encoding="utf-8")
        blocks = split_daily(text)
        if any(b["date"] == date for b in blocks):
            out = [
                new_block if b["date"] == date else render_block(b["heading"], b["body"])
                for b in blocks
            ]
            result = "\n".join(x.strip("\n") for x in out if x.strip("\n")) + "\n"
            f.write_text(result, encoding="utf-8")
        else:
            f.write_text(text.rstrip("\n") + "\n\n" + new_block, encoding="utf-8")
    else:
        f.write_text(new_block, encoding="utf-8")

    return {"date": date, "ok": True}
