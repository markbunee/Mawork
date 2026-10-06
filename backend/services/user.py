"""账号业务逻辑：密码哈希、成员申请与审批、账号管理。

安全口径：
- 密码用标准库 hashlib.pbkdf2_hmac('sha256', …) 派生，20 万轮，每账号随机盐；
  不引入 bcrypt/passlib 等第三方依赖，离线环境也能装。
- 校验用 hmac.compare_digest 做常量时间比较，避免时序侧信道。
- **对外返回的账号信息一律剔除 pwd_hash / salt**（见 _public），
  管理员也拿不到密码——只能重置。

成员申请语义（按需求约定）：
- 任何人可提交「用户名 + 手机号 + 密码」申请；
- 管理员审批通过后才会真正建号；
- 已存在的账号用「同样的用户名 + 同样的手机号」再次申请 = **重置密码申请**，
  管理员通过后密码更新为新提交的那个；
- 用户名被他人占用、或手机号与预留号码不一致，一律拒绝（防抢注 / 防冒改）。
"""

import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime

from .. import config, db, scope
from ..models import user as model

ITERS = 200_000
_SALT_BYTES = 16
# 临时密码字符集：去掉 0/O/1/l/I 等易混淆字符
_TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyzACDEFGHJKLMNPQRSTUVWXYZ23456789"


# ---------------------------------------------------------------------------
# 连接与密码学
# ---------------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    """账号库连接。USERS_DB 是全局库，不随用户上下文变化。"""
    return db.get_conn(config.USERS_DB)


def _hash_password(pwd: str, salt_hex: str, iters: int = ITERS) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", pwd.encode("utf-8"), bytes.fromhex(salt_hex), iters
    ).hex()


def new_secret(pwd: str) -> tuple[str, str, int]:
    """生成 (pwd_hash, salt, iters)。"""
    salt = secrets.token_hex(_SALT_BYTES)
    return _hash_password(pwd, salt), salt, ITERS


def verify_password(pwd: str, salt_hex: str, expect_hash: str, iters: int = ITERS) -> bool:
    """常量时间校验密码。"""
    try:
        got = _hash_password(pwd, salt_hex, iters)
    except ValueError:  # 盐格式损坏
        return False
    return hmac.compare_digest(got, expect_hash or "")


def gen_temp_password(n: int = 12) -> str:
    """生成一次性临时密码（管理员重置时用，明文只在返回的那一瞬间可见）。"""
    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(n))


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def _validate_username(username: str) -> str:
    u = (username or "").strip()
    if len(u) < model.USERNAME_MIN_LEN or len(u) > model.USERNAME_MAX_LEN:
        raise ValueError(
            f"用户名长度需为 {model.USERNAME_MIN_LEN}-{model.USERNAME_MAX_LEN} 位"
        )
    if not re.match(model.USERNAME_PATTERN, u):
        raise ValueError("用户名只能包含字母、数字、下划线、点、连字符")
    return u


def _validate_phone(phone: str) -> str:
    p = (phone or "").strip()
    if len(p) < model.PHONE_MIN_LEN or len(p) > model.PHONE_MAX_LEN:
        raise ValueError("手机号格式不正确")
    if not re.match(r"^[0-9+()-]+$", p):
        raise ValueError("手机号只能包含数字、+、-、括号")
    return p


def _validate_password(pwd: str) -> str:
    if len(pwd or "") < model.PWD_MIN_LEN:
        raise ValueError(f"密码至少 {model.PWD_MIN_LEN} 位")
    return pwd


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def _public(row: sqlite3.Row | None) -> dict | None:
    """账号出库：剔除密码哈希与盐，任何接口都拿不到。"""
    if row is None:
        return None
    d = dict(row)
    d.pop("pwd_hash", None)
    d.pop("salt", None)
    return d


def get_user(uid: int) -> dict | None:
    conn = _conn()
    try:
        return _public(conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())
    finally:
        conn.close()


def get_raw(uid: int) -> dict | None:
    """含哈希的内部读取：仅用于登录校验，绝不下发到前端。"""
    conn = _conn()
    try:
        r = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def get_by_username(username: str) -> dict | None:
    conn = _conn()
    try:
        r = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return _public(r)
    finally:
        conn.close()


def list_users() -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY "
            "CASE role WHEN 'admin' THEN 0 ELSE 1 END, id"
        ).fetchall()
        return [_public(r) for r in rows]  # type: ignore[misc]
    finally:
        conn.close()


def list_uids() -> list[int]:
    conn = _conn()
    try:
        return [r["id"] for r in conn.execute("SELECT id FROM users ORDER BY id")]
    finally:
        conn.close()


def count_users() -> int:
    conn = _conn()
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    finally:
        conn.close()


def touch_login(uid: int) -> None:
    conn = _conn()
    try:
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), uid),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 登录校验
# ---------------------------------------------------------------------------

def authenticate(username: str, password: str) -> dict | None:
    """校验账号密码，成功返回脱敏后的账号信息；失败返回 None。"""
    username = (username or "").strip()
    conn = _conn()
    try:
        r = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if r is None:
            # 即使用户不存在也做一次同等开销的派生，避免「用户是否存在」被时序探测
            _hash_password(password or "", "00" * _SALT_BYTES)
            return None
        ok = verify_password(password or "", r["salt"], r["pwd_hash"], r["pwd_iter"] or ITERS)
        if not ok or r["status"] != "active":
            return None
        return _public(r)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 成员申请 / 重置密码申请
# ---------------------------------------------------------------------------

def apply_member(username: str, phone: str, password: str, note: str = "") -> dict:
    """提交申请。

    已存在且手机号一致 → 重置密码申请（kind='reset'）；否则新建成员申请。
    同一用户名已有待审申请时覆盖更新，避免重复堆积。
    """
    u = _validate_username(username)
    p = _validate_phone(phone)
    _validate_password(password)
    note = (note or "").strip()[:200]

    conn = _conn()
    try:
        exist = conn.execute("SELECT * FROM users WHERE username = ?", (u,)).fetchone()
        kind = "new"
        target_uid = None
        if exist:
            if (exist["phone"] or "") != p:
                raise ValueError("该用户名已存在，且手机号与预留号码不一致")
            kind = "reset"
            target_uid = exist["id"]
        else:
            clash = conn.execute(
                "SELECT id FROM users WHERE phone = ? AND phone <> ''", (p,)
            ).fetchone()
            if clash:
                raise ValueError("该手机号已被其他账号使用")
            # 待审申请之间也要互斥，否则两个人可同时用同一手机号排队
            clash_app = conn.execute(
                "SELECT id FROM user_applications WHERE phone = ? AND phone <> '' "
                "AND status = 'pending' AND username <> ?",
                (p, u),
            ).fetchone()
            if clash_app:
                raise ValueError("该手机号已被其他申请占用")

        pwd_hash, salt, iters = new_secret(password)
        pending = conn.execute(
            "SELECT * FROM user_applications WHERE username = ? AND status = 'pending'",
            (u,),
        ).fetchone()
        if pending:
            conn.execute(
                "UPDATE user_applications SET kind = ?, phone = ?, pwd_hash = ?, "
                "salt = ?, pwd_iter = ?, user_id = ?, note = ?, "
                "created_at = datetime('now', 'localtime') WHERE id = ?",
                (kind, p, pwd_hash, salt, iters, target_uid, note, pending["id"]),
            )
            app_id = pending["id"]
        else:
            cur = conn.execute(
                "INSERT INTO user_applications "
                "(kind, username, phone, pwd_hash, salt, pwd_iter, user_id, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (kind, u, p, pwd_hash, salt, iters, target_uid, note),
            )
            app_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return {"id": app_id, "kind": kind, "username": u, "status": "pending"}


def list_applications(status: str = "pending") -> list[dict]:
    """申请列表（默认只看待审）。不含密码哈希。"""
    conn = _conn()
    try:
        if status and status != "all":
            rows = conn.execute(
                "SELECT id, kind, username, phone, user_id, status, note, "
                "created_at, handled_at, handled_by FROM user_applications "
                "WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, kind, username, phone, user_id, status, note, "
                "created_at, handled_at, handled_by FROM user_applications "
                "ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def approve_application(app_id: int, admin_id: int) -> dict:
    """通过申请：kind='new' 建号；kind='reset' 更新目标账号密码。"""
    conn = _conn()
    try:
        app = conn.execute("SELECT * FROM user_applications WHERE id = ?", (app_id,)).fetchone()
        if app is None:
            raise ValueError("申请不存在")
        if app["status"] != "pending":
            raise ValueError("该申请已处理过")

        if app["kind"] == "new":
            if conn.execute("SELECT 1 FROM users WHERE username = ?", (app["username"],)).fetchone():
                raise ValueError("用户名已被占用，审批失败")
            cur = conn.execute(
                "INSERT INTO users (username, phone, pwd_hash, salt, pwd_iter, "
                "role, status, display_name) VALUES (?, ?, ?, ?, ?, 'member', 'active', ?)",
                (app["username"], app["phone"], app["pwd_hash"], app["salt"],
                 app["pwd_iter"] or ITERS, app["username"]),
            )
            uid = cur.lastrowid
        else:
            uid = app["user_id"]
            target = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
            if target is None:
                raise ValueError("目标账号不存在，可能已被删除")
            conn.execute(
                "UPDATE users SET pwd_hash = ?, salt = ?, pwd_iter = ?, phone = ?, "
                "updated_at = datetime('now', 'localtime') WHERE id = ?",
                (app["pwd_hash"], app["salt"], app["pwd_iter"] or ITERS, app["phone"], uid),
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE user_applications SET status = 'approved', handled_at = ?, "
            "handled_by = ? WHERE id = ?",
            (now, admin_id, app_id),
        )
        # 同一用户名的其它待审申请作废，避免重复审批造成密码被二次覆盖
        conn.execute(
            "UPDATE user_applications SET status = 'rejected', "
            "note = '已由其它审批处理', handled_at = ?, handled_by = ? "
            "WHERE username = ? AND status = 'pending'",
            (now, admin_id, app["username"]),
        )
        conn.commit()
    finally:
        conn.close()

    scope.ensure_user_storage(uid)
    return {"ok": True, "kind": app["kind"], "user_id": uid, "username": app["username"]}


def reject_application(app_id: int, admin_id: int, note: str = "") -> dict:
    """驳回申请。"""
    conn = _conn()
    try:
        app = conn.execute("SELECT * FROM user_applications WHERE id = ?", (app_id,)).fetchone()
        if app is None:
            raise ValueError("申请不存在")
        if app["status"] != "pending":
            raise ValueError("该申请已处理过")
        conn.execute(
            "UPDATE user_applications SET status = 'rejected', note = ?, "
            "handled_at = ?, handled_by = ? WHERE id = ?",
            ((note or "").strip()[:200] or "管理员驳回",
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), admin_id, app_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "id": app_id}


# ---------------------------------------------------------------------------
# 账号管理（管理员）
# ---------------------------------------------------------------------------

def create_user(username: str, phone: str, password: str,
                role: str = "member", display_name: str = "") -> dict:
    """管理员直接建号（无需审批）。"""
    u = _validate_username(username)
    p = _validate_phone(phone)
    _validate_password(password)
    role = role if role in model.ROLES else "member"
    pwd_hash, salt, iters = new_secret(password)

    conn = _conn()
    try:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (u,)).fetchone():
            raise ValueError("用户名已存在")
        cur = conn.execute(
            "INSERT INTO users (username, phone, pwd_hash, salt, pwd_iter, role, "
            "status, display_name) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
            (u, p, pwd_hash, salt, iters, role, (display_name or u)[:64]),
        )
        conn.commit()
        uid = cur.lastrowid
    finally:
        conn.close()
    scope.ensure_user_storage(uid)
    return get_user(uid)  # type: ignore[return-value]


def reset_password(uid: int) -> tuple[dict, str]:
    """管理员重置密码：返回 (账号信息, 临时密码明文)。

    明文只在本次响应里出现一次，不落库、不写日志。
    """
    temp = gen_temp_password()
    pwd_hash, salt, iters = new_secret(temp)
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE users SET pwd_hash = ?, salt = ?, pwd_iter = ?, "
            "updated_at = datetime('now', 'localtime') WHERE id = ?",
            (pwd_hash, salt, iters, uid),
        )
        if cur.rowcount == 0:
            raise ValueError("账号不存在")
        conn.commit()
    finally:
        conn.close()
    return get_user(uid), temp  # type: ignore[return-value]


def set_status(uid: int, status: str) -> dict | None:
    """停用 / 恢复账号。停用后不能登录，数据保留。"""
    if status not in model.USER_STATUSES:
        raise ValueError("状态值非法")
    conn = _conn()
    try:
        u = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if u is None:
            return None
        if u["role"] == "admin" and status == "disabled":
            admins = conn.execute(
                "SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND status = 'active'"
            ).fetchone()["n"]
            if admins <= 1:
                raise ValueError("至少需保留一个启用状态的管理员")
        conn.execute(
            "UPDATE users SET status = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (status, uid),
        )
        conn.commit()
    finally:
        conn.close()
    return get_user(uid)


def delete_user(uid: int) -> dict:
    """删除账号 + 清空其全部业务数据目录。

    顺序很关键：**先删数据目录、成功后再删账号**。
    反过来（先删账号）一旦目录删除失败，账号已消失而数据目录成为孤儿——
    既无法再登录访问，也不会被 init_db() 巡检到，沦为无人认领的残留。
    """
    conn = _conn()
    try:
        u = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if u is None:
            raise ValueError("账号不存在")
        if u["role"] == "admin":
            admins = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'").fetchone()["n"]
            if admins <= 1:
                raise ValueError("不能删除最后一个管理员")
    finally:
        conn.close()

    # 先清数据；删不掉就保留账号，交给管理员重试
    if not scope.delete_user_storage(uid):
        raise ValueError("用户数据目录删除失败，已保留账号，请稍后重试")

    conn = _conn()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.execute("DELETE FROM user_applications WHERE user_id = ? OR username = ?",
                     (uid, u["username"]))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "user_id": uid, "data_removed": True}


def set_role(uid: int, role: str) -> dict | None:
    """提升为管理员 / 降为普通成员。"""
    if role not in model.ROLES:
        raise ValueError("角色值非法")
    conn = _conn()
    try:
        u = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if u is None:
            return None
        if u["role"] == "admin" and role != "admin":
            admins = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'").fetchone()["n"]
            if admins <= 1:
                raise ValueError("至少需保留一个管理员")
        conn.execute(
            "UPDATE users SET role = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (role, uid),
        )
        conn.commit()
    finally:
        conn.close()
    return get_user(uid)


# ---------------------------------------------------------------------------
# 首次启动引导
# ---------------------------------------------------------------------------

def ensure_admin_seeded() -> dict | None:
    """全新部署（无账号）时，用环境变量里的管理员账号初始化第一个用户。

    已有账号则直接返回 None。迁移脚本负责把既有数据挂到某个已有账号下，
    本函数不参与数据搬迁。
    """
    conn = _conn()
    try:
        n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if n:
            return None
        username = (config.ADMIN_USERNAME or "admin").strip()
        password = config.ADMIN_PASSWORD or "mawork123"
        phone = (config.ADMIN_PHONE or "").strip()
        pwd_hash, salt, iters = new_secret(password)
        cur = conn.execute(
            "INSERT INTO users (username, phone, pwd_hash, salt, pwd_iter, role, "
            "status, display_name) VALUES (?, ?, ?, ?, ?, 'admin', 'active', ?)",
            (username, phone, pwd_hash, salt, iters, username),
        )
        conn.execute(
            "INSERT OR REPLACE INTO user_meta (key, value, updated_at) "
            "VALUES ('seeded_admin', ?, datetime('now', 'localtime'))",
            (str(cur.lastrowid),),
        )
        conn.commit()
        uid = cur.lastrowid
    finally:
        conn.close()
    scope.ensure_user_storage(uid)
    return get_user(uid)
