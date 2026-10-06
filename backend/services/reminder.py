"""横切能力 E4：提醒通知（派生，无独立存储）。

聚合四个模块的「今日 / 临近」事项，全部为只读派生，不新增任何数据表：
- 习惯：今天应打卡但未打卡（habit.list_for_date）
- 日程：截止日 <= 今天 且 未完成 的任务（planpool.tasks）
- 记账：今天命中账单日的周期账模板（accounting.recurring）
- 目标：截止日 <= 今天 且 未归档 的目标（insight.goals）

返回结构与 search 一致：按模块分组，每项带 route + query 供前端跳转。
"""

from datetime import date as _date

from .. import config, db
from . import habit as habit_svc
from .common import group_by_module

_DONE_PROGRESS = "已完成"
_DATE_FMT = "%Y-%m-%d"


def _today() -> _date:
    return _date.today()


def _norm(s) -> str:
    return (s or "").strip()


def get_reminders() -> dict:
    today = _today()
    today_s = today.isoformat()
    items: list[dict] = []

    # 1) 习惯打卡：今天应打卡但未打卡
    for h in habit_svc.list_for_date(today_s):
        if h.get("expected") and not h.get("done"):
            habit = h.get("habit") or {}
            items.append(
                {
                    "module": "habit",
                    "module_label": "习惯",
                    "title": f"{habit.get('emoji', '🔴')} {habit.get('name', '')}".strip(),
                    "detail": "今天待打卡",
                    "route": "/habit",
                    "query": {},
                }
            )

    # 2) 日程任务截止：end_date <= 今天 且 未完成
    with db.open_conn(config.PLANPOOL_DB) as conn:
        rows = conn.execute(
            "SELECT id, level1, title, progress, end_date FROM tasks "
            "WHERE end_date <> '' AND end_date <= ? AND progress <> ? "
            "ORDER BY end_date",
            (today_s, _DONE_PROGRESS),
        ).fetchall()
    for r in rows:
        lvl = _norm(r["level1"])
        items.append(
            {
                "module": "planpool",
                "module_label": "日程",
                "title": r["title"] or "未命名任务",
                "detail": f"{r['progress']} · 截止 {r['end_date']}"
                + (f" · {lvl}" if lvl else ""),
                "route": "/planpool",
                "query": {},
            }
        )

    # 3) 账单日：周期账模板命中今天（day_of_month == 今天）
    with db.open_conn(config.ACCOUNTING_DB) as conn:
        rows = conn.execute(
            "SELECT id, kind, category, category2, note, day_of_month FROM recurring "
            "WHERE active = 1 AND day_of_month = ?",
            (today.day,),
        ).fetchall()
    for r in rows:
        label = _norm(r["category2"]) or _norm(r["category"])
        items.append(
            {
                "module": "accounting",
                "module_label": "记账",
                "title": f"账单日：{label}",
                "detail": _norm(r["note"]),
                "route": "/accounting",
                "query": {},
            }
        )

    # 4) 目标节点：deadline <= 今天 且 未归档
    with db.open_conn(config.INSIGHT_DB) as conn:
        rows = conn.execute(
            "SELECT id, title, category, deadline FROM goals "
            "WHERE archived = 0 AND deadline <> '' AND deadline <= ? "
            "ORDER BY deadline",
            (today_s,),
        ).fetchall()
    for r in rows:
        cat = _norm(r["category"])
        items.append(
            {
                "module": "insight",
                "module_label": "目标",
                "title": r["title"] or "未命名目标",
                "detail": f"截止 {r['deadline']}" + (f" · {cat}" if cat else ""),
                "route": "/analysis",
                "query": {},
            }
        )

    return {
        "date": today_s,
        "total": len(items),
        "groups": group_by_module(items),
    }
