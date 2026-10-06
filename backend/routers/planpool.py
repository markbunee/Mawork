"""日程任务路由：一张极简 Excel 网格表的增删改查。"""

import io
from datetime import date as date_cls

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..models.planpool import DEFAULT_COMPLETION, DEFAULT_PROGRESS, PROGRESS_OPTIONS
from ..services import planpool

router = APIRouter(prefix="/api/planpool", tags=["planpool"])


# ---------------------------------------------------------------------------
# 元信息
# ---------------------------------------------------------------------------
@router.get("/meta")
def meta():
    return {
        "progress_options": PROGRESS_OPTIONS,
        "default_progress": DEFAULT_PROGRESS,
        "default_completion": DEFAULT_COMPLETION,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
class TaskIn(BaseModel):
    level1: str = ""
    title: str = ""
    progress: str = DEFAULT_PROGRESS
    completion: int = DEFAULT_COMPLETION
    note: str = ""
    start_date: str = ""
    end_date: str = ""


class ColumnIn(BaseModel):
    label: str
    ftype: str = "text"  # text | date | number | select | check
    options: list[str] = []


class ColumnPatch(BaseModel):
    label: str | None = None
    ftype: str | None = None
    options: list[str] | None = None
    visible: bool | None = None
    pinned: bool | None = None


class ColumnOrder(BaseModel):
    ids: list[int]


class CellsIn(BaseModel):
    fields: dict[str, object]


class ApplyTemplate(BaseModel):
    name: str


def _validate_dates(start_date: str, end_date: str):
    """开始日期 ≤ 结束日期。两者均可为空，若都填写则校验。"""
    if not start_date or not end_date:
        return
    try:
        s = date_cls.fromisoformat(start_date)
        e = date_cls.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    if s > e:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")


@router.post("/tasks")
def create_task(payload: TaskIn):
    _validate_dates(payload.start_date, payload.end_date)
    return planpool.create_task(
        payload.level1, payload.title, payload.progress, payload.completion,
        payload.note, payload.start_date, payload.end_date,
    )


@router.get("/tasks")
def list_tasks(month: str | None = None):
    return planpool.list_tasks(month=month)


@router.put("/tasks/{tid}")
def update_task(tid: int, payload: TaskIn):
    _validate_dates(payload.start_date, payload.end_date)
    tx = planpool.update_task(
        tid, payload.level1, payload.title, payload.progress, payload.completion,
        payload.note, payload.start_date, payload.end_date,
    )
    if tx is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return tx


@router.delete("/tasks/{tid}")
def delete_task(tid: int):
    if not planpool.delete_task(tid):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 灵活列（自由增删 / 重排 / 类型 / 可见性）
# ---------------------------------------------------------------------------
@router.get("/columns")
def columns():
    return planpool.list_columns()


@router.post("/columns")
def create_column(payload: ColumnIn):
    return planpool.add_column(payload.label, payload.ftype, payload.options)


@router.put("/columns/order")
def order_columns(payload: ColumnOrder):
    planpool.set_columns_order(payload.ids)
    return planpool.list_columns()


@router.put("/columns/{cid}")
def patch_column(cid: int, payload: ColumnPatch):
    col = planpool.update_column(
        cid,
        label=payload.label,
        ftype=payload.ftype,
        options=payload.options,
        visible=payload.visible,
        pinned=payload.pinned,
    )
    if col is None:
        raise HTTPException(status_code=404, detail="列不存在")
    return col


@router.delete("/columns/{cid}")
def remove_column(cid: int):
    if not planpool.delete_column(cid):
        raise HTTPException(status_code=400, detail="内置列不可删除")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 自定义列单元格
# ---------------------------------------------------------------------------
@router.put("/tasks/{tid}/cells")
def put_cells(tid: int, payload: CellsIn):
    planpool.upsert_cells(tid, payload.fields)
    return {"ok": True}


# ---------------------------------------------------------------------------
# 预设列模板
# ---------------------------------------------------------------------------
@router.get("/templates")
def templates():
    return planpool.list_templates()


@router.post("/templates/apply")
def apply(payload: ApplyTemplate):
    return planpool.apply_template(payload.name)


class ApplyColumns(BaseModel):
    columns: list = []


@router.post("/templates/apply_json")
def apply_json(payload: ApplyColumns):
    """按列定义 JSON 重建自定义列（统一模板库 E3 的「任务表」模板走此接口）。"""
    return planpool.apply_columns_json(payload.columns)


# ---------------------------------------------------------------------------
# 统计与导出
# ---------------------------------------------------------------------------
@router.get("/stats")
def stats(month: str | None = None):
    return planpool.stats(month=month)


@router.get("/export")
def export():
    try:
        data = planpool.export_excel()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=planpool.xlsx"},
    )
