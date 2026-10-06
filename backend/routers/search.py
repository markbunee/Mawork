"""全局搜索路由（横切能力 E1）：一键跨模块检索。"""

from fastapi import APIRouter, Query

from ..services import search as svc

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    """跨日报 / 文章 / 记账 / 日程 / 计时 / 资料 检索，返回按模块分组的命中项。"""
    return svc.global_search(q, limit)
