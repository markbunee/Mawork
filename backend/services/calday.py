"""日历文本格业务逻辑。

每一天是一块可直接输入的文本方格，逐行存储（text / task 两类）。
日报已入库，日历任务行不再写进 Markdown，只在日报「查看 / 导出」时被
注入到当日「一、今日工作内容」段展示。

与日报的双向关系：
- 日历任务行（manual）→ 日报查看时展示在当日「今日工作内容」上方；
- 日报「三、明日工作计划」条目 → 自动写入次日日历（source=daily_plan，
  真源在日报，保存日报时重建；文本未变的行保留用户勾选的完成状态）。

另有两块独立的自由文本，只由用户自己书写、不与日报互相同步：
- 月度计划：按月（YYYY-MM）一块，展示在日历上方；
- 周计划：按该周周一日期（YYYY-MM-DD）一块，展示在日历左侧列。
"""

import re
import sqlite3
from datetime import date as _date, timedelta

from .. import config, db
from ..models.calday import (
    DONE_PREFIX,
    KIND_OPTIONS,
    KIND_TEXT,
    SOURCE_MANUAL,
    SOURCE_PLAN,
    TODO_PREFIX,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _get_conn() -> sqlite3.Connection:
    return db.get_conn(config.PLANPOOL_DB)


def _line_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "date": row["date"],
        "sort": row["sort_order"],
        "kind": row["kind"] if row["kind"] in KIND_OPTIONS else KIND_TEXT,
        "text": row["content"],
        "done": bool(row["done"]),
        "source": row["source"] if row["source"] in (SOURCE_MANUAL, SOURCE_PLAN) else SOURCE_MANUAL,
        "source_ref": row["source_ref"] or "",
    }


def add_days(date: str, n: int) -> str:
    """日期加 n 天，返回 YYYY-MM-DD。"""
    y, m, d = map(int, date.split("-"))
    return (_date(y, m, d) + timedelta(days=n)).isoformat()


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
def list_days(from_date: str, to_date: str) -> dict[str, list[dict]]:
    """按日期区间取出日历文本行：{date: [line, ...]}。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM calendar_lines WHERE date >= ? AND date <= ? "
            "ORDER BY date, sort_order, id",
            (from_date, to_date),
        ).fetchall()
        days: dict[str, list[dict]] = {}
        for r in rows:
            days.setdefault(r["date"], []).append(_line_dict(r))
        return days
    finally:
        conn.close()


def get_tasks(date: str) -> list[dict]:
    """某一天的任务行（供日报页展示「来自日历的任务」）。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM calendar_lines WHERE date = ? AND kind = 'task' "
            "AND trim(content) <> '' ORDER BY sort_order, id",
            (date,),
        ).fetchall()
        return [_line_dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 写入：整段覆盖，带来源继承
# ---------------------------------------------------------------------------
def save_day(date: str, incoming: list[dict]) -> dict:
    """整段覆盖某一天的文本行。

    前端提交的行不含来源信息，用「文本 + 类型」与库中旧行匹配，
    让自动任务行（daily_plan）保留其来源标记，避免下一轮同步失控。
    """
    conn = _get_conn()
    try:
        old_rows = conn.execute(
            "SELECT * FROM calendar_lines WHERE date = ?", (date,)
        ).fetchall()
        # 旧行的来源查找表：{kind: {text: (source, source_ref)}}
        old_src: dict[str, dict[str, tuple[str, str]]] = {}
        for r in old_rows:
            src = (
                r["source"] if r["source"] in (SOURCE_MANUAL, SOURCE_PLAN) else SOURCE_MANUAL
            )
            old_src.setdefault(r["kind"], {}).setdefault(r["content"], (src, r["source_ref"] or ""))

        conn.execute("DELETE FROM calendar_lines WHERE date = ?", (date,))
        for i, raw in enumerate(incoming):
            kind = raw.get("kind") if raw.get("kind") in KIND_OPTIONS else KIND_TEXT
            content = str(raw.get("text") or "").replace("\r", " ").replace("\n", " ").strip()
            if not content:
                continue
            # 继承来源：同样的行曾是自动任务则继续保持，避免被 next 同步重建删除
            src, sref = old_src.get(kind, {}).get(content, (SOURCE_MANUAL, ""))
            conn.execute(
                "INSERT INTO calendar_lines (date, sort_order, kind, content, done, source, source_ref) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (date, i, kind, content, 1 if raw.get("done") else 0, src, sref),
            )

        rows = conn.execute(
            "SELECT * FROM calendar_lines WHERE date = ? ORDER BY sort_order, id",
            (date,),
        ).fetchall()
        lines = [_line_dict(r) for r in rows]
        conn.commit()
        return {"date": date, "lines": lines, "synced": 0}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 日报「明日工作计划」→ 次日日历（真源在日报）
# ---------------------------------------------------------------------------
def sync_plan_to_calendar(source_date: str, items: list[str]) -> int:
    """把某天日报的明日计划写入次日日历。

    规则（幂等）：
    - 只重建 next_date 下 source='daily_plan' 且 source_ref=source_date 的行；
    - 文本未变的行继承用户勾选的完成状态；文本已变的以日报为准。
    - 日报里删掉的条目，对应行会被删除。
    返回写入条数。
    """
    if not DATE_RE.match(source_date):
        return 0
    next_date = add_days(source_date, 1)
    conn = _get_conn()
    try:
        # 取旧行的完成状态（按文本），用于继承勾选
        old = conn.execute(
            "SELECT content, done FROM calendar_lines "
            "WHERE date = ? AND source = ? AND source_ref = ?",
            (next_date, SOURCE_PLAN, source_date),
        ).fetchall()
        done_by_text: dict[str, bool] = {}
        for r in old:
            done_by_text[r["content"]] = bool(r["done"])

        conn.execute(
            "DELETE FROM calendar_lines WHERE date = ? AND source = ? AND source_ref = ?",
            (next_date, SOURCE_PLAN, source_date),
        )

        count = 0
        for i, item in enumerate(items):
            text = (item or "").strip()
            if not text:
                continue
            conn.execute(
                "INSERT INTO calendar_lines "
                "(date, sort_order, kind, content, done, source, source_ref) "
                "VALUES (?, ?, 'task', ?, ?, ?, ?)",
                (
                    next_date,
                    i,
                    text,
                    1 if done_by_text.get(text, False) else 0,
                    SOURCE_PLAN,
                    source_date,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def render_task_lines(date: str) -> list[str]:
    """把某天任务行渲染成「已完成-内容 / 未完成-内容」列表（日报查看 / 导出用）。"""
    out: list[str] = []
    for t in get_tasks(date):
        prefix = DONE_PREFIX if t["done"] else TODO_PREFIX
        out.append(f"{prefix}{t['text']}")
    return out


# ---------------------------------------------------------------------------
# 月度计划：日历上方的一整块自由文本（YYYY-MM）
# ---------------------------------------------------------------------------
def get_month_note(month: str) -> dict:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT month, content FROM calendar_month_notes WHERE month = ?", (month,)
        ).fetchone()
        return {"month": month, "content": row["content"] if row else ""}
    finally:
        conn.close()


def save_month_note(month: str, content: str) -> dict:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO calendar_month_notes (month, content, updated_at) "
            "VALUES (?, ?, datetime('now', 'localtime')) "
            "ON CONFLICT(month) DO UPDATE SET "
            "content = excluded.content, updated_at = datetime('now', 'localtime')",
            (month, content or ""),
        )
        conn.commit()
        return {"month": month, "content": content or ""}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 周计划：日历左侧一列，按该周周一日期（YYYY-MM-DD）存一块
# ---------------------------------------------------------------------------
def list_week_notes(from_date: str, to_date: str) -> dict[str, str]:
    """取出 [from, to] 区间内各周一的周计划：{week_start: content}。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT week_start, content FROM calendar_week_notes "
            "WHERE week_start >= ? AND week_start <= ? ORDER BY week_start",
            (from_date, to_date),
        ).fetchall()
        return {r["week_start"]: r["content"] for r in rows}
    finally:
        conn.close()


def save_week_note(week_start: str, content: str) -> dict:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO calendar_week_notes (week_start, content, updated_at) "
            "VALUES (?, ?, datetime('now', 'localtime')) "
            "ON CONFLICT(week_start) DO UPDATE SET "
            "content = excluded.content, updated_at = datetime('now', 'localtime')",
            (week_start, content or ""),
        )
        conn.commit()
        return {"week_start": week_start, "content": content or ""}
    finally:
        conn.close()
