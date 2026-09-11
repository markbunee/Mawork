"""日报路由：日报存储于 daily.db（唯一真源），不再读写字盘 Markdown。

- 正文以段落（sections）形式返回，供前端分段编辑；
- 日历任务行（calendar_lines）作为独立来源随日报返回，用于页面顶部展示；
- 保存时正文「三、明日工作计划」自动落到次日日历。
"""

import re

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from .. import config
from ..models.daily import DEFAULT_SECTIONS
from ..services import calday, daily

router = APIRouter(prefix="/api/daily", tags=["daily"])

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
YEAR_RE = re.compile(r"^\d{4}$")


def _check_year(year: str) -> int:
    if not YEAR_RE.match(year):
        raise HTTPException(status_code=422, detail="年份格式应为 YYYY")
    return int(year)


def _check_date(year: str, date: str) -> None:
    if not DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    if not date.startswith(year + "-"):
        raise HTTPException(status_code=422, detail="日期不属于该年份")


@router.get("/years")
def list_years():
    """列出已有日报的年份。"""
    return {"years": daily.list_years()}


@router.get("/export")
def export_year(year: str = Query(...)):
    """导出某年全部日报为 Markdown（含日历任务注入）。"""
    y = _check_year(year)
    content = daily.export_year(y)
    if not content:
        raise HTTPException(status_code=404, detail="该年暂无日报")
    filename = f"daily_{year}.md"
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{year}")
def list_daily(year: str):
    """按月份分组列出某年日报的日期树。"""
    y = _check_year(year)
    return {"year": year, "groups": daily.list_groups(y)}


@router.get("/{year}/{date}")
def get_daily(year: str, date: str):
    """返回某天日报：正文、段落与当日日历任务（日历任务仅作展示注入）。"""
    _check_year(year)
    _check_date(year, date)
    entry = daily.get_entry(date)
    cal_tasks = calday.get_tasks(date)
    if entry is None:
        # 不存在也返回默认三段模板，前端可直接开写
        return {
            "date": date,
            "year": year,
            "exists": False,
            "heading": "",
            "body": "",
            "sections": [dict(s) for s in DEFAULT_SECTIONS],
            "calTasks": cal_tasks,
        }
    return {
        "date": entry["date"],
        "year": year,
        "exists": True,
        "heading": entry["heading"],
        "body": entry["body"],
        "sections": entry["sections"],
        "calTasks": cal_tasks,
    }


class DailyPayload(BaseModel):
    body: str = ""


@router.put("/{year}/{date}")
def upsert_daily(year: str, date: str, payload: DailyPayload):
    """保存某天日报；正文为整篇文本，后端负责切段与触发次日日历同步。"""
    _check_year(year)
    _check_date(year, date)
    try:
        result = daily.upsert_entry(date, payload.body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        "date": result["date"],
        "ok": True,
        "plan_synced": result["plan_synced"],
        "heading": f"## 日报_{config.AUTHOR}：{date.replace('-', '.')}",
    }
