"""习惯培养业务逻辑（数据在 planpool.db）。

- 习惯定义 habits 与打卡记录 habit_logs；打卡记录按 (habit_id, log_date) 唯一；
- 统计：累计打卡次数、完成率（应打卡天数中已打卡比例）、当前连续天数、
  最长连续天数；连续天数算法对「今天还没打但已往日连续」友好。
"""

from datetime import date as _date, timedelta

from .. import config, db

DATE_FMT = "%Y-%m-%d"
FREQ_DAILY = "daily"
FREQ_WEEKDAYS = "weekdays"
FREQ_CUSTOM = "custom"
FREQ_OPTIONS = [FREQ_DAILY, FREQ_WEEKDAYS, FREQ_CUSTOM]


def _get_conn():
    return db.get_conn(config.PLANPOOL_DB)


def _to_date(s: str) -> _date:
    return _date.fromisoformat(s)


def _mon1(d: _date) -> int:
    """周一=1 … 周日=7（与 freq_days 约定一致）。"""
    return d.weekday() + 1


def expected_on(habit: dict, d: _date) -> bool:
    """某天是否应打卡（按频率）。"""
    ft = habit.get("freq_type") or FREQ_DAILY
    if ft == FREQ_DAILY:
        return True
    if ft == FREQ_WEEKDAYS:
        return d.weekday() < 5
    if ft == FREQ_CUSTOM:
        days = [int(x) for x in (habit.get("freq_days") or "").split(",") if x.strip()]
        return _mon1(d) in days
    return True


# ---------------------------------------------------------------------------
# 增删改查
# ---------------------------------------------------------------------------
def list_habits(include_archived: bool = False) -> list[dict]:
    conn = _get_conn()
    try:
        sql = "SELECT * FROM habits"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY created_at, id"
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def get_habit(hid: int) -> dict | None:
    conn = _get_conn()
    try:
        r = conn.execute("SELECT * FROM habits WHERE id = ?", (hid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def create_habit(
    name: str,
    reason: str = "",
    emoji: str = "🔴",
    freq_type: str = FREQ_DAILY,
    freq_days: str = "",
    start_date: str | None = None,
) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("习惯名不能为空")
    if freq_type not in FREQ_OPTIONS:
        freq_type = FREQ_DAILY
    start = start_date or _date.today().isoformat()
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO habits (name, reason, emoji, freq_type, freq_days, start_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, reason or "", emoji or "🔴", freq_type, freq_days or "", start),
        )
        conn.commit()
        return get_habit(cur.lastrowid)
    finally:
        conn.close()


def update_habit(hid: int, **fields) -> dict | None:
    allowed = {"name", "reason", "emoji", "freq_type", "freq_days", "start_date", "archived"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return get_habit(hid)
    if "archived" in sets:
        sets["archived"] = 1 if sets["archived"] else 0
    if "freq_type" in sets and sets["freq_type"] not in FREQ_OPTIONS:
        sets["freq_type"] = FREQ_DAILY
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE habits SET " + ", ".join(f"{k} = ?" for k in sets) + " WHERE id = ?",
            (*[sets[k] for k in sets], hid),
        )
        if cur.rowcount == 0:
            return None
        conn.commit()
        return get_habit(hid)
    finally:
        conn.close()


def archive_habit(hid: int) -> dict | None:
    return update_habit(hid, archived=1)


# ---------------------------------------------------------------------------
# 打卡
# ---------------------------------------------------------------------------
def checkin(hid: int, log_date: str | None = None) -> dict | None:
    d = log_date or _date.today().isoformat()
    if get_habit(hid) is None:
        return None
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO habit_logs (habit_id, log_date) VALUES (?, ?)",
            (hid, d),
        )
        conn.commit()
        r = conn.execute(
            "SELECT * FROM habit_logs WHERE habit_id = ? AND log_date = ?", (hid, d)
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def uncheck(hid: int, log_date: str) -> dict:
    conn = _get_conn()
    try:
        conn.execute(
            "DELETE FROM habit_logs WHERE habit_id = ? AND log_date = ?", (hid, log_date)
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def log_dates(hid: int) -> list[str]:
    """某习惯全部打卡日期（用于前端热力图）。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT log_date FROM habit_logs WHERE habit_id = ? ORDER BY log_date",
            (hid,),
        ).fetchall()
        return [r["log_date"] for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
def _expected_dates(habit: dict, start: _date, end: _date) -> list[_date]:
    cur = start
    out: list[_date] = []
    while cur <= end:
        if expected_on(habit, cur):
            out.append(cur)
        cur += timedelta(days=1)
    return out


def compute_stats(hid: int) -> dict | None:
    habit = get_habit(hid)
    if habit is None:
        return None
    start = _to_date(habit["start_date"])
    today = _date.today()

    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT log_date FROM habit_logs WHERE habit_id = ?", (hid,)
        ).fetchall()
    finally:
        conn.close()
    logs = {r["log_date"] for r in rows}
    log_set = set(logs)

    total_checkins = len(logs)
    expected = _expected_dates(habit, start, today)
    expected_total = len(expected)
    done_expected = sum(1 for d in expected if d.isoformat() in log_set)
    completion_rate = round(done_expected / expected_total * 100) if expected_total else 0

    current_streak, longest_streak = _streaks(habit, log_set, start, today)
    last = max((_to_date(d) for d in logs), default=None)
    return {
        "habit_id": hid,
        "total_checkins": total_checkins,
        "expected_total": expected_total,
        "done_expected": done_expected,
        "completion_rate": completion_rate,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "last_checkin": last.isoformat() if last else "",
        "checked_today": today.isoformat() in log_set,
    }


def _streaks(habit: dict, log_set: set, start: _date, today: _date):
    """返回 (当前连续, 最长连续)。"""
    expected = _expected_dates(habit, start, today)
    if not expected:
        return 0, 0
    seq = [d.isoformat() in log_set for d in expected]

    # 当前连续：从末尾往前；若末尾即今天且今天还没打，则起点顺延到昨天，
    # 不打断用户「当天稍后补打卡」的连续感。
    end_idx = len(seq) - 1
    if not seq[end_idx] and expected[end_idx] == today:
        end_idx -= 1
    cur = 0
    for i in range(end_idx, -1, -1):
        if seq[i]:
            cur += 1
        else:
            break

    longest = 0
    run = 0
    for v in seq:
        if v:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return cur, longest


def board_stats() -> dict:
    habits = list_habits(include_archived=False)
    per: list[dict] = []
    for h in habits:
        st = compute_stats(h["id"]) or {}
        # 拍平成平铺结构：id/name/emoji 等直接出现在顶层，方便前端按 h.id 访问
        per.append({**dict(h), **st})
    total = len(habits)
    checked_today = sum(1 for p in per if p.get("checked_today"))
    all_checkins = sum(p.get("total_checkins", 0) for p in per)
    longest_overall = max((p.get("longest_streak", 0) for p in per), default=0)
    return {
        "today_checked": checked_today,
        "today_total": total,
        "total_checkins": all_checkins,
        "longest_overall": longest_overall,
        "habits": per,
    }


def list_for_date(date_str: str) -> list[dict]:
    """某天的习惯清单（用于日历打卡面板）。"""
    habits = list_habits(include_archived=False)
    d = _to_date(date_str)
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT habit_id FROM habit_logs WHERE log_date = ?", (date_str,)
        ).fetchall()
    finally:
        conn.close()
    done_ids = {r["habit_id"] for r in rows}
    return [
        {
            "habit": dict(h),
            "done": h["id"] in done_ids,
            "expected": expected_on(h, d),
        }
        for h in habits
    ]


def calendar_map(from_date: str, to_date: str) -> dict[str, dict]:
    """区间每日起望 / 已打卡数（给首页日历红点用）。"""
    habits = list_habits(include_archived=False)
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT habit_id, log_date FROM habit_logs "
            "WHERE log_date >= ? AND log_date <= ?",
            (from_date, to_date),
        ).fetchall()
    finally:
        conn.close()
    logs: dict[str, set] = {}
    for r in rows:
        logs.setdefault(r["log_date"], set()).add(r["habit_id"])

    result: dict[str, dict] = {}
    cur = _to_date(from_date)
    end = _to_date(to_date)
    while cur <= end:
        ds = cur.isoformat()
        expected = [h for h in habits if h["start_date"] <= ds and expected_on(h, cur)]
        if expected:
            done = sum(1 for h in expected if h["id"] in logs.get(ds, set()))
            result[ds] = {"total": len(expected), "done": done}
        cur += timedelta(days=1)
    return result
