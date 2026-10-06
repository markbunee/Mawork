"""习惯培养路由：习惯 CRUD、打卡、统计与日历映射。"""

import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services import habit as habit_svc

router = APIRouter(prefix="/api/habit", tags=["habit"])

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class HabitIn(BaseModel):
    name: str = ""
    reason: str = ""
    emoji: str = "🔴"
    freq_type: str = "daily"
    freq_days: str = ""
    start_date: str = ""


@router.get("/habits")
def list_habits(archived: bool = False):
    return {"habits": habit_svc.list_habits(include_archived=archived)}


@router.post("/habits")
def create_habit(payload: HabitIn):
    try:
        return habit_svc.create_habit(
            payload.name,
            payload.reason,
            payload.emoji,
            payload.freq_type,
            payload.freq_days,
            payload.start_date or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/habits/{hid}")
def update_habit(hid: int, payload: HabitIn):
    h = habit_svc.update_habit(
        hid,
        name=payload.name,
        reason=payload.reason,
        emoji=payload.emoji,
        freq_type=payload.freq_type,
        freq_days=payload.freq_days,
        start_date=payload.start_date,
    )
    if h is None:
        raise HTTPException(status_code=404, detail="习惯不存在")
    return h


@router.delete("/habits/{hid}")
def delete_habit(hid: int):
    if not habit_svc.archive_habit(hid):
        raise HTTPException(status_code=404, detail="习惯不存在")
    return {"ok": True}


@router.get("/habits/{hid}/logs")
def habit_logs(hid: int):
    return {"habit_id": hid, "dates": habit_svc.log_dates(hid)}


@router.post("/habits/{hid}/checkin")
def checkin(hid: int, date: str | None = Query(None)):
    if date and not DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    res = habit_svc.checkin(hid, date)
    if res is None:
        raise HTTPException(status_code=404, detail="习惯不存在")
    return {"log": res, "stats": habit_svc.compute_stats(hid)}


@router.delete("/habits/{hid}/checkin/{date}")
def uncheck(hid: int, date: str):
    if not DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    return habit_svc.uncheck(hid, date)


@router.get("/stats")
def stats():
    return habit_svc.board_stats()


@router.get("/by_date")
def by_date(date: str = Query(...)):
    if not DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    return {"date": date, "habits": habit_svc.list_for_date(date)}


@router.get("/calendar")
def calendar(frm: str = Query(..., alias="from"), to: str = Query(...)):
    if not DATE_RE.match(frm) or not DATE_RE.match(to):
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    if frm > to:
        raise HTTPException(status_code=422, detail="起始日期不能晚于结束日期")
    return {"map": habit_svc.calendar_map(frm, to)}
