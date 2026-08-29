"""记账业务逻辑：增删改查、统计聚合、报销转抵、Excel 导出。"""

import io
import sqlite3
from datetime import datetime

from .. import db
from ..models.accounting import (
    CATEGORIES,
    KIND_LABELS,
    REIMBURSE_STATUSES,
)


# ---------------------------------------------------------------------------
# 基础 CRUD
# ---------------------------------------------------------------------------
def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["amount"] = d["amount"] / 100.0  # 分 → 元
    return d


def create_transaction(kind: str, category: str, amount_yuan: float, note: str, date: str) -> dict:
    """新增一笔账。amount_yuan 为元，内部转分存储。"""
    amount_cents = int(round(amount_yuan * 100))
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


def list_transactions(
    kind: str | None = None,
    year: str | None = None,
    month: str | None = None,
) -> list[dict]:
    """按条件查询账目。month 为 'YYYY-MM'，year 为 'YYYY'。"""
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
        return [_row_to_dict(r) for r in rows]
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
        updates["amount"] = int(round(updates["amount"] * 100))

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
        cur = conn.execute("DELETE FROM transactions WHERE id = ?", (tid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 报销：待报销 → 已报销（抵消）
# ---------------------------------------------------------------------------
def settle_reimbursement(tid: int) -> dict | None:
    """将一笔「待报销」转为「已报销」。"""
    tx = get_transaction(tid)
    if tx is None or tx["kind"] != "reimburse" or tx["category"] != "待报销":
        return None
    return update_transaction(tid, category="已报销")


# ---------------------------------------------------------------------------
# 统计聚合
# ---------------------------------------------------------------------------
def _aggregate_by_kind(rows: list[dict]) -> dict:
    """按 kind 汇总金额。"""
    result = {k: 0.0 for k in KIND_LABELS}
    for r in rows:
        result[r["kind"]] += r["amount"]
    return {k: round(v, 2) for k, v in result.items()}


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
    """汇总统计：三类总额 + 各类子分类占比 + 净支出。"""
    rows = list_transactions(month=month, year=year)

    totals = _aggregate_by_kind(rows)

    # 报销内部细分：待报销 / 已报销
    reimburse_detail = _category_breakdown(rows, "reimburse", REIMBURSE_STATUSES)

    expense_breakdown = _category_breakdown(rows, "expense", CATEGORIES["expense"])
    income_breakdown = _category_breakdown(rows, "income", CATEGORIES["income"])

    settled = next(
        (d["amount"] for d in reimburse_detail if d["category"] == "已报销"), 0.0
    )
    net_expense = round(totals["expense"] - settled, 2)

    return {
        "period": month or year or "全部",
        "totals": totals,
        "net_expense": net_expense,
        "breakdown": {
            "expense": expense_breakdown,
            "income": income_breakdown,
            "reimburse": reimburse_detail,
        },
    }


def yearly_series(year: str) -> dict:
    """返回某年 12 个月的月度序列（用于年度折线图）。

    每月统计：
    - expense  支出
    - income   收入
    - net_expense  净支出 = 支出 - 已报销
    - net_income   净收入 = 收入 - 净支出
    """
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT kind, category, amount, date FROM transactions WHERE date LIKE ?",
            (f"{year}%",),
        ).fetchall()
    finally:
        conn.close()

    months = list(range(1, 13))
    result = {m: {"expense": 0.0, "income": 0.0, "reimburse_settled": 0.0} for m in months}

    for r in rows:
        d = r["date"]
        if len(d) < 7:
            continue
        try:
            m = int(d[5:7])
        except ValueError:
            continue
        if m not in result:
            continue
        kind = r["kind"]
        amount = r["amount"]
        if kind == "expense":
            result[m]["expense"] += amount
        elif kind == "income":
            result[m]["income"] += amount
        elif kind == "reimburse" and r["category"] == "已报销":
            result[m]["reimburse_settled"] += amount

    series = []
    for m in months:
        expense = result[m]["expense"]
        income = result[m]["income"]
        settled = result[m]["reimburse_settled"]
        net_expense = expense - settled
        net_income = income - net_expense
        series.append({
            "month": m,
            "expense": round(expense, 2),
            "income": round(income, 2),
            "net_expense": round(net_expense, 2),
            "net_income": round(net_income, 2),
        })

    return {"year": year, "series": series}


def daily_net(year: str, month: str | None = None) -> dict:
    """按天聚合净收入。

    返回该年（或该月）每一天的净收入：
    - net_income = 收入 - (支出 - 已报销)
    - 仅返回有记录的日期，无记录日期不含在内（前端可自行补 0）。
    """
    conn = db.get_conn()
    try:
        if month:
            rows = conn.execute(
                "SELECT kind, category, amount, date FROM transactions WHERE date LIKE ?",
                (f"{year}-{month}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT kind, category, amount, date FROM transactions WHERE date LIKE ?",
                (f"{year}%",),
            ).fetchall()
    finally:
        conn.close()

    # date -> {expense, income, settled}
    by_day: dict[str, dict[str, float]] = {}
    for r in rows:
        d = r["date"]
        if len(d) < 10:
            continue
        day = by_day.setdefault(d, {"expense": 0.0, "income": 0.0, "settled": 0.0})
        kind = r["kind"]
        if kind == "expense":
            day["expense"] += r["amount"]
        elif kind == "income":
            day["income"] += r["amount"]
        elif kind == "reimburse" and r["category"] == "已报销":
            day["settled"] += r["amount"]

    result = {}
    for d, v in by_day.items():
        net_expense = v["expense"] - v["settled"]
        net_income = v["income"] - net_expense
        result[d] = round(net_income, 2)

    return {"year": year, "month": month, "daily": result}


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
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
    title_cell = ws.cell(row=1, column=1, value=f"MaWork 记账明细（{period}）")
    title_cell.font = Font(size=14, bold=True)
    title_cell.alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 24

    # 表头
    headers = ["日期", "类型", "分类", "金额（元）", "说明", "记录时间"]
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
        values = [r["date"], kind_label, r["category"], r["amount"], r["note"], r["created_at"]]
        for col, v in enumerate(values, start=1):
            c = ws.cell(row=i, column=col, value=v)
            c.alignment = Alignment(vertical="center", wrap_text=(col == 5))
        ws.row_dimensions[i].height = 18

    # 列宽
    widths = [14, 10, 12, 12, 40, 20]
    for col, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = w

    # 冻结首两行 + 表头
    ws.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
