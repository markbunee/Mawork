"""记账路由。"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import io

from ..models.accounting import CATEGORY_TREE, CATEGORIES, KIND_LABELS, REIMBURSE_STATUSES
from ..services import accounting

router = APIRouter(prefix="/api/accounting", tags=["accounting"])


# ---------------------------------------------------------------------------
# 元信息：分类、类型
# ---------------------------------------------------------------------------
@router.get("/meta")
def meta():
    return {
        "kinds": [
            {
                "value": "expense",
                "label": KIND_LABELS["expense"],
                "categories": CATEGORIES["expense"],
                "category2": CATEGORY_TREE["expense"],
            },
            {
                "value": "income",
                "label": KIND_LABELS["income"],
                "categories": CATEGORIES["income"],
                "category2": CATEGORY_TREE["income"],
            },
            {
                "value": "reimburse",
                "label": KIND_LABELS["reimburse"],
                "categories": REIMBURSE_STATUSES,
                "category2": CATEGORY_TREE["reimburse"],
            },
        ]
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
class TransactionIn(BaseModel):
    kind: str
    category: str
    category2: str = ""  # 二级分类，可选
    amount: float = Field(gt=0)
    note: str = ""
    date: str  # YYYY-MM-DD


@router.post("/transactions")
def create_transaction(payload: TransactionIn):
    _validate(payload.kind, payload.category, payload.category2)
    return accounting.create_transaction(
        payload.kind, payload.category, payload.amount, payload.note, payload.date,
        category2=payload.category2,
    )


@router.get("/transactions")
def list_transactions(kind: str | None = None, year: str | None = None, month: str | None = None):
    return accounting.list_transactions(kind=kind, year=year, month=month)


@router.put("/transactions/{tid}")
def update_transaction(tid: int, payload: TransactionIn):
    _validate(payload.kind, payload.category, payload.category2)
    return accounting.update_transaction(
        tid,
        kind=payload.kind,
        category=payload.category,
        category2=payload.category2,
        amount=payload.amount,
        note=payload.note,
        date=payload.date,
    )


@router.delete("/transactions/{tid}")
def delete_transaction(tid: int):
    if not accounting.delete_transaction(tid):
        raise HTTPException(status_code=404, detail="账目不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 报销事件（事件化：每笔到账一条记录，支持部分/多次报销）
# ---------------------------------------------------------------------------
class ReimburseEventIn(BaseModel):
    amount: float = Field(gt=0)
    event_date: str  # YYYY-MM-DD 到账日期
    note: str = ""


@router.post("/transactions/{tid}/reimburse-events")
def create_reimburse_event(tid: int, payload: ReimburseEventIn):
    try:
        return accounting.create_reimburse_event(
            tid, payload.amount, payload.event_date, payload.note
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/transactions/{tid}/reimburse-events")
def list_reimburse_events(tid: int):
    return accounting.list_reimburse_events(tid)


@router.delete("/reimburse-events/{eid}")
def delete_reimburse_event(eid: int):
    if not accounting.delete_reimburse_event(eid):
        raise HTTPException(status_code=404, detail="报销事件不存在")
    return {"ok": True}


@router.post("/transactions/{tid}/settle")
def settle_reimbursement(tid: int):
    """快捷：按剩余金额全额报销（到账日期为今天）。"""
    ev = accounting.settle_reimbursement(tid)
    if ev is None:
        raise HTTPException(status_code=400, detail="该账目不可报销或已全部报销")
    return ev


# ---------------------------------------------------------------------------
# 资产账户（多账户资产负债表）
# ---------------------------------------------------------------------------
class AccountIn(BaseModel):
    name: str = ""
    type: str = "cash"
    balance: float = 0


@router.get("/accounts")
def list_accounts():
    return accounting.list_accounts()


@router.post("/accounts")
def create_account(payload: AccountIn):
    try:
        return accounting.create_account(payload.name, payload.type, payload.balance)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/accounts/{aid}")
def update_account(aid: int, payload: AccountIn):
    return accounting.update_account(aid, payload.name, payload.type, payload.balance)


@router.delete("/accounts/{aid}")
def delete_account(aid: int):
    if not accounting.delete_account(aid):
        raise HTTPException(status_code=404, detail="账户不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 预算
# ---------------------------------------------------------------------------
class BudgetIn(BaseModel):
    period: str  # YYYY-MM
    scope: str = "total"  # total / category
    category: str = ""
    limit: float = 0


@router.get("/budgets")
def list_budgets(period: str):
    return accounting.list_budgets(period)


@router.post("/budgets")
def create_budget(payload: BudgetIn):
    return accounting.create_budget(payload.period, payload.scope, payload.category, payload.limit)


@router.put("/budgets/{bid}")
def update_budget(bid: int, payload: BudgetIn):
    return accounting.update_budget(bid, payload.limit)


@router.delete("/budgets/{bid}")
def delete_budget(bid: int):
    if not accounting.delete_budget(bid):
        raise HTTPException(status_code=404, detail="预算不存在")
    return {"ok": True}


@router.get("/budgets/status")
def budgets_status(period: str):
    return accounting.budget_status(period)


# ---------------------------------------------------------------------------
# 周期账
# ---------------------------------------------------------------------------
class RecurringIn(BaseModel):
    kind: str
    category: str
    category2: str = ""
    amount: float | None = None
    note: str = ""
    freq: str = "monthly"
    day_of_month: int = 1
    account: str = ""
    active: bool = True


@router.get("/recurring")
def list_recurring():
    return accounting.list_recurring()


@router.post("/recurring")
def create_recurring(payload: RecurringIn):
    _validate(payload.kind, payload.category, payload.category2)
    return accounting.create_recurring(payload.model_dump())


@router.put("/recurring/{rid}")
def update_recurring(rid: int, payload: RecurringIn):
    _validate(payload.kind, payload.category, payload.category2)
    return accounting.update_recurring(rid, payload.model_dump())


@router.delete("/recurring/{rid}")
def delete_recurring(rid: int):
    if not accounting.delete_recurring(rid):
        raise HTTPException(status_code=404, detail="周期账不存在")
    return {"ok": True}


@router.post("/recurring/apply")
def apply_recurring(period: str):
    return accounting.apply_recurring(period)


# ---------------------------------------------------------------------------
# 统计与导出
# ---------------------------------------------------------------------------
@router.get("/summary")
def summary(month: str | None = None, year: str | None = None):
    return accounting.summary(month=month, year=year)


@router.get("/series")
def series(year: str):
    return accounting.yearly_series(year)


@router.get("/daily")
def daily(year: str, month: str | None = None):
    return accounting.daily_net(year, month=month)


@router.get("/settings")
def get_settings():
    return accounting.balance()


@router.put("/settings")
def save_settings(payload: AccountIn):
    """已下线：多账户模型上线后，单账户的「存款/储蓄」两个数字被 accounts 表取代。

    原实现直接丢弃 payload 并返回 balance()，调用方会误以为保存成功。
    这里明确返回 410 Gone 并指向新接口，不再假装成功。
    （前端已不再调用此接口，改用 /accounts。）
    """
    raise HTTPException(
        status_code=410,
        detail="该接口已废弃，请改用 /api/accounting/accounts 更新账户余额",
    )


@router.get("/export")
def export(year: str | None = None, month: str | None = None):
    try:
        data = accounting.export_excel(year=year, month=month)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    filename = f"accounting_{month or year or 'all'}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def _validate(kind: str, category: str, category2: str = ""):
    if kind not in CATEGORIES:
        raise HTTPException(status_code=400, detail="未知账目类型")
    if category not in CATEGORIES[kind]:
        raise HTTPException(status_code=400, detail="分类不属于该类型")
    subs = CATEGORY_TREE[kind].get(category, [])
    if category2 and subs and category2 not in subs:
        raise HTTPException(status_code=400, detail="二级分类不属于该一级分类")
