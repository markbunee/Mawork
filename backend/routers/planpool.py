"""日程任务路由。"""

import io
from datetime import date as date_cls

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..models.planpool import PROGRESS_OPTIONS, PROGRESS_TODO
from ..services import planpool

router = APIRouter(prefix="/api/planpool", tags=["planpool"])


# ---------------------------------------------------------------------------
# 元信息
# ---------------------------------------------------------------------------
@router.get("/meta")
def meta():
    return {"progress_options": PROGRESS_OPTIONS, "default_progress": PROGRESS_TODO}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
class TaskIn(BaseModel):
    level1: str = ""
    level2: str = ""
    progress: str = PROGRESS_TODO
    note: str = ""
    start_date: str = ""
    end_date: str = ""


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
        payload.level1, payload.level2, payload.progress,
        payload.note, payload.start_date, payload.end_date,
    )


@router.get("/tasks")
def list_tasks(month: str | None = None):
    return planpool.list_tasks(month=month)


@router.put("/tasks/{tid}")
def update_task(tid: int, payload: TaskIn):
    _validate_dates(payload.start_date, payload.end_date)
    tx = planpool.update_task(
        tid, payload.level1, payload.level2, payload.progress,
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


@router.post("/tasks/{tid}/checkin")
def checkin(tid: int, date: str):
    """为任务在某天打卡（date=YYYY-MM-DD）。"""
    tx = planpool.checkin(tid, date)
    if tx is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return tx


@router.delete("/tasks/{tid}/checkin")
def uncheckin(tid: int, date: str):
    """取消某天打卡。"""
    tx = planpool.uncheckin(tid, date)
    if tx is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return tx


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
