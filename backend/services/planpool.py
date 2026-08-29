"""日程任务业务逻辑：CRUD、自动状态流转、统计、Excel 导出。"""

import io
import sqlite3
from datetime import date as date_cls
from typing import Optional

from .. import config, db
from ..models.planpool import (
    MANUAL_PROGRESS,
    PROGRESS_COLORS,
    PROGRESS_DONE,
    PROGRESS_DOING,
    PROGRESS_ON_HOLD,
    PROGRESS_TODO,
)


def _get_conn() -> sqlite3.Connection:
    return db.get_conn(config.PLANPOOL_DB)


# ---------------------------------------------------------------------------
# 状态流转
# ---------------------------------------------------------------------------
def _display_progress(progress: str, start_date: str, end_date: str, today: date_cls) -> str:
    """根据今天日期动态计算实际展示状态。

    规则：
    - 手动状态（完成/搁置）保留不动
    - 否则：结束日期已过 → 未完成
    - 否则：开始日期已到（≤今天）→ 进行中
    - 否则：保持未完成
    """
    if progress in MANUAL_PROGRESS:
        return progress

    def parse(s: str) -> Optional[date_cls]:
        try:
            return date_cls.fromisoformat(s) if s else None
        except ValueError:
            return None

    end = parse(end_date)
    start = parse(start_date)

    if end is not None and end < today:
        return PROGRESS_TODO
    if start is not None and start <= today:
        return PROGRESS_DOING
    return PROGRESS_TODO


def _total_days(start_date: str, end_date: str) -> int:
    """任务总天数（含首尾）。无效或无跨度返回 0。"""
    try:
        s = date_cls.fromisoformat(start_date) if start_date else None
        e = date_cls.fromisoformat(end_date) if end_date else None
    except ValueError:
        return 0
    if s is None or e is None:
        return 0
    days = (e - s).days + 1
    return max(days, 0)


def _row_to_dict(row: sqlite3.Row, today: date_cls, checkins: set[str] | None = None) -> dict:
    d = dict(row)
    d["display_progress"] = _display_progress(d["progress"], d["start_date"], d["end_date"], today)
    checkins = checkins or set()
    d["checkins"] = sorted(checkins)
    total = _total_days(d["start_date"], d["end_date"])
    if total > 0:
        done = len(checkins)
        d["completion"] = round(done / total * 100)
    else:
        d["completion"] = None  # 单日或无日期任务无完成度
    return d


def _load_checkins(conn: sqlite3.Connection) -> dict[int, set[str]]:
    """加载全部打卡：task_id -> set(date)。"""
    rows = conn.execute("SELECT task_id, date FROM task_checkins").fetchall()
    result: dict[int, set[str]] = {}
    for r in rows:
        result.setdefault(r["task_id"], set()).add(r["date"])
    return result


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def create_task(level1: str, level2: str, progress: str, note: str, start_date: str, end_date: str) -> dict:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (level1, level2, progress, note, start_date, end_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (level1, level2, progress, note, start_date, end_date),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row, date_cls.today())
    finally:
        conn.close()


def list_tasks(month: str | None = None) -> list[dict]:
    """列出任务，按一级任务 → 开始日期排序，附带展示状态。

    month 为 'YYYY-MM'，仅返回在该月内活动（跨月覆盖或开始于该月）的任务；
    为空则返回全部。
    """
    conn = _get_conn()
    try:
        if month:
            # 任务在该月活动：start_date 早于下月第一天 且 (end_date 为空 或 end_date 不早于当月第一天)
            first_day = f"{month}-01"
            y, m = int(month[:4]), int(month[5:7])
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            next_month = f"{ny:04d}-{nm:02d}-01"
            rows = conn.execute(
                "SELECT * FROM tasks WHERE "
                "(start_date = '' OR start_date < ?) AND "
                "(end_date = '' OR end_date >= ?) "
                "ORDER BY level1, start_date, id",
                (next_month, first_day),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY level1, start_date, id"
            ).fetchall()
        checkins = _load_checkins(conn)
        today = date_cls.today()
        return [
            _row_to_dict(r, today, checkins.get(r["id"], set())) for r in rows
        ]
    finally:
        conn.close()


def get_task(tid: int) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
        if row is None:
            return None
        checkins = _load_checkins(conn).get(tid, set())
        return _row_to_dict(row, date_cls.today(), checkins)
    finally:
        conn.close()


def update_task(
    tid: int,
    level1: str,
    level2: str,
    progress: str,
    note: str,
    start_date: str,
    end_date: str,
) -> dict | None:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE tasks SET level1=?, level2=?, progress=?, note=?, "
            "start_date=?, end_date=?, updated_at=datetime('now','localtime') "
            "WHERE id=?",
            (level1, level2, progress, note, start_date, end_date, tid),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
        return _row_to_dict(row, date_cls.today())
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


def checkin(task_id: int, date: str) -> dict | None:
    """为某任务在某天打卡。任务不存在返回 None。"""
    conn = _get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if exists is None:
            return None
        conn.execute(
            "INSERT OR IGNORE INTO task_checkins (task_id, date) VALUES (?, ?)",
            (task_id, date),
        )
        conn.commit()
        checkins = _load_checkins(conn).get(task_id, set())
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_dict(row, date_cls.today(), checkins)
    finally:
        conn.close()


def uncheckin(task_id: int, date: str) -> dict | None:
    """取消某天的打卡。任务不存在返回 None。"""
    conn = _get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if exists is None:
            return None
        conn.execute(
            "DELETE FROM task_checkins WHERE task_id = ? AND date = ?",
            (task_id, date),
        )
        conn.commit()
        checkins = _load_checkins(conn).get(task_id, set())
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_dict(row, date_cls.today(), checkins)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
def stats(month: str | None = None) -> dict:
    """统计各状态数量（基于展示状态，而非原始状态）。month 为空统计全部。"""
    tasks = list_tasks(month=month)
    counts = {p: 0 for p in (PROGRESS_DONE, PROGRESS_TODO, PROGRESS_DOING, PROGRESS_ON_HOLD)}
    for t in tasks:
        dp = t.get("display_progress")
        if dp in counts:
            counts[dp] += 1
    return {
        "total": len(tasks),
        "done": counts[PROGRESS_DONE],
        "todo": counts[PROGRESS_TODO],
        "doing": counts[PROGRESS_DOING],
        "on_hold": counts[PROGRESS_ON_HOLD],
    }


# ---------------------------------------------------------------------------
# Excel 导出
# ---------------------------------------------------------------------------
def _task_month(t: dict) -> str:
    """任务归属月份（YYYY-MM），无开始日期归为"未排期"。"""
    d = t.get("start_date") or ""
    if len(d) >= 7:
        return d[:7]
    return "未排期"


def export_excel() -> bytes:
    """导出任务为 Excel，按月份分 sheet（一个月一个子表）。

    每个子表：标题 + 表头 + 状态色背景 + 冻结首行。
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise RuntimeError("缺少 openpyxl，请先安装：pip install openpyxl")

    tasks = list_tasks()

    # 按月份分组（保持月份顺序）
    by_month: dict[str, list[dict]] = {}
    for t in tasks:
        by_month.setdefault(_task_month(t), []).append(t)
    ordered_months = sorted(by_month.keys(), key=lambda m: (m != "未排期", m))

    wb = Workbook()
    wb.remove(wb.active)  # 移除默认 sheet

    headers = ["一级任务", "二级任务", "进度", "备注", "开始日期", "结束日期"]
    widths = [20, 24, 12, 40, 14, 14]

    def fill_sheet(ws, month_label: str, month_tasks: list[dict]):
        # 标题
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
        title_cell = ws.cell(row=1, column=1, value=f"MaWork 日程计划 · {month_label}")
        title_cell.font = Font(size=14, bold=True)
        title_cell.alignment = Alignment(horizontal="center")
        ws.row_dimensions[1].height = 24

        # 表头
        header_fill = PatternFill("solid", fgColor="9A8C72")
        for col, h in enumerate(headers, start=1):
            c = ws.cell(row=2, column=col, value=h)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = header_fill
            c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 20

        # 数据
        for i, t in enumerate(month_tasks, start=3):
            values = [t["level1"], t["level2"], t["display_progress"], t["note"], t["start_date"], t["end_date"]]
            for col, v in enumerate(values, start=1):
                c = ws.cell(row=i, column=col, value=v)
                c.alignment = Alignment(vertical="center", wrap_text=(col == 4))
            color = PROGRESS_COLORS.get(t["display_progress"], PROGRESS_COLORS[PROGRESS_TODO])
            fill = PatternFill("solid", fgColor=color["bg"].lstrip("#"))
            ws.cell(row=i, column=3).fill = fill
            ws.row_dimensions[i].height = 18

        for col, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(col)].width = w
        ws.freeze_panes = "A3"

    for month in ordered_months:
        ws = wb.create_sheet(title=str(month))
        fill_sheet(ws, str(month), by_month[month])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
