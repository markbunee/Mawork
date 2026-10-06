"""MaWork 后端入口。

启动（必须在 Mawork/ 目录下，使 backend 作为包被导入）：
    cd Mawork && uvicorn backend.main:app --port 8001 --reload
    cd Mawork && python -m backend.main
"""

import logging
import os
import sys
from pathlib import Path

# 把 Mawork/ 加入模块搜索路径，保证 backend 作为包可导入
MAWORK_DIR = Path(__file__).resolve().parent.parent
if str(MAWORK_DIR) not in sys.path:
    sys.path.insert(0, str(MAWORK_DIR))


# ---------------------------------------------------------------------------
# 日志：默认输出到标准输出（Docker 会捕获为 `docker logs`），并可选写入挂载卷里的
# 文件（MAWORK_LOG_DIR，默认 /app/logs/mawork.log）实现持久化，保证“日志一定看得到”。
# ---------------------------------------------------------------------------
def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # 默认落到项目内的 logs/；Docker 里通过 MAWORK_LOG_DIR=/app/logs 覆盖为挂载卷
    log_dir = Path(os.getenv("MAWORK_LOG_DIR", str(MAWORK_DIR / "logs")))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "mawork.log", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
        # 让 uvicorn 的访问日志也落盘（保留它自带的 stdout 输出）
        for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
            logging.getLogger(name).addHandler(fh)
    except OSError:
        root.warning("日志目录 %s 不可写，仅输出到标准输出", log_dir)


setup_logging()
logger = logging.getLogger("mawork")

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import config, db, guard
from .auth import limiter, require_auth
from .routers import (
    accounting,
    ai_analysis,
    articles,
    auth,
    backup,
    calday,
    daily,
    habit,
    insight,
    planpool,
    reminder,
    resources,
    search,
    tag,
    template,
    timer,
    user,
)

# 默认隐藏 API 文档，防接口清单泄露；需要时设 MAWORK_ENABLE_DOCS=1 打开
_docs_kwargs = (
    {}
    if config.ENABLE_DOCS
    else {"docs_url": None, "redoc_url": None, "openapi_url": None}
)

app = FastAPI(title="MaWork API", **_docs_kwargs)

# 登录限流器
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(guard.RequestBodyTooLarge)
async def _body_too_large_handler(request: Request, exc: guard.RequestBodyTooLarge):
    """把请求体超限转成 413。

    由 MaxBodySizeMiddleware 在读流式 body 时抛出。异常从路由层向外传播时
    会先经过 CORS 中间件，因此响应带 Access-Control-Allow-Origin，
    浏览器能直接读到「请求体过大」而不是笼统的 CORS 报错。
    """
    return JSONResponse(status_code=413, content={"detail": str(exc)})

# 收紧 CORS：只允许配置中的前端来源（不再全开）。
# ⚠️ 注册位置见下方 guard 中间件处的说明——CORS 必须最后 add（最外层）。
_CORS_MIDDLEWARE = dict(
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 自适应过载保护 / 请求体上限 / 安全响应头
# ⚠️ 注册顺序要紧：Starlette 的 add_middleware 实际是 insert(0, ...)，
# 即**后注册的更靠外**。所以下面三行 + 末尾 CORS 的实际执行顺序（外→内）是：
#     CORS → Guard → MaxBodySize → SecurityHeaders → 路由
# 详细说明见 CORS 注册处。
# ---------------------------------------------------------------------------
app.add_middleware(guard.SecurityHeadersMiddleware)
app.add_middleware(guard.MaxBodySizeMiddleware)
app.add_middleware(guard.GuardMiddleware)

# CORS 放在最后注册 = 最外层。Starlette 的 add_middleware 是 insert(0, ...)，
# 所以实际执行顺序（外→内）是：CORS → Guard → MaxBodySize → SecurityHeaders → 路由。
# CORS 必须在最外层：否则 Guard 的 503 熔断、MaxBody 的 413 会在到达 CORS 之前
# 就短路返回，响应里没有 Access-Control-Allow-Origin，浏览器只能报笼统的
# CORS 错误，前端就拿不到「服务器繁忙」「请求体过大」这类可读提示了。
app.add_middleware(CORSMiddleware, **_CORS_MIDDLEWARE)


@app.on_event("startup")
def startup():
    logger.info("启动 MaWork 后端 | 数据目录=%s | 文档=%s",
                config.WORKSPACES_DIR, "开启" if config.ENABLE_DOCS else "关闭")

    # 弱凭据自检：防止用默认/弱密钥、弱密码直接上线公网被伪造令牌。
    _secret_weak = (
        config.AUTH_SECRET == "mawork-dev-secret-please-change-me"
        or len(config.AUTH_SECRET) < 16
    )
    _pwd_weak = config.ADMIN_PASSWORD in ("mawork123", "CHANGE_ME_STRONG_PASSWORD")
    if _secret_weak or _pwd_weak:
        logger.warning(
            "⚠️ 安全告警：%s 仍为默认值或弱凭据，公网部署存在被破解/伪造令牌风险！"
            "请设置强随机密钥（openssl rand -hex 32）与强管理员密码。",
            "MAWORK_SECRET" if _secret_weak else "MAWORK_ADMIN_PASSWORD",
        )
    if config.REQUIRE_STRONG_SECRET and (_secret_weak or _pwd_weak):
        raise RuntimeError(
            "MAWORK_REQUIRE_STRONG_SECRET=1 但存在弱凭据，拒绝启动；"
            "请先设置合格的 MAWORK_SECRET / MAWORK_ADMIN_PASSWORD。"
        )

    db.init_db()
    logger.info("数据库初始化完成")
    if db.DB_INIT_ERRORS:
        # 不阻断启动（避免一个坏库拖垮全站），但必须让运维立刻看到
        logger.error(
            "⚠️ 启动巡检发现 %d 个用户数据初始化失败，详见日志与 /api/health 的 db_init_errors",
            len(db.DB_INIT_ERRORS),
        )


@app.get("/api/health")
def health():
    """健康检查：公开，供启动脚本探活；并回报护栏实时指标。

    安全取舍：这些是运行时指标，理论上能给攻击者提供 DoS 情报
    （知道内存余量即可精准打满）。但本项目只有自用/小团队场景，
    换取的是「不用登录也能 `docker inspect` / 外部探活直接看状态」，
    因此保留。若要收紧，把 guard 与 db 两块挪到 require_admin 的 /api/admin/health。
    """
    info = guard.read_meminfo() or {}
    return {
        "ok": not db.DB_INIT_ERRORS,
        "guard": {
            "in_flight": guard.METRICS.get("in_flight", 0),
            "concurrency_cap": guard.METRICS.get("cap", 0),
            "last_shed_reason": guard.METRICS.get("shed_reason"),
            "mem_available_mb": round(info.get("MemAvailable", 0) / 1024, 1) if info else None,
            "mem_total_mb": round(info.get("MemTotal", 0) / 1024, 1) if info else None,
            "loadavg_1": guard.read_loadavg_1(),
            "rss_mb": round(guard.process_rss_bytes() / 1024 / 1024, 1),
        },
        # 有用户数据初始化失败时列出，便于巡检立刻定位（不泄露任何业务内容）
        "db_init_errors": {f"u{u}": msg for u, msg in sorted(db.DB_INIT_ERRORS.items())},
    }


# 公开路由：登录/登出（认证本身不能要求认证）
app.include_router(auth.router)

# 业务路由：全部要求携带有效 Bearer 令牌
_protected = [
    daily.router,
    ai_analysis.router,
    accounting.router,
    planpool.router,
    calday.router,
    articles.router,
    reminder.router,
    search.router,
    tag.router,
    template.router,
    timer.router,
    habit.router,
    insight.router,
    user.router,
    backup.router,
]
for _router in _protected:
    app.include_router(_router, dependencies=[Depends(require_auth)])

# 资料库单独挂载：各端点自行声明鉴权。
# 因为 GET /api/resources/pdf 要供 <iframe src> 直连（带不了 Authorization 头），
# 它改用「短时票据 + HMAC 绑定用户与路径」鉴权；/tree 与 /content 仍是 Bearer。
# 详见 backend/routers/resources.py 顶部说明。
app.include_router(resources.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8001, reload=True)
