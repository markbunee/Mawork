"""认证路由：登录 / 当前用户 / 成员申请。

- POST /api/auth/login   ：账号密码换 JWT 令牌（按 IP 限流，防暴力破解）；
- GET  /api/auth/me      ：校验令牌并回显当前用户，用于前端启动时探活；
- POST /api/auth/apply   ：成员申请（用户名 + 手机号 + 密码），
                           同用户名 + 同手机号再次提交 = 重置密码申请；
                           均需管理员在「用户管理」里通过后生效。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..auth import create_access_token, limiter, require_auth
from ..services import user as user_svc

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str
    password: str


class ApplyPayload(BaseModel):
    username: str
    phone: str
    password: str
    note: str = Field(default="")


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: LoginPayload):
    """账号密码登录，成功返回 JWT 令牌。"""
    rec = user_svc.authenticate(payload.username, payload.password)
    if rec is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    user_svc.touch_login(rec["id"])
    token = create_access_token(rec["username"], rec["id"], rec["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "uid": rec["id"],
        "username": rec["username"],
        "role": rec["role"],
    }


@router.get("/me")
def me(user: dict = Depends(require_auth)):
    """校验当前令牌并返回用户信息（不含任何密码字段）。"""
    return user


@router.post("/apply")
@limiter.limit("5/minute")
def apply(request: Request, payload: ApplyPayload):
    """提交成员申请 / 重置密码申请。无需登录。"""
    try:
        result = user_svc.apply_member(
            payload.username, payload.phone, payload.password, payload.note
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    tip = (
        "已提交重置密码申请，请等待管理员通过后使用新密码登录"
        if result["kind"] == "reset"
        else "已提交成员申请，请等待管理员通过后再登录"
    )
    return {**result, "message": tip}
