"""请求级用户上下文（多用户数据隔离的基础）。

为什么单独一个文件：config 需要读当前用户 id 才能解析出该用户的库路径，
而 scope / db 又要 import config。若把 ContextVar 放在 scope 或 config 里
会形成循环导入，因此抽出这个「零依赖」模块只放上下文变量。

用法：
    token = ctx.set_uid(3)        # 进入某用户的数据空间
    try:
        ... config.ACCOUNTING_DB  # -> workspaces/users/u3/accounting.db
    finally:
        ctx.reset_uid(token)
"""

from contextvars import ContextVar

# 当前请求所属用户 id；None 表示「未绑定用户」（启动期 / 单用户遗留模式）
_current_uid: ContextVar[int | None] = ContextVar("mawork_uid", default=None)


def set_uid(uid: int | None) -> object:
    """设置当前用户 id，返回用于还原的 token。"""
    return _current_uid.set(uid)


def reset_uid(token: object) -> None:
    """还原到上一个用户上下文。"""
    _current_uid.reset(token)  # type: ignore[arg-type]


def current_uid() -> int | None:
    """当前用户 id；未绑定时返回 None。"""
    return _current_uid.get()
