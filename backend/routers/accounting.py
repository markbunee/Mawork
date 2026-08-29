"""记账路由。"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import io

from .. import db
from ..models.accounting import CATEGORIES, KIND_LABELS, REIMBURSE_STATUSES
from ..services import accounting

router = APIRouter(prefix="/api/accounting", tags=["accounting"])


# ---------------------------------------------------------------------------
# 元信息：分类、类型
# ---------------------------------------------------------------------------
@router.get("/meta")
def meta():
    return {
        "kinds": [
            {"value": "expense", "label": KIND_LABELS["expense"], "categories": CATEGORIES["expense"]},
            {"value": "income", "label": KIND_LABELS["income"], "categories": CATEGORIES["income"]},
            {"value": "reimburse", "label": KIND_LABELS["reimburse"], "categories": REIMBURSE_STATUSES},
        ]
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
class TransactionIn(BaseModel):
    kind: str
    category: str
    amount: float = Field(gt=0)
    note: str = ""
    date: str  # YYYY-MM-DD


@router.post("/transactions")
def create_transaction(payload: TransactionIn):
    _validate(payload.kind, payload.category)
    return accounting.create_transaction(
        payload.kind, payload.category, payload.amount, payload.note, payload.date
    )


@router.get("/transactions")
def list_transactions(kind: str | None = None, year: str | None = None, month: str | None = None):
    return accounting.list_transactions(kind=kind, year=year, month=month)


@router.put("/transactions/{tid}")
def update_transaction(tid: int, payload: TransactionIn):
    return accounting.update_transaction(
        tid,
        kind=payload.kind,
        category=payload.category,
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
# 报销转抵
# ---------------------------------------------------------------------------
@router.post("/transactions/{tid}/settle")
def settle_reimbursement(tid: int):
    tx = accounting.settle_reimbursement(tid)
    if tx is None:
        raise HTTPException(status_code=400, detail="仅「待报销」可转为「已报销」")
    return tx


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
def _validate(kind: str, category: str):
    if kind not in CATEGORIES:
        raise HTTPException(status_code=400, detail="未知账目类型")
    if category not in CATEGORIES[kind]:
        raise HTTPException(status_code=400, detail="分类不属于该类型")
