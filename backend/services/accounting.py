"""记账业务逻辑：增删改查、统计聚合、报销事件、Excel 导出。

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
    return int((Decimal(str(yuan)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _cents_to_yuan(cents: int) -> float:
    """分 → 元（Decimal 计算，避免浮点误差）。"""
    return float(Decimal(cents) / 100)


# ---------------------------------------------------------------------------
# 基础 CRUD
# ---------------------------------------------------------------------------
def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["amount"] = _cents_to_yuan(d["amount"])  # 分 → 元
    return d


def create_transaction(kind: str, category: str, amount_yuan: float, note: str, date: str) -> dict:
    """新增一笔账。amount_yuan 为元，内部转分存储。"""
    amount_cents = _yuan_to_cents(amount_yuan)
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO transactions (kind, category, amount, note, date) "
            "VALUES (?, ?, ?, ?, ?)",
            (kind, category, amount_cents, note, date),
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
    allowed = {"kind", "category", "amount", "note", "date"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_transaction(tid)

    if "amount" in updates:
        updates["amount"] = _yuan_to_cents(updates["amount"])

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
    """为「待报销」账目创建一条报销事件（部分报销 / 多次报销 / 可追溯）。

    校验：报销总额（含本次）不得超过该笔待报销的原始金额。
    """
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
    """报销细分：返回 (本期待报销原始额, 本期报销到账额)（元）。

    - pending（待报销）：按 transactions.date 归属本期，是本期垫付的金额
    - settled（已报销）：按 reimburse_events.event_date 归属本期，是本期到账的金额
    """
    pending = 0.0
    for r in rows:
        if r["kind"] == "reimburse":
            pending += r["amount"]
    return round(pending, 2), round(_events_total(period_prefix), 2)


def _category_breakdown(rows: list[dict], kind: str, categories: list[str]) -> list[dict]:
    """按子分类汇总某类账目的金额占比。"""
    totals = {c: 0.0 for c in categories}
    for r in rows:
        if r["kind"] == kind and r["category"] in totals:
            totals[r["category"]] += r["amount"]
    return [
        {"category": c, "amount": round(v, 2)}
        for c, v in totals.items()
    ]


def summary(month: str | None = None, year: str | None = None) -> dict:
    """汇总统计：收支 + 报销细分。

    口径（报销不计入收支，只影响余额）：
    - totals.expense / totals.income 不含任何报销
    - pending（未报销费用）= 本期垫付的待报销总额
    - settled（已报销到账）= 本期报销事件到账总额
    - net_income（净收入）= 收入 - 支出，不含报销
    """
    rows = list_transactions(month=month, year=year)

    totals = _aggregate_by_kind(rows)
    pending, settled = _reimburse_totals(rows, month or year)

    # 报销占比：本期垫付（待报销）/ 本期到账（已报销）
    reimburse_detail = [
        {"category": "待报销", "amount": pending},
        {"category": "已报销", "amount": settled},
    ]

    expense_breakdown = _category_breakdown(rows, "expense", CATEGORIES["expense"])
    income_breakdown = _category_breakdown(rows, "income", CATEGORIES["income"])

    return {
        "period": month or year or "全部",
        "totals": totals,
        # 净收入 = 收入 - 支出（不含报销）
        "net_income": round(totals["income"] - totals["expense"], 2),
        # 未报销费用 = 待报销 − 已报销（按当前 month/year/全部 口径，与余额全累计一致）
        "unreimbursed": round(max(0.0, pending - settled), 2),
        # 兼容旧字段名
        "net_expense": round(pending, 2),
        "pending": pending,
        "settled": settled,
        "breakdown": {
            "expense": expense_breakdown,
            "income": income_breakdown,
            "reimburse": reimburse_detail,
        },
    }


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
    """返回某年 12 个月的月度序列（用于年度折线图）。

    每月口径（与 summary / daily_net 一致）：
    - expense  支出（不含报销）
    - income   收入（不含报销）
    - pending  本月垫付的待报销总额
    - settled  本月报销到账总额
    - net_income = 收入 - 支出（报销不计入收支，只影响余额）
    """
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

    series = []
    for m in months:
        v = result[m]
        # 净收入 = 收入 - 支出（报销不计入收支）
        net = v["income"] - v["expense"]
        series.append({
            "month": m,
            "expense": round(_cents_to_yuan(v["expense"]), 2),
            "income": round(_cents_to_yuan(v["income"]), 2),
            "pending": round(_cents_to_yuan(v["pending"]), 2),
            "settled": round(_cents_to_yuan(v["settled"]), 2),
            "net_expense": round(_cents_to_yuan(v["pending"]), 2),
            "net_income": round(_cents_to_yuan(net), 2),
        })

    return {"year": year, "series": series}


def daily_net(year: str, month: str | None = None) -> dict:
    """按天聚合净收入。

    每日口径：net_income = 收入 - 支出。
    报销（垫付/到账）不计入收支，只影响余额，因此日历上不会因报销产生正负波动。
    仅返回有记录的日期。
    """
    conn = db.get_conn()
    try:
        if month:
            rows = conn.execute(
                "SELECT kind, amount, date FROM transactions WHERE date LIKE ?",
                (f"{year}-{month}%",),
            ).fetchall()
            ev_rows = conn.execute(
                "SELECT event_date, COALESCE(SUM(amount), 0) AS s FROM reimburse_events "
                "WHERE event_date LIKE ? GROUP BY event_date",
                (f"{year}-{month}%",),
            ).fetchall()
        else:
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

    # date -> {expense, income, pending, settled}
    by_day: dict[str, dict[str, int]] = {}
    for r in rows:
        d = r["date"]
        if len(d) < 10:
            continue
        day = by_day.setdefault(d, {"expense": 0, "income": 0, "pending": 0, "settled": 0})
        kind = r["kind"]
        if kind == "expense":
            day["expense"] += r["amount"]
        elif kind == "income":
            day["income"] += r["amount"]
        elif kind == "reimburse":
            day["pending"] += r["amount"]

    for r in ev_rows:
        d = r["event_date"]
        if len(d) < 10:
            continue
        day = by_day.setdefault(d, {"expense": 0, "income": 0, "pending": 0, "settled": 0})
        day["settled"] += r["s"]

    result = {}
    for d, v in by_day.items():
        # 净收入 = 收入 - 支出；报销（垫付/到账）不计入收支，只影响余额
        net = v["income"] - v["expense"]
        result[d] = round(_cents_to_yuan(net), 2)

    return {"year": year, "month": month, "daily": result}


# ---------------------------------------------------------------------------
# 存款 / 储蓄设置与余额
# ---------------------------------------------------------------------------
def get_settings() -> dict:
    """读取存款/储蓄设置（分 → 元）。"""
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM account_settings").fetchall()
    finally:
        conn.close()
    settings = {"deposit": 0.0, "saving": 0.0}
    for r in rows:
        if r["key"] in settings:
            try:
                settings[r["key"]] = _cents_to_yuan(int(r["value"]))
            except (TypeError, ValueError):
                pass
    return settings


def save_settings(deposit: float, saving: float) -> dict:
    """保存存款/储蓄（元 → 分）。"""
    conn = db.get_conn()
    try:
        for key, yuan in (("deposit", deposit), ("saving", saving)):
            cents = _yuan_to_cents(yuan)
            conn.execute(
                "INSERT INTO account_settings (key, value, updated_at) "
                "VALUES (?, ?, datetime('now', 'localtime')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, str(cents)),
            )
        conn.commit()
    finally:
        conn.close()
    return get_settings()


def cumulative_net_income() -> float:
    """历史累计净收入（元）= 全部收入 - 全部支出。

    报销（垫付 / 到账）不计入收支；垫付占用的资金通过「未收回垫付」
    在余额中体现（见 _outstanding_total / balance）。
    """
    rows = list_transactions()
    totals = _aggregate_by_kind(rows)
    return round(totals["income"] - totals["expense"], 2)


def _outstanding_total() -> float:
    """未收回垫付余额（元）= 全部待报销原始额 - 全部报销到账额。

    这是「钱已经垫出去、但还没报销回来」的部分，只影响余额，不影响净收入。
    """
    conn = db.get_conn()
    try:
        pending = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM transactions WHERE kind = 'reimburse'"
        ).fetchone()["s"]
        settled = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM reimburse_events"
        ).fetchone()["s"]
        return _cents_to_yuan(pending - settled)
    finally:
        conn.close()


def balance() -> dict:
    """余额 = 存款 + 储蓄 + 历史累计净收入 - 未收回垫付。

    报销不占用收入（净收入 = 收入 - 支出），但垫付的钱确实已经花出去，
    因此通过「未收回垫付」扣减；报销到账后该部分自动回补。
    """
    settings = get_settings()
    net_income = cumulative_net_income()
    outstanding = _outstanding_total()
    deposit = settings["deposit"]
    saving = settings["saving"]
    return {
        "deposit": deposit,
        "saving": saving,
        "net_income": net_income,
        "outstanding": outstanding,
        "balance": round(deposit + saving + net_income - outstanding, 2),
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

    # 标题
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=7)
    title_cell = ws.cell(row=1, column=1, value=f"MaWork 记账明细（{period}）")
    title_cell.font = Font(size=14, bold=True)
    title_cell.alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 24

    # 表头
    headers = ["日期", "类型", "分类", "金额（元）", "已报销（元）", "说明", "记录时间"]
    header_fill = PatternFill("solid", fgColor="9A8C72")
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=2, column=col, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    # 数据
    for i, r in enumerate(rows, start=3):
        kind_label = KIND_LABELS.get(r["kind"], r["kind"])
        reimbursed = r.get("reimbursed", "") if r["kind"] == "reimburse" else ""
        values = [r["date"], kind_label, r["category"], r["amount"], reimbursed, r["note"], r["created_at"]]
        for col, v in enumerate(values, start=1):
            c = ws.cell(row=i, column=col, value=v)
            c.alignment = Alignment(vertical="center", wrap_text=(col == 6))
        ws.row_dimensions[i].height = 18

    # 列宽
    widths = [14, 10, 12, 12, 14, 40, 20]
    for col, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = w

    # 冻结首两行 + 表头
    ws.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
