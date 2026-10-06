"""洞察（统计 / 复盘）业务逻辑。

职责：
1. dashboard(from, to)：跨模块**只读**聚合（记账 / 计时 / 日程 / 习惯 / 日报 / 目标），
   一次返回 Dashboard 所需的量化与质化数据，避免前端拉全年日报正文；
2. 目标 KPI：CRUD + 推进打卡（写入 insight.db）；
3. review(scope, anchor)：基于真实数据自动生成周 / 月 / 季复盘 Markdown。

约定：
- 本模块**只读**其它模块的库，写入一律落在 insight.db，不破坏各模块数据主权；
- 金额在记账库里以「分」存储，读出后统一转成「元」；
- 所有区间均为闭区间 [from, to]，日期格式 YYYY-MM-DD。
"""

import re
import sqlite3
from datetime import date, datetime, timedelta

from .. import config, db
from ..services import habit as habit_svc
from ..services.accounting import _cents_to_yuan
from ..services.daily import parse_sections

DATE_FMT = "%Y-%m-%d"
_TAG_RE = re.compile(r"(?:^|\s)#([^\s#,，。；;：:]+)")

# 复盘范围
SCOPES = ("week", "month", "quarter", "year")
SCOPE_LABELS = {"week": "周", "month": "月", "quarter": "季", "year": "年"}

PROGRESS_DONE = "已完成"

# 日报三段是否齐全：工作 / 问题 / 计划
_REQUIRED_SECTIONS = ("work", "issue", "plan")


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _get_conn() -> sqlite3.Connection:
    return db.get_conn(config.INSIGHT_DB)


def _d(s: str) -> date:
    return datetime.strptime(s, DATE_FMT).date()


def _iso(d: date) -> str:
    return d.strftime(DATE_FMT)


def _validate_date(s: str, field: str = "日期") -> date:
    try:
        return _d(s)
    except ValueError as e:
        raise ValueError(f"{field}格式应为 YYYY-MM-DD") from e


def _pct(a: float, b: float) -> float:
    """安全百分比：分母为 0 时返回 0。"""
    return round(a / b * 100, 1) if b else 0.0


def _iter_days(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _range_of(scope: str, anchor: str) -> tuple[str, str]:
    """按范围类型与锚点日期算出 [from, to]。

    week：锚点所在自然周（周一 ~ 周日）
    month：锚点所在自然月首末日
    quarter：锚点所在自然季度
    year：锚点所在自然年
    """
    a = _validate_date(anchor, "anchor")
    if scope == "week":
        monday = a - timedelta(days=a.weekday())
        return _iso(monday), _iso(monday + timedelta(days=6))
    if scope == "month":
        first = a.replace(day=1)
        if first.month == 12:
            last = first.replace(year=first.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last = first.replace(month=first.month + 1, day=1) - timedelta(days=1)
        return _iso(first), _iso(last)
    if scope == "quarter":
        q = (a.month - 1) // 3
        first = date(a.year, q * 3 + 1, 1)
        last_month = q * 3 + 3
        if last_month == 12:
            last = date(a.year + 1, 1, 1) - timedelta(days=1)
        else:
            last = date(a.year, last_month + 1, 1) - timedelta(days=1)
        return _iso(first), _iso(last)
    if scope == "year":
        return _iso(date(a.year, 1, 1)), _iso(date(a.year, 12, 31))
    raise ValueError(f"未知复盘范围：{scope}")


def _iso_week(d: date) -> tuple[int, int]:
    """ISO (周年, 周号)。

    跨年周必须用 ISO 周年而非日历年：2027-01-01 属于 2026 年第 53 周，
    若用 d.year 会得到「2027 年第 1 周」这种与标题、文件名互相矛盾的编号。
    """
    iso = d.isocalendar()
    return int(iso[0]), int(iso[1])


# ---------------------------------------------------------------------------
# 目标 KPI
# ---------------------------------------------------------------------------
def _goal_to_dict(row: sqlite3.Row) -> dict:
    g = dict(row)
    return g


def _progress_of(g: dict) -> dict:
    """算目标进度：支持正向（存钱）与反向（减重，目标值小于起始值）。"""
    start = float(g.get("start_value") or 0)
    target = float(g.get("target") or 0)
    current = float(g.get("current") or 0)
    span = target - start
    if abs(span) < 1e-9:
        pct = 100.0 if current >= target else 0.0
    else:
        pct = (current - start) / span * 100
    pct = max(0.0, min(100.0, pct))
    return {
        **g,
        "remaining": round(target - current, 2),
        "pct": round(pct, 1),
        "done": pct >= 100,
    }


def list_goals(include_archived: bool = False) -> list[dict]:
    conn = _get_conn()
    try:
        sql = "SELECT * FROM goals"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY archived, deadline, id"
        rows = conn.execute(sql).fetchall()
        return [_progress_of(_goal_to_dict(r)) for r in rows]
    finally:
        conn.close()


def get_goal(gid: int) -> dict | None:
    conn = _get_conn()
    try:
        r = conn.execute("SELECT * FROM goals WHERE id = ?", (gid,)).fetchone()
        return _progress_of(_goal_to_dict(r)) if r else None
    finally:
        conn.close()


def create_goal(payload: dict) -> dict:
    title = (payload.get("title") or "").strip()
    if not title:
        raise ValueError("目标名不能为空")
    target = float(payload.get("target") or 0)
    start_value = float(payload.get("start_value") or 0)
    deadline = (payload.get("deadline") or "").strip()
    if deadline:
        _validate_date(deadline, "截止日")
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO goals (title, category, metric, start_value, target, current, deadline, note) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                title,
                (payload.get("category") or "").strip(),
                (payload.get("metric") or "").strip(),
                start_value,
                target,
                # 未显式给 current 时以起始值开局
                float(payload.get("current", start_value) or 0),
                deadline,
                (payload.get("note") or "").strip(),
            ),
        )
        conn.commit()
        r = conn.execute("SELECT * FROM goals WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _progress_of(_goal_to_dict(r))
    finally:
        conn.close()


def update_goal(gid: int, payload: dict) -> dict | None:
    allowed = {"title", "category", "metric", "start_value", "target", "current", "deadline", "note", "archived"}
    sets = {k: payload[k] for k in allowed if k in payload and payload[k] is not None}
    if not sets:
        return get_goal(gid)
    if "title" in sets:
        title = str(sets["title"]).strip()
        if not title:
            raise ValueError("目标名不能为空")
        sets["title"] = title
    if "deadline" in sets and str(sets["deadline"]).strip():
        _validate_date(str(sets["deadline"]).strip(), "截止日")
    if "archived" in sets:
        sets["archived"] = 1 if sets["archived"] else 0
    for k in ("start_value", "target", "current"):
        if k in sets:
            sets[k] = float(sets[k] or 0)
    conn = _get_conn()
    try:
        sets["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE goals SET " + ", ".join(f"{k} = ?" for k in sets) + " WHERE id = ?",
            (*[sets[k] for k in sets], gid),
        )
        conn.commit()
        r = conn.execute("SELECT * FROM goals WHERE id = ?", (gid,)).fetchone()
        return _progress_of(_goal_to_dict(r)) if r else None
    finally:
        conn.close()


def delete_goal(gid: int) -> bool:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM goal_logs WHERE goal_id = ?", (gid,))
        cur = conn.execute("DELETE FROM goals WHERE id = ?", (gid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def checkin_goal(gid: int, delta: float, note: str = "", log_date: str | None = None) -> dict | None:
    """推进一次目标：累加 delta 并落一条推进记录。"""
    g = get_goal(gid)
    if g is None:
        return None
    day = log_date or date.today().strftime(DATE_FMT)
    _validate_date(day)
    current = round(float(g["current"]) + float(delta), 4)
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE goals SET current = ?, updated_at = datetime('now','localtime') WHERE id = ?",
            (current, gid),
        )
        conn.execute(
            "INSERT INTO goal_logs (goal_id, log_date, delta, value, note) VALUES (?,?,?,?,?)",
            (gid, day, float(delta), current, note or ""),
        )
        conn.commit()
        return get_goal(gid)
    finally:
        conn.close()


def list_goal_logs(gid: int, limit: int = 200) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM goal_logs WHERE goal_id = ? ORDER BY log_date DESC, id DESC LIMIT ?",
            (gid, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 关键结果 KR（横切能力 E7）：目标 → 关键结果 → 周计划
# ---------------------------------------------------------------------------
def week_key(d: date) -> str:
    """ISO 周键：YYYY-Www（周计划联动用）。"""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def current_week_key() -> str:
    return week_key(date.today())


def _kr_to_dict(row: sqlite3.Row) -> dict:
    return _progress_of(dict(row))


def list_key_results(goal_id: int | None = None) -> list[dict]:
    conn = _get_conn()
    try:
        if goal_id is None:
            rows = conn.execute("SELECT * FROM key_results ORDER BY goal_id, id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM key_results WHERE goal_id = ? ORDER BY id", (goal_id,)
            ).fetchall()
        return [_kr_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_key_result(kid: int) -> dict | None:
    conn = _get_conn()
    try:
        r = conn.execute("SELECT * FROM key_results WHERE id = ?", (kid,)).fetchone()
        return _kr_to_dict(r) if r else None
    finally:
        conn.close()


def create_key_result(goal_id: int, payload: dict) -> dict:
    title = (payload.get("title") or "").strip()
    if not title:
        raise ValueError("关键结果名不能为空")
    if get_goal(goal_id) is None:
        raise ValueError("目标不存在")
    deadline = (payload.get("deadline") or "").strip()
    if deadline:
        _validate_date(deadline, "截止日")
    start_value = float(payload.get("start_value") or 0)
    weight = float(payload.get("weight") if payload.get("weight") is not None else 1)
    if weight < 0:
        raise ValueError("权重不能为负")
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO key_results "
            "(goal_id, title, metric, start_value, target, current, weight, week, deadline, note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                goal_id,
                title,
                (payload.get("metric") or "").strip(),
                start_value,
                float(payload.get("target") or 0),
                float(payload.get("current", start_value) or 0),
                weight,
                (payload.get("week") or "").strip(),
                deadline,
                (payload.get("note") or "").strip(),
            ),
        )
        conn.commit()
        r = conn.execute("SELECT * FROM key_results WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _kr_to_dict(r)
    finally:
        conn.close()


def update_key_result(kid: int, payload: dict) -> dict | None:
    allowed = {
        "title", "metric", "start_value", "target", "current",
        "weight", "week", "deadline", "note",
    }
    sets = {k: payload[k] for k in allowed if k in payload and payload[k] is not None}
    if not sets:
        return get_key_result(kid)
    if "title" in sets:
        title = str(sets["title"]).strip()
        if not title:
            raise ValueError("关键结果名不能为空")
        sets["title"] = title
    if "deadline" in sets and str(sets["deadline"]).strip():
        _validate_date(str(sets["deadline"]).strip(), "截止日")
    for k in ("start_value", "target", "current", "weight"):
        if k in sets:
            sets[k] = float(sets[k] or 0)
    if "weight" in sets and sets["weight"] < 0:
        raise ValueError("权重不能为负")
    conn = _get_conn()
    try:
        sets["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            "UPDATE key_results SET " + ", ".join(f"{k} = ?" for k in sets) + " WHERE id = ?",
            (*[sets[k] for k in sets], kid),
        )
        if cur.rowcount == 0:
            return None
        conn.commit()
        return get_key_result(kid)
    finally:
        conn.close()


def delete_key_result(kid: int) -> bool:
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM key_results WHERE id = ?", (kid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def goal_rollup(goal_id: int) -> dict:
    """把目标下各 KR 的进度按 weight 加权汇总，作为目标的整体推进度。"""
    krs = list_key_results(goal_id)
    total_w = sum(float(k.get("weight") or 0) for k in krs)
    if not krs or total_w <= 0:
        return {"goal_id": goal_id, "kr_count": len(krs), "pct": None, "krs": krs}
    pct = sum(float(k.get("pct") or 0) * float(k.get("weight") or 0) for k in krs) / total_w
    return {
        "goal_id": goal_id,
        "kr_count": len(krs),
        "pct": round(max(0.0, min(100.0, pct)), 1),
        "krs": krs,
    }


def list_key_results_by_week(week: str) -> list[dict]:
    """周计划联动：取某周（YYYY-Www）挂了哪些 KR。"""
    key = (week or "").strip() or current_week_key()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT kr.*, g.title AS goal_title, g.category AS goal_category "
            "FROM key_results kr JOIN goals g ON g.id = kr.goal_id "
            "WHERE kr.week = ? ORDER BY kr.goal_id, kr.id",
            (key,),
        ).fetchall()
        return [_progress_of(dict(r)) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 跨模块聚合：各模块的取数函数
# ---------------------------------------------------------------------------
def _finance(start: str, end: str) -> dict:
    """记账：区间收支、分类 Top、每日净额、预算执行、资产合计。"""
    conn = db.get_conn(config.ACCOUNTING_DB)
    try:
        rows = conn.execute(
            "SELECT kind, amount, date, category, category2 FROM transactions "
            "WHERE date >= ? AND date <= ?",
            (start, end),
        ).fetchall()
        accounts = conn.execute("SELECT COALESCE(SUM(balance), 0) AS s FROM accounts").fetchone()["s"]
    finally:
        conn.close()

    income = expense = reimburse = 0.0
    cat_exp: dict[str, float] = {}
    cat_inc: dict[str, float] = {}
    daily: dict[str, float] = {}
    for r in rows:
        amt = _cents_to_yuan(r["amount"])
        day = r["date"]
        daily.setdefault(day, 0.0)
        if r["kind"] == "income":
            income += amt
            daily[day] += amt
            k = r["category"] or "其他"
            cat_inc[k] = cat_inc.get(k, 0.0) + amt
        elif r["kind"] == "expense":
            expense += amt
            daily[day] -= amt
            k = f"{r['category']}·{r['category2']}" if r["category2"] else (r["category"] or "其他")
            cat_exp[k] = cat_exp.get(k, 0.0) + amt
        elif r["kind"] == "reimburse":
            reimburse += amt

    # 未收回垫付：截至区间末的滚动余额（累计垫付 − 累计到账），
    # 复用 accounting._reimburse_outstanding，与记账概览/资产卡/年度走势同源。
    from ..services.accounting import _reimburse_outstanding

    cum_p, cum_s = _reimburse_outstanding(end)
    unreimbursed = max(0.0, cum_p - cum_s)

    def top(d: dict, n: int = 6) -> list[dict]:
        return [
            {"category": k, "amount": round(v, 2)}
            for k, v in sorted(d.items(), key=lambda x: -x[1])[:n]
        ]

    # 预算仅在同一自然月内才有意义
    month = start[:7] if start[:7] == end[:7] else None
    budget = None
    if month:
        try:
            from ..services.accounting import budget_status

            budget = budget_status(month)
        except Exception:
            budget = None

    return {
        "income": round(income, 2),
        "expense": round(expense, 2),
        "reimburse": round(reimburse, 2),
        "unreimbursed": round(unreimbursed, 2),
        "net": round(income - expense, 2),
        "top_expense": top(cat_exp),
        "top_income": top(cat_inc),
        "by_day": {k: round(v, 2) for k, v in sorted(daily.items())},
        "budget": budget,
        "accounts_total": round(_cents_to_yuan(accounts), 2),
    }


def _focus(start: str, end: str) -> dict:
    """计时：区间专注总时长、会话数、每日分布与 Top 任务。"""
    conn = db.get_conn(config.TIMER_DB)
    try:
        day_rows = conn.execute(
            "SELECT day, COALESCE(SUM(duration_sec),0) AS s, COUNT(*) AS n FROM time_logs "
            "WHERE day >= ? AND day <= ? GROUP BY day",
            (start, end),
        ).fetchall()
        task_rows = conn.execute(
            "SELECT COALESCE(NULLIF(title,''),'未命名') AS title, SUM(duration_sec) AS s, COUNT(*) AS n "
            "FROM time_logs WHERE day >= ? AND day <= ? GROUP BY title ORDER BY s DESC LIMIT 8",
            (start, end),
        ).fetchall()
        total = conn.execute(
            "SELECT COALESCE(SUM(duration_sec),0) AS s, COUNT(*) AS n FROM time_logs "
            "WHERE day >= ? AND day <= ?",
            (start, end),
        ).fetchone()
    finally:
        conn.close()

    return {
        "total_sec": int(total["s"]),
        "sessions": int(total["n"]),
        "by_day": {r["day"]: int(r["s"]) for r in day_rows},
        "top_tasks": [
            {"title": r["title"], "total_sec": int(r["s"]), "sessions": int(r["n"])}
            for r in task_rows
        ],
    }


def _tasks(start: str, end: str) -> dict:
    """日程：区间内到期的任务完成情况与平均完成度。"""
    conn = db.get_conn(config.PLANPOOL_DB)
    try:
        rows = conn.execute("SELECT * FROM tasks").fetchall()
    finally:
        conn.close()

    def _task_day(t: sqlite3.Row) -> str:
        """任务归属日：优先结束日期，其次开始日期，都没有则用创建日。"""
        return (t["end_date"] or t["start_date"] or (t["created_at"] or "")[:10] or "")[:10]

    in_range = [t for t in rows if start <= _task_day(t) <= end]
    counts = {"未完成": 0, "进行中": 0, "已完成": 0}
    done_by_day: dict[str, int] = {}
    completion_sum = 0
    for t in in_range:
        p = t["progress"] or "未完成"
        counts[p] = counts.get(p, 0) + 1
        completion_sum += int(t["completion"] or 0)
        if p == PROGRESS_DONE:
            d = _task_day(t)
            done_by_day[d] = done_by_day.get(d, 0) + 1

    total = len(in_range)
    done = counts[PROGRESS_DONE]
    return {
        "total": total,
        "done": done,
        "doing": counts["进行中"],
        "todo": counts["未完成"],
        "done_rate": _pct(done, total),
        "avg_completion": round(completion_sum / total, 1) if total else 0.0,
        "by_day": dict(sorted(done_by_day.items())),
    }


def _habits(start: str, end: str) -> dict:
    """习惯：区间应打卡 / 实打卡、每日达标率与各习惯明细。"""
    habits = habit_svc.list_habits(include_archived=False)
    conn = db.get_conn(config.PLANPOOL_DB)
    try:
        rows = conn.execute(
            "SELECT habit_id, log_date FROM habit_logs WHERE log_date >= ? AND log_date <= ?",
            (start, end),
        ).fetchall()
    finally:
        conn.close()

    logs: dict[str, set] = {}
    for r in rows:
        logs.setdefault(r["log_date"], set()).add(r["habit_id"])

    d0, d1 = _d(start), _d(end)
    items: list[dict] = []
    expected_total = done_total = 0
    for h in habits:
        exp = 0
        done = 0
        for d in _iter_days(max(d0, _d(h["start_date"])), d1):
            if not habit_svc.expected_on(h, d):
                continue
            exp += 1
            if h["id"] in logs.get(_iso(d), set()):
                done += 1
        expected_total += exp
        done_total += done
        st = habit_svc.compute_stats(h["id"]) or {}
        items.append({
            "id": h["id"],
            "name": h["name"],
            "emoji": h["emoji"],
            "expected": exp,
            "done": done,
            "rate": _pct(done, exp),
            "streak": st.get("current_streak", 0),
            "longest": st.get("longest_streak", 0),
        })
    items.sort(key=lambda x: (-x["rate"], -x["expected"]))

    by_day: dict[str, dict] = {}
    for d in _iter_days(d0, d1):
        ds = _iso(d)
        expected = [
            h for h in habits
            if h["start_date"] <= ds and habit_svc.expected_on(h, d)
        ]
        if expected:
            by_day[ds] = {
                "total": len(expected),
                "done": sum(1 for h in expected if h["id"] in logs.get(ds, set())),
            }

    return {
        "expected": expected_total,
        "done": done_total,
        "rate": _pct(done_total, expected_total),
        "by_day": by_day,
        "items": items,
    }


def _writing(start: str, end: str) -> dict:
    """日报：写作频率、字数、streak、标签分布与三段完整度（质化）。"""
    conn = db.get_conn(config.DAILY_DB)
    try:
        rows = conn.execute(
            "SELECT date, body FROM daily_entries WHERE date >= ? AND date <= ? ORDER BY date",
            (start, end),
        ).fetchall()
        all_days = {r["date"] for r in conn.execute("SELECT date FROM daily_entries").fetchall()}
    finally:
        conn.close()

    today_iso = date.today().strftime(DATE_FMT)
    by_day: dict[str, int] = {}
    tag_count: dict[str, int] = {}
    total_chars = 0
    full_days = 0
    for r in rows:
        body = r["body"] or ""
        by_day[r["date"]] = len(body.strip())
        total_chars += len(body.strip())
        for t in _TAG_RE.findall(body):
            tag_count[t] = tag_count.get(t, 0) + 1
        keys = {s["key"] for s in parse_sections(body)}
        if all(k in keys for k in _REQUIRED_SECTIONS):
            full_days += 1

    # 连续写作天数：以今天（或区间末日）往前数，今天还没写不算断
    end_d = min(_d(end), _d(today_iso))
    streak = 0
    guard = 0
    cur = end_d
    while guard < 5000:
        guard += 1
        ds = _iso(cur)
        if ds in all_days:
            streak += 1
        elif ds == today_iso:
            pass  # 当天还没写，不打断连续感
        else:
            break
        cur -= timedelta(days=1)

    days = len(by_day)
    elapsed = sum(1 for d in _iter_days(_d(start), _d(end)) if _iso(d) <= today_iso)
    tags = [
        {"tag": k, "count": v}
        for k, v in sorted(tag_count.items(), key=lambda x: (-x[1], x[0]))[:20]
    ]
    return {
        "days": days,
        "elapsed": elapsed,
        "coverage": _pct(days, elapsed),
        "total_chars": total_chars,
        "avg_chars": round(total_chars / days) if days else 0,
        "streak": streak,
        "complete_days": full_days,
        "complete_rate": _pct(full_days, days),
        "by_day": by_day,
        "tags": tags,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def dashboard(from_: str, to: str) -> dict:
    """跨模块只读聚合，返回 Dashboard 所需的全部数据。

    返回结构见前端 api/insight.ts 的 Dashboard 类型。
    """
    start_d = _validate_date(from_, "from")
    end_d = _validate_date(to, "to")
    if start_d > end_d:
        raise ValueError("起始日期不能晚于结束日期")
    start, end = _iso(start_d), _iso(end_d)
    n_days = sum(1 for _ in _iter_days(start_d, end_d))

    return {
        "range": {
            "from": start,
            "to": end,
            "days": n_days,
            "label": f"{start} ~ {end}（{n_days} 天）",
        },
        "finance": _finance(start, end),
        "focus": _focus(start, end),
        "tasks": _tasks(start, end),
        "habits": _habits(start, end),
        "writing": _writing(start, end),
        "goals": list_goals(),
    }


# ---------------------------------------------------------------------------
# 自动复盘
# ---------------------------------------------------------------------------
def _fmt_sec(sec: int) -> str:
    h, m = divmod(int(sec) // 60, 60)
    if h:
        return f"{h} 小时 {m} 分钟"
    return f"{m} 分钟"


def _review_title(scope: str, start_d: date, end_d: date) -> str:
    if scope == "week":
        iy, iw = _iso_week(start_d)
        return f"{iy} 年第 {iw} 周复盘（{_iso(start_d)} ~ {_iso(end_d)}）"
    if scope == "month":
        return f"{start_d.year} 年 {start_d.month} 月复盘"
    if scope == "quarter":
        return f"{start_d.year} 年第 {(start_d.month - 1) // 3 + 1} 季度复盘"
    return f"{start_d.year} 年度复盘"


def review(scope: str, anchor: str) -> dict:
    """生成周 / 月 / 季复盘 Markdown（基于真实数据 + 提问引导）。"""
    if scope not in SCOPES:
        raise ValueError(f"未知复盘范围：{scope}")
    start, end = _range_of(scope, anchor)
    data = dashboard(start, end)
    start_d, end_d = _d(start), _d(end)

    f = data["finance"]
    fo = data["focus"]
    t = data["tasks"]
    h = data["habits"]
    w = data["writing"]
    g = data["goals"]

    lines: list[str] = []
    add = lines.append

    add(f"# {_review_title(scope, start_d, end_d)}")
    add("")
    add(f"> 区间：{start} ~ {end} · 共 {data['range']['days']} 天 · "
        f"生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    add("")

    add("## 一、总览")
    add("")
    add("| 维度 | 结果 |")
    add("| --- | --- |")
    add(f"| 收支结余 | {f['net']:+.2f} 元（收 {f['income']:.2f} / 支 {f['expense']:.2f}） |")
    add(f"| 专注时长 | {_fmt_sec(fo['total_sec'])}（{fo['sessions']} 个时段） |")
    add(f"| 任务完成 | {t['done']}/{t['total']}（{t['done_rate']}%） · 平均完成度 {t['avg_completion']}% |")
    add(f"| 习惯达标 | {h['done']}/{h['expected']}（{h['rate']}%） |")
    add(f"| 日报写作 | {w['days']} 篇 / {w['elapsed']} 天 · 连续 {w['streak']} 天 · {w['total_chars']} 字 |")
    add(f"| 复盘完整度 | {w['complete_rate']}%（工作 / 问题 / 计划三段齐全） |")
    add("")

    add("## 二、收支")
    add("")
    if f["top_expense"]:
        add("支出 Top：")
        add("")
        for i in f["top_expense"]:
            add(f"- {i['category']}：{i['amount']:.2f} 元")
    else:
        add("- 本区间没有支出记录")
    if f["budget"] and f["budget"]["total"]["limit"] > 0:
        bt = f["budget"]["total"]
        add("")
        add(f"预算执行：已花 {bt['spent']:.2f} / {bt['limit']:.2f} 元（{bt['pct']}%）"
            f"{' · ⚠️ 已超支' if bt['over'] else ''}")
    add("")

    add("## 三、专注与任务")
    add("")
    if fo["top_tasks"]:
        add("耗时最多的三件事：")
        add("")
        for i in fo["top_tasks"][:3]:
            add(f"- {i['title']}：{_fmt_sec(i['total_sec'])}")
    else:
        add("- 本区间没有专注记录")
    add("")
    add(f"到期任务 {t['total']} 项，完成 {t['done']} 项，进行中 {t['doing']} 项，未开始 {t['todo']} 项。")
    add("")

    add("## 四、习惯")
    add("")
    if h["items"]:
        for i in h["items"]:
            add(f"- {i['emoji']} {i['name']}：{i['done']}/{i['expected']}（{i['rate']}%）"
                f" · 连续 {i['streak']} 天")
    else:
        add("- 还没有正在培养的习惯")
    add("")

    add("## 五、写作与思考")
    add("")
    add(f"共写下 {w['days']} 篇日报、{w['total_chars']} 字（篇均 {w['avg_chars']} 字）。")
    if w["tags"]:
        add("")
        add("高频主题：" + "、".join(f"#{i['tag']}（{i['count']}）" for i in w["tags"][:8]))
    add("")

    add("## 六、目标进展")
    add("")
    if g:
        for item in g:
            add(f"- {item['title']}：{item['current']}{item['metric']} / {item['target']}{item['metric']}"
                f"（{item['pct']}%）{' ✅ 已达成' if item['done'] else ''}")
    else:
        add("- 还没有设定目标，去「目标」页创建一个吧")
    add("")

    add("## 七、复盘提问")
    add("")
    add("1. 这段时间最有价值的一件事是什么？为什么它能成？")
    add("2. 最大的一次偏离发生在哪里？当时的触发条件是什么？")
    add("3. 哪一项数据你会希望在下一周期明显改善？具体数字是多少？")
    add("4. 有哪些事本可以不自己做（授权 / 放弃 / 简化）？")
    add("5. 下周（月）只保留哪三件事，其余全部砍掉？")
    add("")
    add("---")
    add("")
    add("### 我的回答")
    add("")
    add("（在这里写下你的答案，形成闭环）")

    content = "\n".join(lines) + "\n"
    iy, iw = _iso_week(start_d)
    name_map = {
        "week": f"{iy}-W{iw:02d} 周复盘.md",
        "month": f"{start[:7]} 月度复盘.md",
        "quarter": f"{start_d.year}-Q{(start_d.month - 1) // 3 + 1} 季度复盘.md",
        "year": f"{start_d.year} 年度复盘.md",
    }
    return {
        "scope": scope,
        "anchor": anchor,
        "from": start,
        "to": end,
        "title": _review_title(scope, start_d, end_d),
        "folder": "复盘",
        "filename": name_map[scope],
        "content": content,
    }
