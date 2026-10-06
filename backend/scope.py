"""用户数据空间：目录与业务库的创建、初始化、销毁。

每个用户在 workspaces/users/u{uid}/ 下拥有一整套独立的 db 与文件，
模块库路径由 config 依据 ctx 中的当前用户自动解析（见 config.__getattr__）。

- ensure_user_storage(uid)：建目录 + 建表 + 种子数据（首次），之后靠启动时的
  db.init_db() 全量巡检来承接 schema 升级，避免每次请求都跑一遍迁移；
- delete_user_storage(uid)：删除用户时连数据目录一起清掉。
"""

import logging
import shutil
from contextlib import contextmanager
from pathlib import Path

from . import config, ctx, db

_MARKER = ".inited"


def ensure_user_storage(uid: int) -> Path:
    """确保该用户的数据目录与库已就绪，返回目录路径（幂等）。"""
    d = config.user_dir(uid)
    d.mkdir(parents=True, exist_ok=True)
    marker = d / _MARKER
    if not marker.exists():
        db.init_user(uid)
        marker.write_text("ok", encoding="utf-8")
    return d


def delete_user_storage(uid: int) -> bool:
    """删除用户数据目录（含全部 db 与文件）。目录不存在时返回 False。

    刻意**不用** ignore_errors=True：那样会把「文件被占用删不掉」静默吞掉，
    留下半残目录（账号已删、数据半在），事后极难排查。删不掉就如实返回 False
    并记日志，由调用方决定是否继续删账号。

    """
    d = config.user_dir(uid)
    if not d.exists():
        return False
    try:
        shutil.rmtree(d)
    except OSError as e:
        logging.getLogger("mawork").warning("删除用户 u%s 数据目录失败：%s", uid, e)
        return False
    return not d.exists()


def each_user_dir() -> list[tuple[int, Path]]:
    """列出已存在的用户数据目录：[(uid, dir)]，按 uid 升序。"""
    if not config.USERS_DIR.exists():
        return []
    out: list[tuple[int, Path]] = []
    for d in config.USERS_DIR.iterdir():
        if not d.is_dir() or not d.name.startswith("u"):
            continue
        try:
            uid = int(d.name[1:])
        except ValueError:
            continue
        out.append((uid, d))
    return sorted(out, key=lambda x: x[0])


@contextmanager
def in_user(uid: int | None):
    """把一段代码放进指定用户的数据空间：`with in_user(3): ...`。"""
    token = ctx.set_uid(uid)
    try:
        yield
    finally:
        ctx.reset_uid(token)
