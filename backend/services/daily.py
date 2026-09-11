"""日报业务逻辑（daily.db 为唯一真源）。

- 整篇正文按行首「一、xxx / 二、xxx …」切成段落（daily_sections），
  段落标题写法不统一，用 section_key 归一化供查询 / 展示 / 导出；
- 正文与日历任务行是两份独立真源：日历任务（calendar_lines）在
  「查看 / 导出」日报时注入到当日「今日工作内容」段开头；
- 保存日报时，正文「三、明日工作计划」段的条目会自动写入次日日历
  （见 calday.sync_plan_to_calendar）。
"""

import re
import sqlite3

from .. import config, db
from ..models.daily import (
    DAILY_HEADING_RE,
    KEY_ISSUE,
    KEY_OTHER,
    KEY_PLAN,
    KEY_WORK,
)
from . import calday

# 段标题：行首形如「一、xxx」
SEC_TITLE_RE = re.compile(r"^\s*[一二三四五六七八九十百]{1,3}、\s*\S")
# 计划条目前缀：1. / 1、 / - / [x] 等
ITEM_PREFIX_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.、)）]|\[[ xX]\])\s*")


def _get_conn() -> sqlite3.Connection:
    return db.get_conn(config.DAILY_DB)


# ---------------------------------------------------------------------------
# 段落解析 / 归一化
# ---------------------------------------------------------------------------
def section_key_of(heading: str) -> str:
    """把段落标题归一到 work / issue / plan / other。"""
    h = heading or ""
    if "今日工作" in h or "今日所做" in h:
        return KEY_WORK
    if "问题反馈" in h or "问题与" in h or "问题及" in h:
        return KEY_ISSUE
    if "明日" in h or "明天" in h:
        return KEY_PLAN
    return KEY_OTHER


def parse_sections(body: str) -> list[dict]:
    """把日报正文切成 [{heading, key, body}]。"""
    sections: list[dict] = []
    cur: dict | None = None
    for raw in (body or "").split("\n"):
        if SEC_TITLE_RE.match(raw):
            if cur is not None:
                sections.append(cur)
            cur = {"heading": raw.strip(), "key": section_key_of(raw), "lines": []}
        else:
            if cur is None:
                cur = {"heading": "", "key": KEY_OTHER, "lines": []}
            cur["lines"].append(raw)
    if cur is not None:
        sections.append(cur)
    return [
        {"heading": s["heading"], "key": s["key"], "body": "\n".join(s["lines"]).strip("\n")}
        for s in sections
    ]


def join_sections(sections: list[dict]) -> str:
    """段落列表拼回整篇正文（标题与正文间空一行，段间空两行）。"""
    parts: list[str] = []
    for s in sections:
        heading = (s.get("heading") or "").strip()
        body = (s.get("body") or "").strip("\n")
        if not heading and not body:
            continue
        if heading and body:
            parts.append(f"{heading}\n\n{body}")
        elif heading:
            parts.append(heading)
        else:
            parts.append(body)
    return "\n\n".join(parts).strip("\n")


def extract_plan_items(body: str) -> list[str]:
    """从正文里取「明日工作计划」段的条目（去掉列表前缀与空行）。"""
    items: list[str] = []
    for sec in parse_sections(body):
        if sec["key"] != KEY_PLAN:
            continue
        for raw in sec["body"].split("\n"):
            t = ITEM_PREFIX_RE.sub("", raw).strip()
            if t:
                items.append(t)
    return items


# ---------------------------------------------------------------------------
# 增删改查
# ---------------------------------------------------------------------------
def list_years() -> list[str]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT year FROM daily_entries ORDER BY year DESC"
        ).fetchall()
        return [str(r["year"]) for r in rows]
    finally:
        conn.close()


def list_groups(year: int) -> list[dict]:
    """按月份自动分组：[{title: "07月", dates: [...]}]。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT date FROM daily_entries WHERE year = ? ORDER BY date",
            (year,),
        ).fetchall()
    finally:
        conn.close()
    groups: list[dict] = []
    cur: dict | None = None
    for r in rows:
        month = r["date"][5:7]
        if cur is None or cur["title"] != f"{month}月":
            cur = {"title": f"{month}月", "dates": []}
            groups.append(cur)
        cur["dates"].append(r["date"])
    return groups


def get_entry(date: str) -> dict | None:
    """取一篇日报；正文为空的条目返回空段列表。"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM daily_entries WHERE date = ?", (date,)
        ).fetchone()
        if row is None:
            return None
        sec_rows = conn.execute(
            "SELECT heading, section_key, body FROM daily_sections "
            "WHERE entry_id = ? ORDER BY sort_order",
            (row["id"],),
        ).fetchall()
        sections = [
            {"heading": s["heading"], "key": s["section_key"], "body": s["body"]}
            for s in sec_rows
        ]
        return {
            "date": row["date"],
            "heading": row["heading"],
            "body": row["body"],
            "sections": sections,
        }
    finally:
        conn.close()


def upsert_entry(date: str, body: str) -> dict:
    """保存一篇日报正文，并触发「明日工作计划 → 次日日历」同步。"""
    body = (body or "").strip("\n")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError(f"非法日期：{date}")
    year, month = int(date[:4]), int(date[5:7])
    heading = f"## 日报_{config.AUTHOR}：{date.replace('-', '.')}"
    sections = parse_sections(body)

    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM daily_entries WHERE date = ?", (date,)
        ).fetchone()
        if row:
            entry_id = row["id"]
            conn.execute(
                "UPDATE daily_entries SET body = ?, heading = ?, updated_at = "
                "datetime('now', 'localtime') WHERE id = ?",
                (body, heading, entry_id),
            )
            conn.execute("DELETE FROM daily_sections WHERE entry_id = ?", (entry_id,))
        else:
            cur = conn.execute(
                "INSERT INTO daily_entries (date, year, month, heading, body) "
                "VALUES (?, ?, ?, ?, ?)",
                (date, year, month, heading, body),
            )
            entry_id = cur.lastrowid
        for i, sec in enumerate(sections):
            conn.execute(
                "INSERT INTO daily_sections (entry_id, sort_order, heading, section_key, body) "
                "VALUES (?, ?, ?, ?, ?)",
                (entry_id, i, sec["heading"], sec["key"], sec["body"]),
            )
        conn.commit()
    finally:
        conn.close()

    # 「三、明日工作计划」→ 次日日历（独立于正文事务）
    plan_synced = calday.sync_plan_to_calendar(date, extract_plan_items(body))
    return {"ok": True, "date": date, "plan_synced": plan_synced}


def render_entry_text(date: str) -> str:
    """把一篇日报渲染成 Markdown 文本（日历任务注入「今日工作内容」前）。"""
    entry = get_entry(date)
    if entry is None:
        return ""
    task_lines = calday.render_task_lines(date)
    sections = entry["sections"] or []
    rendered: list[dict] = []
    for sec in sections:
        out = dict(sec)
        if sec["key"] == KEY_WORK and task_lines:
            injected = "\n".join(task_lines)
            out["body"] = injected if not sec["body"].strip() else f"{injected}\n{sec['body'].strip()}"
            task_lines = []
        rendered.append(out)
    # 没有 work 段但有日历任务：补一段
    if task_lines:
        rendered = [
            {"heading": "一、今日工作内容", "key": KEY_WORK, "body": "\n".join(task_lines)}
        ] + rendered
    body = join_sections(rendered)
    return f"{entry['heading']}\n\n{body}" if body else entry["heading"]


def export_year(year: int) -> str:
    """导出某年全部日报为 Markdown（按月分组、含日历任务注入）。"""
    parts: list[str] = []
    for group in list_groups(year):
        parts.append(f"# {group['title']}")
        for date in group["dates"]:
            text = render_entry_text(date)
            if text:
                parts.append("")
                parts.append(text)
    return "\n".join(parts).strip() + "\n"


# ---------------------------------------------------------------------------
# 历史 Markdown 一次性导入（幂等，按 date 唯一）
# ---------------------------------------------------------------------------
def import_legacy_md() -> int:
    """扫描 workspaces/{year}/daily.md / Daily.md，把存量日报导入 daily.db。

    返回新导入篇数；已存在于库中的日期跳过。原文件保留不动。
    """
    if not config.WORKSPACES_DIR.exists():
        return 0
    heading_re = re.compile(DAILY_HEADING_RE)
    imported = 0
    year_dirs = sorted(
        d
        for d in config.WORKSPACES_DIR.iterdir()
        if d.is_dir() and len(d.name) == 4 and d.name.isdigit()
    )
    for ydir in year_dirs:
        for name in ("daily.md", "Daily.md"):
            f = ydir / name
            if not f.exists():
                continue
            blocks: list[tuple[str, str]] = []  # (date, body)
            cur_date: str | None = None
            cur_lines: list[str] = []
            for ln in f.read_text(encoding="utf-8").splitlines():
                m = heading_re.match(ln.strip())
                if m:
                    if cur_date is not None:
                        blocks.append((cur_date, "\n".join(cur_lines)))
                    cur_date = (
                        f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                    )
                    cur_lines = []
                elif cur_date is not None:
                    cur_lines.append(ln)
            if cur_date is not None:
                blocks.append((cur_date, "\n".join(cur_lines)))

            conn = _get_conn()
            try:
                for date, raw_body in blocks:
                    body = raw_body.strip("\n")
                    if not body:
                        continue
                    exists = conn.execute(
                        "SELECT 1 FROM daily_entries WHERE date = ?", (date,)
                    ).fetchone()
                    if exists:
                        continue
                    _insert_entry(conn, date, body)
                    imported += 1
                conn.commit()
            finally:
                conn.close()
    return imported


def _insert_entry(conn: sqlite3.Connection, date: str, body: str) -> None:
    """建库阶段的内部写入（不含次日日历同步）。"""
    year, month = int(date[:4]), int(date[5:7])
    heading = f"## 日报_{config.AUTHOR}：{date.replace('-', '.')}"
    sections = parse_sections(body)
    cur = conn.execute(
        "INSERT INTO daily_entries (date, year, month, heading, body) "
        "VALUES (?, ?, ?, ?, ?)",
        (date, year, month, heading, body),
    )
    entry_id = cur.lastrowid
    for i, sec in enumerate(sections):
        conn.execute(
            "INSERT INTO daily_sections (entry_id, sort_order, heading, section_key, body) "
            "VALUES (?, ?, ?, ?, ?)",
            (entry_id, i, sec["heading"], sec["key"], sec["body"]),
        )
