"""MaWork 认证：多账号 + JWT 令牌 + 登录限流。

配置见 config.py（均可用环境变量覆盖）：
    MAWORK_SECRET / MAWORK_ADMIN_USER / MAWORK_ADMIN_PASSWORD / MAWORK_ADMIN_PHONE
    MAWORK_TOKEN_EXPIRE_MINUTES / MAWORK_MULTI_USER

安全说明：
- 账号密码存 PBKDF2-SHA256 哈希（20 万轮 + 随机盐），校验走 hmac.compare_digest；
- 令牌为 HS256 签名的 JWT，载荷含 uid / role，通过 Authorization: Bearer 传递；
- 登录接口由 slowapi 按客户端 IP 限流（见 routers/auth.py）。

多用户隔离的关键：
- require_auth 是 **async** 依赖 —— 必须如此！同步依赖会被 FastAPI 丢进线程池执行，
  而线程池用的是 copy_context，里面设置的 ContextVar 不会带回请求上下文。
  写成 async 后，它设置的当前用户 id 会被后续代码（含线程池里的同步端点）继承，
  config.X_DB 因而自动指向该用户的目录。
"""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from slowapi import Limiter
from slowapi.util import get_remote_address

from . import config, ctx
from .services import user as user_svc

# 登录限流器（按客户端 IP）。在 main.py 中注册到 app.state.limiter。
limiter = Limiter(key_func=get_remote_address)

# auto_error=False：缺失令牌时由 require_auth 统一抛出 401（返回中文提示）
_bearer = HTTPBearer(auto_error=False)


def create_access_token(subject: str, uid: int, role: str = "member") -> str:
    """签发访问令牌（载荷含 uid / role）。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "uid": uid,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, config.AUTH_SECRET, algorithm=config.AUTH_ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str = "需要管理员权限") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """FastAPI 依赖：校验令牌 → 载入账号 → 绑定当前用户上下文。

    返回脱敏后的账号信息（不含密码哈希）。
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("未登录或缺少令牌")
    try:
        payload = jwt.decode(
            credentials.credentials,
            config.AUTH_SECRET,
            algorithms=[config.AUTH_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("登录已过期，请重新登录")
    except jwt.PyJWTError:
        raise _unauthorized("令牌无效")

    uid = payload.get("uid")
    username = str(payload.get("sub", ""))
    if uid is None:
        # 兼容旧令牌：只有 sub 没有 uid，按用户名回查
        rec = user_svc.get_by_username(username)
        if rec is None:
            raise _unauthorized("令牌无效")
        uid = rec["id"]
    rec = user_svc.get_raw(int(uid))
    if rec is None or rec["username"] != username:
        raise _unauthorized("账号不存在或已删除")
    if rec["status"] != "active":
        raise _unauthorized("账号已停用，请联系管理员")

    # ★ 绑定数据空间：此后 config.X_DB 全部指向该用户目录
    ctx.set_uid(rec["id"])
    return {"id": rec["id"], "username": rec["username"], "role": rec["role"]}


async def require_admin(user: dict = Depends(require_auth)) -> dict:
    """管理员专用依赖。"""
    if user.get("role") != "admin":
        raise _forbidden()
    return user
