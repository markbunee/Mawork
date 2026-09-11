"""计时器路由：四种模式的 CRUD、运行控制与耗时统计。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..models.timer import (
    DEFAULT_STATUS,
    DEFAULT_TYPE,
    STATUS_OPTIONS,
    TIMER_TYPES,
    TYPE_LABELS,
)
from ..services import timer as svc

router = APIRouter(prefix="/api/timer", tags=["timer"])


# ---------------------------------------------------------------------------
# 元信息
# ---------------------------------------------------------------------------
@router.get("/meta")
def meta():
    return {
        "types": TIMER_TYPES,
        "type_labels": TYPE_LABELS,
        "status_options": STATUS_OPTIONS,
        "default_type": DEFAULT_TYPE,
        "default_status": DEFAULT_STATUS,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
class TimerIn(BaseModel):
    type: str = DEFAULT_TYPE
    title: str = ""
    note: str = ""
    target_at: str = ""
    start_at: str = ""
    status: str = DEFAULT_STATUS


@router.post("/timers")
def create(payload: TimerIn):
    return svc.create_timer(
        payload.type, payload.title, payload.note, payload.target_at, payload.start_at, payload.status
    )


@router.get("/timers")
def list_timers(type: str | None = None):
    return svc.list_timers(type)


@router.put("/timers/{tid}")
def update(tid: int, payload: TimerIn):
    t = svc.update_timer(
        tid, payload.type, payload.title, payload.note, payload.target_at, payload.start_at, payload.status
    )
    if t is None:
        raise HTTPException(status_code=404, detail="计时器不存在")
    return t


@router.delete("/timers/{tid}")
def delete(tid: int):
    if not svc.delete_timer(tid):
        raise HTTPException(status_code=404, detail="计时器不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 运行控制（仅对正计时生效，其余模式静默返回）
# ---------------------------------------------------------------------------
@router.post("/timers/{tid}/start")
def start(tid: int):
    t = svc.start_timer(tid)
    if t is None:
        raise HTTPException(status_code=404, detail="计时器不存在")
    return t


@router.post("/timers/{tid}/stop")
def stop(tid: int):
    t = svc.stop_timer(tid)
    if t is None:
        raise HTTPException(status_code=404, detail="计时器不存在")
    return t


@router.post("/timers/{tid}/reset")
def reset(tid: int):
    t = svc.reset_timer(tid)
    if t is None:
        raise HTTPException(status_code=404, detail="计时器不存在")
    return t


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
@router.get("/stats")
def stats(granularity: str = "day"):
    if granularity not in ("day", "week", "month"):
        raise HTTPException(status_code=422, detail="granularity 仅支持 day / week / month")
    return svc.stats(granularity)
