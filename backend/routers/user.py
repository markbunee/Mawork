"""用户管理路由（管理员专用）。

成员申请 / 审批、账号增删改、重置密码。
所有接口都要求管理员角色；账号信息一律不含密码字段。

路由声明顺序：`/applications*` 必须写在 `/{uid}*` 之前（见 HANDOFF 2.3）。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_admin
from ..services import user as user_svc

router = APIRouter(prefix="/api/user", tags=["user"])


class CreateUserPayload(BaseModel):
    username: str
    phone: str = ""
    password: str
    role: str = "member"
    display_name: str = ""


class RejectPayload(BaseModel):
    note: str = ""


class StatusPayload(BaseModel):
    status: str


class RolePayload(BaseModel):
    role: str


def _bad(e: Exception, code: int = 400):
    raise HTTPException(status_code=code, detail=str(e))


# ---------------------------------------------------------------------------
# 申请审批
# ---------------------------------------------------------------------------
@router.get("/applications")
def list_applications(status: str = "pending", _: dict = Depends(require_admin)):
    """申请列表；status=pending（默认）/ approved / rejected / all。"""
    return {"items": user_svc.list_applications(status)}


@router.post("/applications/{aid}/approve")
def approve(aid: int, admin: dict = Depends(require_admin)):
    """通过申请：新建账号 或 更新目标账号密码。"""
    try:
        return user_svc.approve_application(aid, admin["id"])
    except ValueError as e:
        _bad(e)


@router.post("/applications/{aid}/reject")
def reject(aid: int, payload: RejectPayload, admin: dict = Depends(require_admin)):
    """驳回申请（可附理由）。"""
    try:
        return user_svc.reject_application(aid, admin["id"], payload.note)
    except ValueError as e:
        _bad(e)


# ---------------------------------------------------------------------------
# 账号管理
# ---------------------------------------------------------------------------
@router.get("/list")
def list_users(_: dict = Depends(require_admin)):
    """全部账号（不含密码字段）。"""
    return {"items": user_svc.list_users()}


@router.post("")
@router.post("/")
def create_user(payload: CreateUserPayload, _: dict = Depends(require_admin)):
    """管理员直接建号（免审批）。"""
    try:
        return user_svc.create_user(
            payload.username, payload.phone, payload.password,
            payload.role, payload.display_name,
        )
    except ValueError as e:
        _bad(e)


@router.post("/{uid}/reset-password")
def reset_password(uid: int, _: dict = Depends(require_admin)):
    """重置密码，返回一次性临时密码明文（仅此一次可见，不落库）。"""
    try:
        rec, temp = user_svc.reset_password(uid)
    except ValueError as e:
        _bad(e)
    return {"user": rec, "temp_password": temp, "message": "请把临时密码告知该成员，并提醒其尽快提交改密申请"}


@router.post("/{uid}/status")
def set_status(uid: int, payload: StatusPayload, _: dict = Depends(require_admin)):
    """停用 / 恢复账号。"""
    try:
        rec = user_svc.set_status(uid, payload.status)
    except ValueError as e:
        _bad(e)
    if rec is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    return rec


@router.post("/{uid}/role")
def set_role(uid: int, payload: RolePayload, _: dict = Depends(require_admin)):
    """设为管理员 / 降为普通成员。"""
    try:
        rec = user_svc.set_role(uid, payload.role)
    except ValueError as e:
        _bad(e)
    if rec is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    return rec


@router.delete("/{uid}")
def delete_user(uid: int, admin: dict = Depends(require_admin)):
    """删除账号及其全部业务数据。"""
    if uid == admin["id"]:
        raise HTTPException(status_code=400, detail="不能删除当前登录的管理员自己")
    try:
        return user_svc.delete_user(uid)
    except ValueError as e:
        _bad(e)
