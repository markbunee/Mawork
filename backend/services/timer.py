"""计时器业务逻辑：四种模式的 CRUD、运行控制与耗时统计。

约定：
- 列表按 id 倒序（最新在前）；
- 正计时的开始/停止会结算本段耗时并写入 time_logs；倒计时/倒数日/正数日不写日志；
- 删除计时器时级联删除其耗时日志，保证统计干净；
- 统计按 time_logs 的冗余列 day/week/month 做 GROUP BY，零额外计算。
"""

import sqlite3
from datetime import date, datetime
from typing import Optional

from .. import config, db
from ..models.timer import (
    DEFAULT_STATUS,
    DEFAULT_TYPE,
    STATUS_ACTIVE,
    STATUS_FINISHED,
    STATUS_OPTIONS,
    STATUS_PAUSED,
    TIMER_TYPES,
    TYPE_COUNTUP,
)

# 本地时间格式：YYYY-MM-DD HH:MM:SS
_TS_FMT = "%Y-%m-%d %H:%M:%S"


def _get_conn() -> sqlite3.Connection:
    return db.get_conn(config.TIMER_DB)


def _now_local() -> str:
    return datetime.now().strftime(_TS_FMT)


def _week_key(d: date) -> str:
    """ISO 周年周键：YYYY-Www。"""
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def norm_type(type_: str) -> str:
    """非法类型回落为默认「正计时」。"""
    return type_ if type_ in TIMER_TYPES else DEFAULT_TYPE


def norm_status(status: str) -> str:
    """非法状态回落为默认「active」。"""
    return status if status in STATUS_OPTIONS else DEFAULT_STATUS


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def create_timer(
    type_: str,
    title: str,
    note: str,
    target_at: str,
    start_at: str,
    status: str = DEFAULT_STATUS,
) -> dict:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO timers (type, title, note, target_at, start_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                norm_type(type_),
                title or "",
                note or "",
                target_at or "",
                start_at or "",
                norm_status(status),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_timers(type_: Optional[str] = None) -> list[dict]:
    conn = _get_conn()
    try:
        if type_:
            rows = conn.execute(
                "SELECT * FROM timers WHERE type = ? ORDER BY id DESC", (norm_type(type_),)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM timers ORDER BY id DESC").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_timer(tid: int) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (tid,)).fetchone()
        return _row_to_dict(row) if row is not None else None
    finally:
        conn.close()


def update_timer(
    tid: int,
    type_: str,
    title: str,
    note: str,
    target_at: str,
    start_at: str,
    status: str,
) -> Optional[dict]:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE timers SET type=?, title=?, note=?, target_at=?, start_at=?, status=?, "
            "updated_at=datetime('now','localtime') WHERE id=?",
            (
                norm_type(type_),
                title or "",
                note or "",
                target_at or "",
                start_at or "",
                norm_status(status),
                tid,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (tid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def delete_timer(tid: int) -> bool:
    conn = _get_conn()
    try:
        # 级联删除关联耗时日志，保持统计干净
        conn.execute("DELETE FROM time_logs WHERE timer_id = ?", (tid,))
        cur = conn.execute("DELETE FROM timers WHERE id = ?", (tid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 运行控制（仅对正计时有意义）
# ---------------------------------------------------------------------------
def start_timer(tid: int) -> Optional[dict]:
    """开始正计时：记录当前段起点，状态置 active。其它模式忽略。"""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (tid,)).fetchone()
        if row is None:
            return None
        if row["type"] != TYPE_COUNTUP:
            return _row_to_dict(row)
        conn.execute(
            "UPDATE timers SET running_since=?, status=?, updated_at=datetime('now','localtime') "
            "WHERE id=?",
            (_now_local(), STATUS_ACTIVE, tid),
        )
        conn.commit()
        return _row_to_dict(conn.execute("SELECT * FROM timers WHERE id = ?", (tid,)).fetchone())
    finally:
        conn.close()


def stop_timer(tid: int) -> Optional[dict]:
    """停止正计时：结算本段耗时并写入 time_logs，累计到 accumulated_sec。"""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM timers WHERE id = ?", (tid,)).fetchone()
        if row is None:
            return None
        if row["type"] != TYPE_COUNTUP or not row["running_since"]:
            return _row_to_dict(row)

        start_dt = datetime.strptime(row["running_since"], _TS_FMT)
        now_dt = datetime.now()
        elapsed = int((now_dt - start_dt).total_seconds())
        if elapsed < 0:
            elapsed = 0

        end_str = now_dt.strftime(_TS_FMT)
        d = now_dt.date()
        conn.execute(
            "INSERT INTO time_logs (timer_id, title, note, start_at, end_at, duration_sec, day, week, month) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tid,
                row["title"],
                row["note"],
                row["running_since"],
                end_str,
                elapsed,
                d.isoformat(),
                _week_key(d),
                f"{d.year}-{d.month:02d}",
            ),
        )
        conn.execute(
            "UPDATE timers SET accumulated_sec=?, running_since='', status=?, "
            "updated_at=datetime('now','localtime') WHERE id=?",
            (row["accumulated_sec"] + elapsed, STATUS_PAUSED, tid),
        )
        conn.commit()
        return _row_to_dict(conn.execute("SELECT * FROM timers WHERE id = ?", (tid,)).fetchone())
    finally:
        conn.close()


def reset_timer(tid: int) -> Optional[dict]:
    """重置正计时累计（不写日志，仅清零）。"""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE timers SET accumulated_sec=0, running_since='', status=?, "
            "updated_at=datetime('now','localtime') WHERE id=? AND type=?",
            (STATUS_PAUSED, tid, TYPE_COUNTUP),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        return _row_to_dict(conn.execute("SELECT * FROM timers WHERE id = ?", (tid,)).fetchone())
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
def stats(granularity: str = "day") -> dict:
    """按日/周/月聚合耗时，并给出任务整体耗时明细。

    granularity: 'day' | 'week' | 'month'，对应 time_logs 的冗余列。
    返回：{ granularity, buckets:[{key,total_sec,sessions}], top_tasks:[{title,total_sec,sessions}], total_sec }
    """
    col = {"day": "day", "week": "week", "month": "month"}.get(granularity, "day")
    conn = _get_conn()
    try:
        bucket_rows = conn.execute(
            f"SELECT {col} AS bucket, SUM(duration_sec) AS total_sec, COUNT(*) AS sessions "
            f"FROM time_logs GROUP BY {col} ORDER BY bucket DESC"
        ).fetchall()
        buckets = [
            {
                "key": r["bucket"] or "未知",
                "total_sec": r["total_sec"],
                "sessions": r["sessions"],
            }
            for r in bucket_rows
        ]

        task_rows = conn.execute(
            "SELECT COALESCE(NULLIF(title, ''), '未命名') AS title, "
            "SUM(duration_sec) AS total_sec, COUNT(*) AS sessions "
            "FROM time_logs GROUP BY title ORDER BY total_sec DESC"
        ).fetchall()
        top_tasks = [
            {"title": r["title"], "total_sec": r["total_sec"], "sessions": r["sessions"]}
            for r in task_rows
        ]

        total = conn.execute("SELECT COALESCE(SUM(duration_sec), 0) AS s FROM time_logs").fetchone()["s"]
        return {
            "granularity": granularity,
            "buckets": buckets,
            "top_tasks": top_tasks,
            "total_sec": total,
        }
    finally:
        conn.close()
