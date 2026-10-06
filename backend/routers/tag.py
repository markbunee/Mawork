"""横切能力 E6：标签中台路由（受保护）。"""

from fastapi import APIRouter, Query

from ..services import tag as svc

router = APIRouter(prefix="/api/tag", tags=["tag"])


@router.get("/list")
def list_tags():
    """全站标签云。"""
    return svc.list_tags()


@router.get("/items")
def tag_items(tag: str = Query(..., min_length=1)):
    """某标签下的全部条目（跨日报 / 文章 / 日程）。"""
    return svc.tag_items(tag)
