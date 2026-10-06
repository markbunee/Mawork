"""MaWork 后端配置：路径与常量。"""

import os
from pathlib import Path

from . import ctx

# Mawork/ 目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据根目录：默认 Mawork/workspaces/，可用 MAWORK_DATA_DIR 覆盖
# （Docker 挂载卷、或把数据放到别处时很有用）。
# 注意：这是**全局根**，业务数据一律走 data_dir()（按用户隔离），
# 直接使用 WORKSPACES_DIR 只适合全局级文件（如 users.db）。
WORKSPACES_DIR = Path(os.getenv("MAWORK_DATA_DIR", "") or (BASE_DIR / "workspaces"))

# 下面两个派生路径同样走 __getattr__ 动态解析（见文件末尾），
# 这样「测试脚本覆盖 config.WORKSPACES_DIR」的套路依然有效：
#   用户数据根目录：WORKSPACES_DIR/users/u{uid}/
#   账号库（全局唯一，不属于任何用户）：WORKSPACES_DIR/users.db

# 多用户开关：1（默认）按用户隔离数据；0 退回旧的单用户根目录模式
MULTI_USER = os.getenv("MAWORK_MULTI_USER", "1").lower() in ("1", "true", "yes")

# 日报作者
AUTHOR = "马炫轩"


# ===========================================================================
# 按用户解析的数据路径
# ===========================================================================
# 各业务库文件均为「运行时」读取 config.X_DB，这里用 PEP 562 的模块级
# __getattr__ 让它们随当前请求的用户自动指向该用户的目录，
# 好处：services / routers 里已有的 config.ACCOUNTING_DB 等写法无需改动。
# 测试脚本若执行 config.ACCOUNTING_DB = tmp/xxx.db，赋值会写入模块字典，
# 优先于 __getattr__，因此「临时库」套路依然可用。
_DB_FILES = {
    "ACCOUNTING_DB": "accounting.db",   # 记账
    "PLANPOOL_DB": "planpool.db",       # 日程任务 + 日历文本格 + 习惯
    "DAILY_DB": "daily.db",             # 日报（唯一真源）
    "TIMER_DB": "timer.db",             # 计时
    "INSIGHT_DB": "insight.db",         # 洞察：目标 KPI
    "TEMPLATES_DB": "templates.db",     # 模板库
    "ARTICLES_DB": "articles.db",       # 文章：Markdown 文章（每篇一条记录）
    "DB_PATH": "accounting.db",         # 兼容旧引用：默认库 = 记账库
}


def data_dir() -> Path:
    """当前用户的数据目录；未绑定用户或关闭多用户时返回全局根。"""
    uid = ctx.current_uid()
    if not MULTI_USER or uid is None:
        return WORKSPACES_DIR
    return WORKSPACES_DIR / "users" / f"u{uid}"


def db_path(key: str) -> Path:
    """按逻辑名取当前用户的库路径（key 见 _DB_FILES）。"""
    try:
        fname = _DB_FILES[key]
    except KeyError:
        raise KeyError(f"未知的数据库名：{key}") from None
    return data_dir() / fname


def user_dir(uid: int) -> Path:
    """指定用户的数据目录。"""
    return (WORKSPACES_DIR / "users") / f"u{uid}"


def users_db_path() -> Path:
    """全局账号库路径。"""
    return WORKSPACES_DIR / "users.db"


def __getattr__(name: str):
    """动态解析路径常量（业务库 + 用户目录 + 账号库）。

    做成运行时解析，好处有二：
    1) config.X_DB 随请求用户自动切换（多用户隔离的核心）；
    2) 测试脚本覆盖 config.WORKSPACES_DIR 后，所有派生路径一起跟着变。
    """
    fname = _DB_FILES.get(name)
    if fname is not None:
        return data_dir() / fname
    if name == "USERS_DIR":
        return WORKSPACES_DIR / "users"
    if name == "USERS_DB":
        return WORKSPACES_DIR / "users.db"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ===========================================================================
# 认证配置（全部可通过环境变量覆盖，生产环境务必覆盖 SECRET 与 ADMIN_PASSWORD）
# ===========================================================================

# JWT 签名密钥。默认值仅供本地开发，务必用环境变量 MAWORK_SECRET 覆盖。
AUTH_SECRET = os.getenv("MAWORK_SECRET", "mawork-dev-secret-please-change-me")
AUTH_ALGORITHM = "HS256"

# 令牌有效期（分钟），默认 12 小时
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("MAWORK_TOKEN_EXPIRE_MINUTES", "720"))

# 首个管理员账号（全新部署时自动播种；已有账号则忽略）
ADMIN_USERNAME = os.getenv("MAWORK_ADMIN_USER", "admin")
# 管理员密码。默认值仅供本地开发，务必用 MAWORK_ADMIN_PASSWORD 覆盖。
ADMIN_PASSWORD = os.getenv("MAWORK_ADMIN_PASSWORD", "mawork123")
# 管理员手机号（可选，用于日后自助改密校验）
ADMIN_PHONE = os.getenv("MAWORK_ADMIN_PHONE", "")

# CORS 允许的前端来源（逗号分隔）。
# 开发态：前端经 Vite 代理访问 /api，属同源，其实不会触发 CORS；
# 若前端与后端分域部署（如静态站点），需在此加入前端源。
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "MAWORK_CORS_ORIGINS",
        "http://localhost:5174,http://127.0.0.1:5174",
    ).split(",")
    if o.strip()
]

# 本项目鉴权走 Authorization 头 + Cookie 不依赖，因此 allow_credentials=True；
# 但 Starlette 在 allow_origins 含 "*" 时会同时发出 `Allow-Origin: *` 与
# `Allow-Credentials: true` —— 这个组合浏览器一律拒绝，且语义上就是错的。
# 与其等到线上排查「为什么跨域全挂」，不如在配置期直接拦下。
if "*" in CORS_ORIGINS:
    raise RuntimeError(
        "MAWORK_CORS_ORIGINS 不允许为 *：本项目用 Authorization 头鉴权，"
        "不需要通配来源。请填写真实前端域名（多个用逗号分隔）。"
    )

# 是否暴露 API 文档（/docs、/redoc、/openapi.json）。默认关闭以防接口清单泄露。
ENABLE_DOCS = os.getenv("MAWORK_ENABLE_DOCS", "0").lower() in ("1", "true", "yes")

# ===========================================================================
# 自适应护栏（运行时测量系统资源，不绑定机器规格）
# 详见 backend/guard.py：内存/负载实时读取 /proc，机器越大越宽松、越小越早熔断。
# 两条铁律：① 服务器不因过载崩；② 单个超大请求拖不垮。
# ===========================================================================
# 单请求体硬上限（字节）。即使可用内存很大也不会超过此值。
GUARD_MAX_BODY_BYTES = int(os.getenv("MAWORK_GUARD_MAX_BODY", str(10 * 1024 * 1024)))
# 可用内存绝对地板（MB）：低于此值即开始甩负载，任何规格都危险。
GUARD_MEM_AVAILABLE_FLOOR_MB = float(os.getenv("MAWORK_GUARD_MEM_FLOOR_MB", "100"))
# 可用内存低于总量比例也甩负载（小机器早触发、大机器晚触发）。
GUARD_MEM_AVAILABLE_PCT = float(os.getenv("MAWORK_GUARD_MEM_PCT", "0.10"))
# 1 分钟平均负载 > cpu 数 × 此值 即视为压力。
GUARD_LOADAVG_PER_CPU = float(os.getenv("MAWORK_GUARD_LOAD_PER_CPU", "1.5"))
# 单请求 / 单文件读取上限 = 当前可用内存 × 此比例（与硬上限取较小者）。
GUARD_BODY_MEM_FRACTION = float(os.getenv("MAWORK_GUARD_BODY_MEM_FRAC", "0.25"))
# 并发上限 ≈ cpu 数 × 此值（至少 8）。
GUARD_CONCURRENCY_PER_CPU = int(os.getenv("MAWORK_GUARD_CONC_PER_CPU", "4"))


# ===========================================================================
# 公网安全开关
# ===========================================================================
# 是否强制要求强密钥/强密码才允许启动（默认关闭，避免误伤本地开发）。
REQUIRE_STRONG_SECRET = os.getenv("MAWORK_REQUIRE_STRONG_SECRET", "0").lower() in ("1", "true", "yes")
# 是否在响应头加 HSTS（默认关闭；建议统一在反代 nginx 层加）。
ENABLE_HSTS = os.getenv("MAWORK_HSTS", "0").lower() in ("1", "true", "yes")
# 是否启用严格 CSP（默认关闭；确认前端无内联脚本后再开，避免白屏）。
ENABLE_CSP = os.getenv("MAWORK_CSP", "0").lower() in ("1", "true", "yes")
