"""账号领域模型（users.db，全局库，不参与按用户隔离）。

两张表：
- users：正式账号。密码只存 PBKDF2 哈希 + 盐，**任何接口都不返回明文/哈希**；
- user_applications：成员申请。分两种：
    kind='new'   新成员申请（用户名 + 手机号 + 密码）
    kind='reset' 重置密码申请（同一用户名 + 同一手机号再次申请即为改密）
  申请需管理员审批通过后才会真正建号 / 改密，审批前不生效。
"""

# 账号状态
USER_STATUSES = ("active", "disabled")     # 正常 / 已停用（停用不能登录，数据保留）
# 申请状态
APP_STATUSES = ("pending", "approved", "rejected")
# 申请类型
APP_KINDS = ("new", "reset")
# 角色
ROLES = ("admin", "member")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT    NOT NULL UNIQUE,        -- 登录名（唯一）
    phone        TEXT    NOT NULL DEFAULT '',    -- 手机号（与用户名配对，用于改密校验）
    pwd_hash     TEXT    NOT NULL,               -- PBKDF2-SHA256 十六进制摘要
    salt         TEXT    NOT NULL,               -- 每账号随机盐（十六进制）
    role         TEXT    NOT NULL DEFAULT 'member',  -- admin / member
    status       TEXT    NOT NULL DEFAULT 'active',  -- active / disabled
    display_name TEXT    NOT NULL DEFAULT '',
    pwd_iter     INTEGER NOT NULL DEFAULT 200000,    -- 哈希迭代次数（便于日后提升强度）
    created_at   TEXT    DEFAULT (datetime('now', 'localtime')),
    updated_at   TEXT    DEFAULT (datetime('now', 'localtime')),
    last_login   TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_users_phone  ON users(phone);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

CREATE TABLE IF NOT EXISTS user_applications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT    NOT NULL,                 -- new / reset
    username   TEXT    NOT NULL,
    phone      TEXT    NOT NULL DEFAULT '',
    pwd_hash   TEXT    NOT NULL,                 -- 待生效的密码哈希
    salt       TEXT    NOT NULL,
    pwd_iter   INTEGER NOT NULL DEFAULT 200000,
    user_id    INTEGER,                          -- kind=reset 时指向目标账号
    status     TEXT    NOT NULL DEFAULT 'pending',
    note       TEXT    NOT NULL DEFAULT '',      -- 申请人备注 / 管理员驳回理由
    created_at TEXT    DEFAULT (datetime('now', 'localtime')),
    handled_at TEXT    NOT NULL DEFAULT '',
    handled_by INTEGER                           -- 审批的管理员 id
);
CREATE INDEX IF NOT EXISTS idx_apps_status ON user_applications(status, id);
CREATE INDEX IF NOT EXISTS idx_apps_user   ON user_applications(username);

CREATE TABLE IF NOT EXISTS user_meta (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
"""

# 密码与用户名规则（前后端共用同一套口径，前端做提示、后端做强校验）
PWD_MIN_LEN = 8
USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 32
USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"
PHONE_MIN_LEN = 6
PHONE_MAX_LEN = 20
