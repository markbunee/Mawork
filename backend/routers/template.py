"""模板库路由（横切能力 E3）：统一模板的增删改查，受保护。"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services import template as svc

router = APIRouter(prefix="/api/template", tags=["template"])


class TemplateIn(BaseModel):
    scope: str = "daily"
    name: str = ""
    content: str = ""


@router.get("/list")
def list_templates(scope: str | None = Query(None)):
    """模板列表；scope 为空时返回全部。"""
    return {"templates": svc.list_templates(scope)}


@router.post("")
def create(payload: TemplateIn):
    try:
        return svc.create_template(payload.scope, payload.name, payload.content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/{tid}")
def update(tid: int, payload: TemplateIn):
    try:
        t = svc.update_template(tid, payload.name or None, payload.content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if t is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    return t


@router.delete("/{tid}")
def delete(tid: int):
    try:
        if not svc.delete_template(tid):
            raise HTTPException(status_code=404, detail="模板不存在")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}
