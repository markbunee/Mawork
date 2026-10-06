"""记账业务逻辑：增删改查、统计聚合、报销事件、资产账户、预算、周期账、Excel 导出。

金额统一以「分」整数存储；元↔分换算一律走 Decimal，避免浮点误差
（元 → 分 用 ROUND_HALF_UP 四舍五入到分）。
"""
import io
import sqlite3
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from .. import db
from ..models.accounting import (
    CATEGORIES,
    KIND_LABELS,
)


# ---------------------------------------------------------------------------
# 金额换算（统一 Decimal）
# ---------------------------------------------------------------------------
def _yuan_to_cents(yuan) -> int:
    """元 → 分（Decimal 精确换算，四舍五入到分）。"""
    if yuan is None:
        return 0
    return int((Decimal(str(yuan)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _cents_to_yuan(cents: int) -> float:
    """分 → 元（Decimal 计算，避免浮点误差）。"""
    return float(Decimal(cents) / 100)


# ---------------------------------------------------------------------------
# 基础 CRUD（支持二级分类 category2）
# ---------------------------------------------------------------------------
def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["amount"] = _cents_to_yuan(d["amount"])  # 分 → 元
    d.setdefault("category2", "")
    return d


def create_transaction(
    kind: str,
    category: str,
    amount_yuan: float,
    note: str,
    date: str,
    category2: str = "",
) -> dict:
    """新增一笔账。amount_yuan 为元，内部转分存储。"""
    amount_cents = _yuan_to_cents(amount_yuan)
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO transactions (kind, category, category2, amount, note, date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (kind, category, category2 or "", amount_cents, note, date),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def _reimburse_events_sums(conn: sqlite3.Connection, tx_ids: list[int]) -> dict[int, int]:
    """批量返回 tx_id -> 已报销总额（分）。"""
    if not tx_ids:
        return {}
    marks = ",".join("?" * len(tx_ids))
    rows = conn.execute(
        f"SELECT tx_id, COALESCE(SUM(amount), 0) AS s FROM reimburse_events "
        f"WHERE tx_id IN ({marks}) GROUP BY tx_id",
        tx_ids,
    ).fetchall()
    return {r["tx_id"]: r["s"] for r in rows}


def list_transactions(
    kind: str | None = None,
    year: str | None = None,
    month: str | None = None,
) -> list[dict]:
    """按条件查询账目。month 为 'YYYY-MM'，year 为 'YYYY'。

    报销账目附带 reimbursed（已报销）与 remaining（剩余待报销）字段。
    """
    sql = "SELECT * FROM transactions WHERE 1=1"
    params: list = []
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if month:
        sql += " AND date LIKE ?"
        params.append(f"{month}%")
    elif year:
        sql += " AND date LIKE ?"
        params.append(f"{year}%")

    sql += " ORDER BY date DESC, id DESC"

    conn = db.get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        txs = [_row_to_dict(r) for r in rows]
        reimburse_ids = [t["id"] for t in txs if t["kind"] == "reimburse"]
        if reimburse_ids:
            sums = _reimburse_events_sums(conn, reimburse_ids)
            for t in txs:
                if t["kind"] == "reimburse":
                    reimbursed = _cents_to_yuan(sums.get(t["id"], 0))
                    t["reimbursed"] = reimbursed
                    t["remaining"] = round(t["amount"] - reimbursed, 2)
        return txs
    finally:
        conn.close()


def get_transaction(tid: int) -> dict | None:
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tid,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def update_transaction(tid: int, **fields) -> dict | None:
    """按给定字段更新。"""
    allowed = {"kind", "category", "category2", "amount", "note", "date"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_transaction(tid)

    if "amount" in updates:
        updates["amount"] = _yuan_to_cents(updates["amount"])
    if "category2" in updates:
        updates["category2"] = updates["category2"] or ""

    tx = get_transaction(tid)
    if tx and tx["kind"] == "reimburse":
        # 报销账目修改：已报销总额不得超过新金额；改出报销类型则清理事件
        new_kind = updates.get("kind", "reimburse")
        if new_kind != "reimburse":
            conn = db.get_conn()
            try:
                conn.execute("DELETE FROM reimburse_events WHERE tx_id = ?", (tid,))
                conn.commit()
            finally:
                conn.close()
        elif "amount" in updates:
            conn = db.get_conn()
            try:
                done = _reimburse_events_sums(conn, [tid]).get(tid, 0)
            finally:
                conn.close()
            if done > updates["amount"]:
                raise ValueError("已报销金额不能超过修改后的待报销金额")

    sets = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [tid]

    conn = db.get_conn()
    try:
        conn.execute(f"UPDATE transactions SET {sets} WHERE id = ?", params)
        conn.commit()
        return get_transaction(tid)
    finally:
        conn.close()


def delete_transaction(tid: int) -> bool:
    conn = db.get_conn()
    try:
        # 级联清理报销事件（旧表可能未建外键约束，显式删除）
        conn.execute("DELETE FROM reimburse_events WHERE tx_id = ?", (tid,))
        cur = conn.execute("DELETE FROM transactions WHERE id = ?", (tid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 报销事件：待报销 → 到账（事件化，支持部分/多次报销）
# ---------------------------------------------------------------------------
def _event_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["amount"] = _cents_to_yuan(d["amount"])  # 分 → 元
    return d


def create_reimburse_event(tid: int, amount_yuan: float, event_date: str, note: str = "") -> dict:
    """为「待报销」账目创建一条报销事件（部分报销 / 多次报销 / 可追溯）。"""
    tx = get_transaction(tid)
    if tx is None or tx["kind"] != "reimburse":
        raise ValueError("仅「待报销」账目可报销")
    cents = _yuan_to_cents(amount_yuan)
    if cents <= 0:
        raise ValueError("报销金额必须大于 0")

    conn = db.get_conn()
    try:
        done = _reimburse_events_sums(conn, [tid]).get(tid, 0)
        total = _yuan_to_cents(tx["amount"])
        if done + cents > total:
            remaining = _cents_to_yuan(total - done)
            raise ValueError(f"报销总额不能超过待报销金额（剩余 {remaining:.2f} 元）")
        cur = conn.execute(
            "INSERT INTO reimburse_events (tx_id, amount, event_date, note) "
            "VALUES (?, ?, ?, ?)",
            (tid, cents, event_date, note),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM reimburse_events WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _event_to_dict(row)
    finally:
        conn.close()


def list_reimburse_events(tid: int) -> list[dict]:
    """某笔待报销的全部到账事件（按到账日期排序）。"""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM reimburse_events WHERE tx_id = ? ORDER BY event_date, id",
            (tid,),
        ).fetchall()
        return [_event_to_dict(r) for r in rows]
    finally:
        conn.close()


def delete_reimburse_event(eid: int) -> bool:
    conn = db.get_conn()
    try:
        cur = conn.execute("DELETE FROM reimburse_events WHERE id = ?", (eid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def settle_reimbursement(tid: int) -> dict | None:
    """快捷操作：将一笔「待报销」按剩余金额全额报销，到账日期为今天。"""
    tx = get_transaction(tid)
    if tx is None or tx["kind"] != "reimburse":
        return None
    conn = db.get_conn()
    try:
        done = _reimburse_events_sums(conn, [tid]).get(tid, 0)
    finally:
        conn.close()
    total = _yuan_to_cents(tx["amount"])
    remaining = total - done
    if remaining <= 0:
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    return create_reimburse_event(tid, _cents_to_yuan(remaining), today, "全额报销")


# ---------------------------------------------------------------------------
# 资产账户（多账户资产负债表）
# ---------------------------------------------------------------------------
def _account_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["balance"] = _cents_to_yuan(d["balance"])
    return d


def list_accounts() -> list[dict]:
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
        return [_account_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def create_account(name: str, type_: str, balance_yuan: float = 0) -> dict:
    if not name:
        raise ValueError("账户名不能为空")
    cents = _yuan_to_cents(balance_yuan)
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO accounts (name, type, balance) VALUES (?, ?, ?)",
            (name, type_, cents),
        )
        conn.commit()
        return _account_row_to_dict(
            conn.execute("SELECT * FROM accounts WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    finally:
        conn.close()


def update_account(aid: int, name: str | None = None, type_: str | None = None, balance_yuan: float | None = None) -> dict | None:
    conn = db.get_conn()
    try:
        if balance_yuan is not None:
            conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (_yuan_to_cents(balance_yuan), aid))
        if name is not None:
            conn.execute("UPDATE accounts SET name = ? WHERE id = ?", (name, aid))
        if type_ is not None:
            conn.execute("UPDATE accounts SET type = ? WHERE id = ?", (type_, aid))
        conn.commit()
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (aid,)).fetchone()
        return _account_row_to_dict(row) if row else None
    finally:
        conn.close()


def delete_account(aid: int) -> bool:
    conn = db.get_conn()
    try:
        cur = conn.execute("DELETE FROM accounts WHERE id = ?", (aid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def accounts_total() -> float:
    """所有资产账户余额合计（元）。"""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT COALESCE(SUM(balance), 0) AS s FROM accounts").fetchone()
        return _cents_to_yuan(row["s"])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 预算
# ---------------------------------------------------------------------------
def create_budget(period: str, scope: str, category: str, limit_yuan: float) -> dict:
    cents = _yuan_to_cents(limit_yuan)
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO budgets (period, scope, category, limit_cents) VALUES (?, ?, ?, ?)",
            (period, scope, category or "", cents),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM budgets WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _budget_row_to_dict(row)
    finally:
        conn.close()


def _budget_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["limit"] = _cents_to_yuan(d["limit_cents"])
    return d


def list_budgets(period: str) -> list[dict]:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM budgets WHERE period = ? ORDER BY scope, category", (period,)
        ).fetchall()
        return [_budget_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_budget(bid: int, limit_yuan: float) -> dict | None:
    conn = db.get_conn()
    try:
        conn.execute("UPDATE budgets SET limit_cents = ? WHERE id = ?", (_yuan_to_cents(limit_yuan), bid))
        conn.commit()
        row = conn.execute("SELECT * FROM budgets WHERE id = ?", (bid,)).fetchone()
        return _budget_row_to_dict(row) if row else None
    finally:
        conn.close()


def delete_budget(bid: int) -> bool:
    conn = db.get_conn()
    try:
        cur = conn.execute("DELETE FROM budgets WHERE id = ?", (bid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def budget_status(month: str) -> dict:
    """返回某月预算执行状态：总预算 + 各分类预算的「预算/已花/剩余/超支」。

    口径：
    - total（总预算）：统计**所有真实花钱**——支出(expense) + 报销垫付(reimburse)。
      报销垫付虽然会退回，但钱确实已经花出去，预算必须计入，否则业务性支出
      （记为报销）会让预算形同虚设。
    - by_category（分类预算）：只统计 expense。报销的一级分类固定为「待报销」，
      与餐饮/交通等个人支出分类不同口径，不参与分类预算比对。
    """
    budgets = list_budgets(month)
    total_limit = sum(b["limit"] for b in budgets if b["scope"] == "total")
    total_budget = next((b for b in budgets if b["scope"] == "total"), None)

    # 本月实际支出（按一级分类）
    rows = list_transactions(month=month)
    spent_by_cat: dict[str, float] = {}
    total_spent = 0.0
    expense_spent = 0.0
    reimburse_spent = 0.0
    for r in rows:
        if r["kind"] == "expense":
            spent_by_cat[r["category"]] = spent_by_cat.get(r["category"], 0) + r["amount"]
            expense_spent += r["amount"]
        elif r["kind"] == "reimburse":
            # 垫付也是真实支出，计入总预算（不计入分类预算）
            reimburse_spent += r["amount"]
    total_spent = expense_spent + reimburse_spent

    cat_status = []
    for b in budgets:
        if b["scope"] != "category":
            continue
        spent = round(spent_by_cat.get(b["category"], 0), 2)
        cat_status.append({
            "id": b["id"],
            "category": b["category"],
            "limit": b["limit"],
            "spent": spent,
            "remaining": round(b["limit"] - spent, 2),
            "over": spent > b["limit"],
            "pct": round(spent / b["limit"] * 100, 1) if b["limit"] else 0,
        })

    return {
        "period": month,
        "total": {
            "id": total_budget["id"] if total_budget else None,
            "limit": round(total_limit, 2),
            "spent": round(total_spent, 2),
            "remaining": round(total_limit - total_spent, 2),
            "over": total_limit > 0 and total_spent > total_limit,
            "pct": round(total_spent / total_limit * 100, 1) if total_limit else 0,
            # spent 的构成，便于前端解释「已花」到底算了些什么
            "expense": round(expense_spent, 2),
            "reimburse": round(reimburse_spent, 2),
        },
        "by_category": cat_status,
    }


# ---------------------------------------------------------------------------
# 周期账（房租 / 订阅 / 工资 等一键生成）
# ---------------------------------------------------------------------------
def _recurring_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["amount"] = None if row["amount"] is None else float(row["amount"])
    d["active"] = bool(row["active"])
    d["category2"] = d.get("category2", "") or ""
    return d


def list_recurring() -> list[dict]:
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM recurring ORDER BY id").fetchall()
        return [_recurring_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def create_recurring(payload: dict) -> dict:
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO recurring (kind, category, category2, amount, note, freq, day_of_month, account, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload["kind"],
                payload["category"],
                payload.get("category2", "") or "",
                None if payload.get("amount") in (None, "") else float(payload["amount"]),
                payload.get("note", "") or "",
                payload.get("freq", "monthly"),
                int(payload.get("day_of_month", 1) or 1),
                payload.get("account", "") or "",
                1 if payload.get("active", True) else 0,
            ),
        )
        conn.commit()
        return _recurring_row_to_dict(
            conn.execute("SELECT * FROM recurring WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    finally:
        conn.close()


def update_recurring(rid: int, payload: dict) -> dict | None:
    conn = db.get_conn()
    try:
        if payload.get("amount") is not None and payload.get("amount") != "":
            conn.execute("UPDATE recurring SET amount = ? WHERE id = ?", (float(payload["amount"]), rid))
        for col in ("kind", "category", "category2", "note", "freq", "account"):
            if col in payload:
                conn.execute(f"UPDATE recurring SET {col} = ? WHERE id = ?", (payload[col] or "", rid))
        if "day_of_month" in payload:
            conn.execute("UPDATE recurring SET day_of_month = ? WHERE id = ?", (int(payload["day_of_month"] or 1), rid))
        if "active" in payload:
            conn.execute("UPDATE recurring SET active = ? WHERE id = ?", (1 if payload["active"] else 0, rid))
        conn.commit()
        row = conn.execute("SELECT * FROM recurring WHERE id = ?", (rid,)).fetchone()
        return _recurring_row_to_dict(row) if row else None
    finally:
        conn.close()


def delete_recurring(rid: int) -> bool:
    conn = db.get_conn()
    try:
        cur = conn.execute("DELETE FROM recurring WHERE id = ?", (rid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def apply_recurring(month: str) -> dict:
    """把 active 的周期账模板生成为该月交易（按 day_of_month 落日期）。

    幂等：同一模板同一月份只生成一次（以 last_applied 标记）。
    返回 {created: int, skipped: int}。
    """
    templates = [t for t in list_recurring() if t["active"] and t["last_applied"] != month]
    created = 0
    skipped = 0

    year, mm = month.split("-")
    for t in templates:
        # 计算落账日期（不超过当月天数）
        import calendar
        last_day = calendar.monthrange(int(year), int(mm))[1]
        dom = min(t["day_of_month"] or 1, last_day)
        date = f"{month}-{dom:02d}"

        if t["amount"] is None:
            # 无固定金额：跳过自动生成，留给用户手动填
            skipped += 1
            conn = db.get_conn()
            try:
                conn.execute("UPDATE recurring SET last_applied = ? WHERE id = ?", (month, t["id"]))
                conn.commit()
            finally:
                conn.close()
            continue

        create_transaction(
            kind=t["kind"],
            category=t["category"],
            category2=t.get("category2", ""),
            amount_yuan=t["amount"],
            note=(t.get("note") or "") + "（周期账）",
            date=date,
        )
        conn = db.get_conn()
        try:
            conn.execute("UPDATE recurring SET last_applied = ? WHERE id = ?", (month, t["id"]))
            conn.commit()
        finally:
            conn.close()
        created += 1

    return {"created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# 统计聚合
# ---------------------------------------------------------------------------
def _aggregate_by_kind(rows: list[dict]) -> dict:
    """按 kind 汇总金额（报销不计入收入与支出，单独累计在 totals["reimburse"]）。"""
    result = {k: 0.0 for k in KIND_LABELS}
    for r in rows:
        kind = r["kind"]
        if kind == "expense":
            result["expense"] += r["amount"]
        elif kind == "income":
            result["income"] += r["amount"]
        elif kind == "reimburse":
            result["reimburse"] += r["amount"]
    return {k: round(v, 2) for k, v in result.items()}


def _events_total(period_prefix: str | None = None) -> float:
    """报销到账总额（元）。period_prefix 为 'YYYY' / 'YYYY-MM'，按 event_date 归属期间。"""
    conn = db.get_conn()
    try:
        if period_prefix:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS s FROM reimburse_events WHERE event_date LIKE ?",
                (f"{period_prefix}%",),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS s FROM reimburse_events"
            ).fetchone()
        return _cents_to_yuan(row["s"])
    finally:
        conn.close()


def _reimburse_totals(rows: list[dict], period_prefix: str | None = None) -> tuple[float, float]:
    """报销发生额（本期内）：返回 (本期待报销原始额, 本期报销到账额)（元）。"""
    pending = 0.0
    for r in rows:
        if r["kind"] == "reimburse":
            pending += r["amount"]
    return round(pending, 2), round(_events_total(period_prefix), 2)


def _period_end(month: str | None, year: str | None) -> str | None:
    """统计口径的期末日期 'YYYY-MM-DD'；None 表示全部（无截止）。"""
    import calendar

    if month:
        y, m = month.split("-")
        last = calendar.monthrange(int(y), int(m))[1]
        return f"{month}-{last:02d}"
    if year:
        return f"{year}-12-31"
    return None


def _reimburse_outstanding(period_end: str | None) -> tuple[float, float]:
    """未收回垫付（滚动余额口径）：截至 period_end 的「累计垫付 − 累计到账」。

    与 balance()（全量）、yearly_series（月末滚动）同一口径，
    解决 summary 原先用「本期垫付 − 本期到账」相减导致的金额错乱。
    返回 (累计垫付, 累计到账)（元）。
    """
    conn = db.get_conn()
    try:
        if period_end:
            p = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions "
                "WHERE kind = 'reimburse' AND date <= ?",
                (period_end,),
            ).fetchone()[0]
            s = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM reimburse_events "
                "WHERE event_date <= ?",
                (period_end,),
            ).fetchone()[0]
        else:
            p = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE kind = 'reimburse'"
            ).fetchone()[0]
            s = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM reimburse_events"
            ).fetchone()[0]
        return _cents_to_yuan(p), _cents_to_yuan(s)
    finally:
        conn.close()


def _category_breakdown(rows: list[dict], kind: str, categories: list[str]) -> list[dict]:
    """按一级分类汇总某类账目的金额。

    ⚠️ 历史数据里可能存在**已下线的分类**（例如 2025-09 改版前的
    「住宿 / 发展 / 家庭」）。这些金额必须照常计入，绝不能因为不在当前
    分类表里就静默丢弃——否则各分类之和会小于真实收支，图表「总额对不上」。
    未注册分类按金额降序追加在已注册分类之后，保证
    `sum(breakdown) == totals[kind]` 恒成立。
    """
    totals = {c: 0.0 for c in categories}
    unknown: dict[str, float] = {}
    for r in rows:
        if r["kind"] != kind:
            continue
        cat = r["category"] or "其他"
        if cat in totals:
            totals[cat] += r["amount"]
        else:
            unknown[cat] = unknown.get(cat, 0.0) + r["amount"]
    out = [
        {"category": c, "amount": round(v, 2)}
        for c, v in totals.items()
    ]
    out.extend(
        {"category": c, "amount": round(v, 2), "legacy": True}
        for c, v in sorted(unknown.items(), key=lambda x: -x[1])
        if round(v, 2) != 0
    )
    return out


def summary(month: str | None = None, year: str | None = None) -> dict:
    """汇总统计：收支 + 报销细分 + 预算执行。

    口径（报销不计入收支，只影响余额）：
    - totals.expense / totals.income 不含任何报销
    - pending / settled：本期（月/年）垫付发生额 与 本期到账发生额（用于明细占比）
    - unreimbursed（未收回垫付）：截至期末的滚动余额 = 累计垫付 − 累计到账
      （与资产卡的「未收回垫付」、年度走势的「未收回垫付」同一口径，可累加核对）
    - net_income（净收入）= 收入 - 支出，不含报销
    """
    rows = list_transactions(month=month, year=year)

    totals = _aggregate_by_kind(rows)
    # 本期发生额（月/年内的垫付与到账），用于占比饼图
    pending_flow, settled_flow = _reimburse_totals(rows, month or year)
    # 滚动余额口径的未收回垫付：累计垫付 − 累计到账（截至期末）
    cum_pending, cum_settled = _reimburse_outstanding(_period_end(month, year))
    unreimbursed = round(max(0.0, cum_pending - cum_settled), 2)

    reimburse_detail = [
        {"category": "已报销", "amount": round(cum_settled, 2)},
        {"category": "未收回垫付", "amount": unreimbursed},
    ]

    expense_breakdown = _category_breakdown(rows, "expense", CATEGORIES["expense"])
    income_breakdown = _category_breakdown(rows, "income", CATEGORIES["income"])

    result = {
        "period": month or year or "全部",
        "totals": totals,
        "net_income": round(totals["income"] - totals["expense"], 2),
        "unreimbursed": unreimbursed,
        "net_expense": round(cum_pending, 2),   # 累计垫付（余额口径）
        "pending": pending_flow,                # 本期垫付发生额
        "settled": settled_flow,                # 本期到账发生额
        "breakdown": {
            "expense": expense_breakdown,
            "income": income_breakdown,
            "reimburse": reimburse_detail,
        },
    }

    # 预算执行（仅月维度有意义）
    if month:
        result["budget"] = budget_status(month)

    return result


def _month_of(d: str) -> int | None:
    """从 'YYYY-MM-DD' 取月份；格式不规范返回 None。"""
    if len(d) < 7:
        return None
    try:
        m = int(d[5:7])
    except ValueError:
        return None
    return m if 1 <= m <= 12 else None


def yearly_series(year: str) -> dict:
    """返回某年 12 个月的月度序列（用于年度折线图）。"""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT kind, amount, date FROM transactions WHERE date LIKE ?",
            (f"{year}%",),
        ).fetchall()
        ev_rows = conn.execute(
            "SELECT event_date, COALESCE(SUM(amount), 0) AS s FROM reimburse_events "
            "WHERE event_date LIKE ? GROUP BY event_date",
            (f"{year}%",),
        ).fetchall()
    finally:
        conn.close()

    months = list(range(1, 13))
    result = {m: {"expense": 0, "income": 0, "pending": 0, "settled": 0} for m in months}

    for r in rows:
        m = _month_of(r["date"])
        if m is None:
            continue
        kind = r["kind"]
        if kind == "expense":
            result[m]["expense"] += r["amount"]
        elif kind == "income":
            result[m]["income"] += r["amount"]
        elif kind == "reimburse":
            result[m]["pending"] += r["amount"]

    for r in ev_rows:
        m = _month_of(r["event_date"])
        if m is None:
            continue
        result[m]["settled"] += r["s"]

    # 未收回垫付统一走 _reimburse_outstanding（滚动余额口径），与 summary / balance 同源，
    # 避免手工累加导致口径漂移。
    series = []
    for m in months:
        v = result[m]
        net = v["income"] - v["expense"]
        end = f"{year}-{m:02d}-31"
        cum_p, cum_s = _reimburse_outstanding(end)
        outstanding = max(0.0, cum_p - cum_s)
        series.append({
            "month": m,
            "expense": round(_cents_to_yuan(v["expense"]), 2),
            "income": round(_cents_to_yuan(v["income"]), 2),
            "pending": round(_cents_to_yuan(v["pending"]), 2),
            "settled": round(_cents_to_yuan(v["settled"]), 2),
            "unreimbursed": round(outstanding, 2),
            "net_expense": round(_cents_to_yuan(v["pending"]), 2),
            "net_income": round(_cents_to_yuan(net), 2),
        })

    return {"year": year, "series": series}


def daily_net(year: str, month: str | None = None) -> dict:
    """按天聚合净收入（元）：'YYYY-MM-DD' ->（收入 − 支出）。

    口径与 summary.net_income 一致：报销垫付与到账都不计入净收入，
    垫付的回收情况请看未收回垫付（summary.unreimbursed / balance.outstanding）。
    """
    prefix = f"{year}-{month}%" if month else f"{year}%"
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT kind, amount, date FROM transactions WHERE date LIKE ?",
            (prefix,),
        ).fetchall()
    finally:
        conn.close()

    by_day: dict[str, dict[str, int]] = {}
    for r in rows:
        d = r["date"]
        if len(d) < 10:
            continue
        kind = r["kind"]
        if kind not in ("expense", "income"):
            continue
        day = by_day.setdefault(d, {"expense": 0, "income": 0})
        day[kind] += r["amount"]

    result = {
        d: round(_cents_to_yuan(v["income"] - v["expense"]), 2)
        for d, v in by_day.items()
    }
    return {"year": year, "month": month, "daily": result}


# ---------------------------------------------------------------------------
# 余额（多账户聚合）
# ---------------------------------------------------------------------------
def cumulative_net_income() -> float:
    """历史累计净收入（元）= 全部收入 - 全部支出（报销不计入）。

    直接走 SQL 聚合，避免为求两个和而把全量交易 + 每笔报销的到账明细都拉进内存。
    """
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN kind = 'income' THEN amount ELSE 0 END), 0) "
            "     - COALESCE(SUM(CASE WHEN kind = 'expense' THEN amount ELSE 0 END), 0) AS s "
            "FROM transactions"
        ).fetchone()
        return _cents_to_yuan(row["s"])
    finally:
        conn.close()


def _outstanding_total() -> float:
    """未收回垫付余额（元）；超额报销（收回 > 垫付）时可能为负。

    直接复用 _reimburse_outstanding（全量累计），与 summary / yearly_series 同源。
    """
    p, s = _reimburse_outstanding(None)
    return round(p - s, 2)


def balance() -> dict:
    """净资产 = 资产账户合计 + 历史累计净收入 - 未收回垫付。

    口径（重要，勿混用）：
    - 累计净收入 = 全部收入 − 全部支出，**不含报销**（报销是「应收款」而非收支）。
    - 未收回垫付 = 累计垫付 − 累计已报销到账，代表「已经花出去但还没收回」的钱。
    - 因此报销对净资产的净影响 = −垫付 + 已收回 = −未收回垫付，
      公式里减一次未收回垫付即等价于「减全额垫付、加已收回」，天然自洽。

    前提：资产账户里填的是**记账起点余额**（或未包含上述净收入/垫付流的快照）。
    若把账户维护成「当前真实余额」，就会与净收入、未收回垫付重复计算，导致总量偏大。
    """
    acct_total = accounts_total()
    net_income = cumulative_net_income()
    outstanding = _outstanding_total()
    return {
        "accounts": list_accounts(),
        "accounts_total": round(acct_total, 2),
        "net_income": net_income,
        "outstanding": outstanding,
        "balance": round(acct_total + net_income - outstanding, 2),
    }


# ---------------------------------------------------------------------------
# Excel 导出
# ---------------------------------------------------------------------------
def export_excel(year: str | None = None, month: str | None = None) -> bytes:
    """导出账目为 Excel（.xlsx），带排版：标题、表头、冻结首行、列宽。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise RuntimeError("缺少 openpyxl，请先安装：pip install openpyxl")

    rows = list_transactions(month=month, year=year)
    period = month or year or "全部"

    wb = Workbook()
    ws = wb.active
    ws.title = "账目明细"

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=9)
    title_cell = ws.cell(row=1, column=1, value=f"MaWork 记账明细（{period}）")
    title_cell.font = Font(size=14, bold=True)
    title_cell.alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 24

    headers = ["日期", "类型", "一级分类", "二级分类", "金额（元）", "已报销（元）", "未收回（元）", "说明", "记录时间"]
    header_fill = PatternFill("solid", fgColor="9A8C72")
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=2, column=col, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    for i, r in enumerate(rows, start=3):
        kind_label = KIND_LABELS.get(r["kind"], r["kind"])
        is_reimburse = r["kind"] == "reimburse"
        reimbursed = r.get("reimbursed", "") if is_reimburse else ""
        remaining = r.get("remaining", "") if is_reimburse else ""
        values = [
            r["date"], kind_label, r["category"], r.get("category2", "") or "",
            r["amount"], reimbursed, remaining, r["note"], r["created_at"],
        ]
        for col, v in enumerate(values, start=1):
            c = ws.cell(row=i, column=col, value=v)
            c.alignment = Alignment(vertical="center", wrap_text=(col == 8))
        ws.row_dimensions[i].height = 18

    # 合计行：金额按类型分列；未收回垫付用滚动余额口径（与页面一致）
    if rows:
        sr = 3 + len(rows)
        t = _aggregate_by_kind(rows)
        cum_p, cum_s = _reimburse_outstanding(_period_end(month, year))
        outstanding = max(0.0, cum_p - cum_s)
        cells = {
            1: "合计",
            2: f"支出 {t['expense']:.2f}",
            3: f"收入 {t['income']:.2f}",
            5: f"垫付 {t['reimburse']:.2f}",
            7: round(outstanding, 2),
        }
        for col, v in cells.items():
            c = ws.cell(row=sr, column=col, value=v)
            c.font = Font(bold=True)
        ws.cell(row=sr, column=8, value=f"未收回垫付为滚动余额（累计垫付−累计到账），非本期发生额").font = Font(size=10, color="808080")

    widths = [14, 16, 16, 12, 12, 14, 14, 40, 20]
    for col, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
