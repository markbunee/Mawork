"""日程任务业务逻辑：扁平表格的 CRUD、统计与 Excel 导出。

约定（本次改版）：
- 「一级计划」（level1）为分类列，「任务名」（title）是其下的具体任务；
- 不再有日 / 周 / 月度计划类型（月 / 周计划改由日历模块的独立文本承担）；
- 状态三态「未完成 / 进行中 / 已完成」完全由用户手动维护，不做基于日期的自动流转；
- 完成度为用户手填的 0-100 整数，与状态互不联动；
- 列表一律按结束日期升序排序（无结束日期的排最后）。
"""

import io
import sqlite3
from typing import Optional

from .. import config, db
from ..models.planpool import (
    COMPLETION_MAX,
    COMPLETION_MIN,
    DEFAULT_COMPLETION,
    DEFAULT_PROGRESS,
    PROGRESS_DONE,
    PROGRESS_DOING,
    PROGRESS_OPTIONS,
    PROGRESS_TODO,
)

# 无结束日期的任务排在最后
ORDER_BY_SQL = "ORDER BY CASE WHEN end_date = '' THEN 1 ELSE 0 END, end_date, id"


def _get_conn() -> sqlite3.Connection:
    return db.get_conn(config.PLANPOOL_DB)


# ---------------------------------------------------------------------------
# 字段规范化
# ---------------------------------------------------------------------------
def norm_progress(progress: str) -> str:
    """非法状态回落为默认「未完成」。"""
    return progress if progress in PROGRESS_OPTIONS else DEFAULT_PROGRESS


def norm_completion(value: object) -> int:
    """完成度规范到 0-100 的整数，非法值回落为 0。"""
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_COMPLETION
    return max(COMPLETION_MIN, min(COMPLETION_MAX, n))


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["progress"] = norm_progress(d.get("progress", ""))
    d["completion"] = norm_completion(d.get("completion"))
    return d


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def create_task(
    level1: str,
    title: str,
    progress: str,
    completion: object,
    note: str,
    start_date: str,
    end_date: str,
) -> dict:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (level1, title, progress, completion, note, start_date, end_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                level1 or "",
                title,
                norm_progress(progress),
                norm_completion(completion),
                note,
                start_date,
                end_date,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_tasks(month: Optional[str] = None) -> list[dict]:
    """列出任务，按结束日期升序排序（无结束日期的排最后）。

    month 为 'YYYY-MM'，仅返回在该月内活动的任务；为空则返回全部。
    """
    conn = _get_conn()
    try:
        if month:
            first_day = f"{month}-01"
            y, m = int(month[:4]), int(month[5:7])
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            next_month = f"{ny:04d}-{nm:02d}-01"
            rows = conn.execute(
                "SELECT * FROM tasks WHERE "
                "(start_date = '' OR start_date < ?) AND "
                "(end_date = '' OR end_date >= ?) " + ORDER_BY_SQL,
                (next_month, first_day),
            ).fetchall()
        else:
            rows = conn.execute(f"SELECT * FROM tasks {ORDER_BY_SQL}").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_task(tid: int) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
        return _row_to_dict(row) if row is not None else None
    finally:
        conn.close()


def update_task(
    tid: int,
    level1: str,
    title: str,
    progress: str,
    completion: object,
    note: str,
    start_date: str,
    end_date: str,
) -> Optional[dict]:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE tasks SET level1=?, title=?, progress=?, completion=?, note=?, "
            "start_date=?, end_date=?, updated_at=datetime('now','localtime') "
            "WHERE id=?",
            (
                level1 or "",
                title,
                norm_progress(progress),
                norm_completion(completion),
                note,
                start_date,
                end_date,
                tid,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def delete_task(tid: int) -> bool:
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (tid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
def stats(month: Optional[str] = None) -> dict:
    """按用户手动设定的状态统计数量。"""
    tasks = list_tasks(month=month)
    counts = {p: 0 for p in (PROGRESS_DONE, PROGRESS_TODO, PROGRESS_DOING)}
    for t in tasks:
        counts[t["progress"]] = counts.get(t["progress"], 0) + 1
    return {
        "total": len(tasks),
        "done": counts[PROGRESS_DONE],
        "todo": counts[PROGRESS_TODO],
        "doing": counts[PROGRESS_DOING],
    }


# ---------------------------------------------------------------------------
# Excel 导出
# ---------------------------------------------------------------------------
def _task_month(t: dict) -> str:
    """任务归属月份（YYYY-MM），优先用结束日期，无日期归为「未排期」。"""
    d = t.get("end_date") or t.get("start_date") or ""
    return d[:7] if len(d) >= 7 else "未排期"


def export_excel() -> bytes:
    """导出任务为 Excel，按月份分 sheet，极简网格、无状态配色。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise RuntimeError("缺少 openpyxl，请先安装：pip install openpyxl")

    tasks = list_tasks()

    by_month: dict[str, list[dict]] = {}
    for t in tasks:
        by_month.setdefault(_task_month(t), []).append(t)
    ordered_months = sorted(by_month.keys(), key=lambda m: (m != "未排期", m))

    wb = Workbook()
    wb.remove(wb.active)

    headers = ["一级计划", "任务", "状态", "完成度", "备注", "开始日期", "结束日期"]
    widths = [22, 34, 10, 10, 40, 14, 14]

    thin = Side(style="thin", color="D9D5CC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def fill_sheet(ws, month_label: str, month_tasks: list[dict]):
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        title_cell = ws.cell(row=1, column=1, value=f"MaWork 日程 · {month_label}")
        title_cell.font = Font(size=14, bold=True)
        title_cell.alignment = Alignment(horizontal="center")
        ws.row_dimensions[1].height = 24

        header_fill = PatternFill("solid", fgColor="F3F1EC")
        for col, h in enumerate(headers, start=1):
            c = ws.cell(row=2, column=col, value=h)
            c.font = Font(bold=True)
            c.fill = header_fill
            c.border = border
            c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 20

        for i, t in enumerate(month_tasks, start=3):
            values = [
                t.get("level1", ""),
                t["title"],
                t["progress"],
                f"{t['completion']}%",
                t["note"],
                t["start_date"],
                t["end_date"],
            ]
            for col, v in enumerate(values, start=1):
                c = ws.cell(row=i, column=col, value=v)
                c.border = border
                # 第 5 列是备注，多行时自动换行
                c.alignment = Alignment(vertical="center", wrap_text=(col == 5))
            # 多行备注自动撑高（避免截断显示，最多 14 行）
            lines = min((t["note"] or "").count("\n") + 1, 14)
            ws.row_dimensions[i].height = 18 if lines == 1 else 18 * lines

        for col, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(col)].width = w
        ws.freeze_panes = "A3"

    for month in ordered_months:
        ws = wb.create_sheet(title=str(month))
        fill_sheet(ws, str(month), by_month[month])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
