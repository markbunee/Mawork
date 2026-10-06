"""洞察路由：跨模块统计 Dashboard、目标 KPI、自动复盘。

路由顺序注意：静态路径必须声明在路径参数之前。
- GET /dashboard         必须在任何 /{...} 之前（本文件没有路径参数路由，但保持习惯）
- GET /goals/logs/{gid}  与 DELETE /goals/{gid} 按方法区分，无冲突
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services import insight

router = APIRouter(prefix="/api/insight", tags=["insight"])


def _bad_request(e: Exception):
    raise HTTPException(status_code=422, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Dashboard：跨模块只读聚合
# ---------------------------------------------------------------------------
@router.get("/dashboard")
def get_dashboard(
    from_: str = Query(..., alias="from", description="起始日期 YYYY-MM-DD"),
    to: str = Query(..., description="结束日期 YYYY-MM-DD"),
):
    try:
        return insight.dashboard(from_, to)
    except ValueError as e:
        _bad_request(e)


# ---------------------------------------------------------------------------
# 目标 KPI
# ---------------------------------------------------------------------------
@router.get("/goals")
def list_goals(archived: bool = Query(False)):
    return {"goals": insight.list_goals(include_archived=archived)}


class GoalPayload(BaseModel):
    title: str = ""
    category: str = ""
    metric: str = ""
    start_value: float | None = None
    target: float | None = None
    current: float | None = None
    deadline: str | None = None
    note: str | None = None
    archived: bool | None = None


@router.post("/goals")
def create_goal(payload: GoalPayload):
    try:
        return insight.create_goal(payload.model_dump(exclude_none=True))
    except ValueError as e:
        _bad_request(e)


@router.put("/goals/{gid}")
def update_goal(gid: int, payload: GoalPayload):
    try:
        g = insight.update_goal(gid, payload.model_dump(exclude_none=True))
    except ValueError as e:
        _bad_request(e)
    if g is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    return g


@router.delete("/goals/{gid}")
def delete_goal(gid: int):
    if not insight.delete_goal(gid):
        raise HTTPException(status_code=404, detail="目标不存在")
    return {"ok": True}


class CheckinPayload(BaseModel):
    delta: float = 0
    note: str = ""
    log_date: str | None = None


@router.post("/goals/{gid}/checkin")
def checkin_goal(gid: int, payload: CheckinPayload):
    try:
        g = insight.checkin_goal(gid, payload.delta, payload.note, payload.log_date)
    except ValueError as e:
        _bad_request(e)
    if g is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    return g


@router.get("/goals/{gid}/logs")
def list_goal_logs(gid: int, limit: int = 200):
    return {"goal_id": gid, "logs": insight.list_goal_logs(gid, limit)}


# ---------------------------------------------------------------------------
# 关键结果 KR（横切能力 E7）
# ---------------------------------------------------------------------------
@router.get("/goals/{gid}/key_results")
def list_key_results(gid: int):
    """某目标的全部关键结果 + 加权汇总进度。"""
    return insight.goal_rollup(gid)


class KeyResultPayload(BaseModel):
    title: str = ""
    metric: str = ""
    start_value: float | None = None
    target: float | None = None
    current: float | None = None
    weight: float | None = None
    week: str | None = None
    deadline: str | None = None
    note: str | None = None


@router.post("/goals/{gid}/key_results")
def create_key_result(gid: int, payload: KeyResultPayload):
    try:
        return insight.create_key_result(gid, payload.model_dump(exclude_none=True))
    except ValueError as e:
        _bad_request(e)


@router.put("/key_results/{kid}")
def update_key_result(kid: int, payload: KeyResultPayload):
    try:
        kr = insight.update_key_result(kid, payload.model_dump(exclude_none=True))
    except ValueError as e:
        _bad_request(e)
    if kr is None:
        raise HTTPException(status_code=404, detail="关键结果不存在")
    return kr


@router.delete("/key_results/{kid}")
def delete_key_result(kid: int):
    if not insight.delete_key_result(kid):
        raise HTTPException(status_code=404, detail="关键结果不存在")
    return {"ok": True}


@router.get("/key_results/by_week")
def key_results_by_week(week: str = Query("", description="YYYY-Www，留空为当前周")):
    """周计划联动：某周挂载的关键结果。"""
    return {"week": week or insight.current_week_key(), "items": insight.list_key_results_by_week(week)}


# ---------------------------------------------------------------------------
# 自动复盘
# ---------------------------------------------------------------------------
@router.get("/review")
def get_review(
    scope: str = Query("week", description="week | month | quarter | year"),
    anchor: str = Query(..., description="锚点日期 YYYY-MM-DD"),
):
    try:
        return insight.review(scope, anchor)
    except ValueError as e:
        _bad_request(e)
