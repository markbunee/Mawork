"""日历文本格路由：按天读写可直接输入的文本行（日报已入库，任务行由日报页读取展示）。"""

import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import calday

router = APIRouter(prefix="/api/calday", tags=["calday"])

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class CalLineIn(BaseModel):
    kind: str = "text"
    text: str = ""
    done: bool = False


class CalDayIn(BaseModel):
    lines: list[CalLineIn] = Field(default_factory=list)


class MonthNoteIn(BaseModel):
    month: str
    content: str = ""


class WeekNoteIn(BaseModel):
    week_start: str
    content: str = ""


@router.get("")
def list_days(frm: str = Query(..., alias="from"), to: str = Query(...)):
    """取出 [from, to] 区间内每一天的文本行。"""
    if not DATE_RE.match(frm) or not DATE_RE.match(to):
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    if frm > to:
        raise HTTPException(status_code=422, detail="起始日期不能晚于结束日期")
    return {"days": calday.list_days(frm, to)}


@router.get("/month_note")
def get_month_note(month: str = Query(...)):
    """取某个月的月度计划。"""
    if not MONTH_RE.match(month):
        raise HTTPException(status_code=422, detail="月份格式应为 YYYY-MM")
    return calday.get_month_note(month)


@router.put("/month_note")
def put_month_note(payload: MonthNoteIn):
    """保存某个月的月度计划（整段覆盖）。"""
    if not MONTH_RE.match(payload.month):
        raise HTTPException(status_code=422, detail="月份格式应为 YYYY-MM")
    return calday.save_month_note(payload.month, payload.content)


@router.get("/week_notes")
def list_week_notes(frm: str = Query(..., alias="from"), to: str = Query(...)):
    """取 [from, to] 内各周一的周计划。"""
    if not DATE_RE.match(frm) or not DATE_RE.match(to):
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    if frm > to:
        raise HTTPException(status_code=422, detail="起始日期不能晚于结束日期")
    return {"notes": calday.list_week_notes(frm, to)}


@router.put("/week_note")
def put_week_note(payload: WeekNoteIn):
    """保存某一周的周计划（整段覆盖），键为该周周一。"""
    if not DATE_RE.match(payload.week_start):
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    return calday.save_week_note(payload.week_start, payload.content)


@router.put("/{date}")
def save_day(date: str, payload: CalDayIn):
    """整段覆盖某一天的文本行；自动任务行（daily_plan）保留来源标记。"""
    if not DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    result = calday.save_day(date, [l.model_dump() for l in payload.lines])
    return result
