"""MaWork 自适应过载保护与请求安全护栏。

设计原则（不绑定任何机器规格）：

- 所有阈值都【运行时测量】系统真实资源（Linux 的 /proc/meminfo、/proc/loadavg、
  ru_maxrss），而不是写死“2核2G”之类的假设。机器越大越宽松、越小越早熔断。
- 两条铁律：
  1) 服务器不因过载崩 —— 一旦内存/负载逼近极限，重路由优先被 503 拦掉，
     轻路由（登录/日报/计时）保留，绝不雪崩。
  2) 单个超大请求拖不垮 —— 任何请求体都有【硬上限 + 相对可用内存的上限】，
     超过直接 413；大文件读取也按可用内存动态封顶。

仅依赖 Python 标准库（Linux /proc 接口），无需额外 pip 包；非 Linux 时优雅降级。
"""

import json
import os
import resource
from typing import Optional

from . import config

# 运行时指标（供 /api/health 回报，便于监控是否触发护栏）
METRICS: dict = {"in_flight": 0, "cap": 0, "shed_reason": None}


class RequestBodyTooLarge(Exception):
    """请求体超过上限。

    由 MaxBodySizeMiddleware 在读取流式 body 时抛出，
    由 main.py 注册的 exception handler 转成 413 响应。
    之所以走异常而不是「静默截断 body」，是因为截断后下游只会报
    含糊的 400/422，而 413 + 明确文案才是设计上要给用户的信息。
    """


# ---------------------------------------------------------------------------
# 运行时测量（Linux /proc，零依赖；非 Linux 时返回 None 优雅降级）
# ---------------------------------------------------------------------------
def read_meminfo() -> Optional[dict]:
    """返回 /proc/meminfo 的键值（值为 kB 整数）。"""
    try:
        info: dict = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, val = line.partition(":")
                val = val.strip().split()
                if val:
                    info[key.strip()] = int(val[0])  # 单位 kB
        return info
    except OSError:
        return None


def read_loadavg_1() -> Optional[float]:
    """返回 1 分钟平均负载。"""
    try:
        with open("/proc/loadavg") as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def process_rss_bytes() -> int:
    """当前进程常驻内存（ru_maxrss，Linux 单位为 kB）。"""
    try:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    except (OSError, ValueError):
        return 0


def cpu_count() -> int:
    return os.cpu_count() or 1


# ---------------------------------------------------------------------------
# 自适应阈值（基于实时资源，不写死机器规格）
# ---------------------------------------------------------------------------
def adaptive_concurrency_cap() -> int:
    """并发上限随 CPU 数浮动：至少 8，约 cpu×N，受内存粗略约束。"""
    return max(8, cpu_count() * config.GUARD_CONCURRENCY_PER_CPU)


def max_body_bytes() -> int:
    """单请求体上限 = min(硬上限, 当前可用内存 × 比例)。"""
    hard = config.GUARD_MAX_BODY_BYTES
    info = read_meminfo()
    if info:
        avail = info.get("MemAvailable", 0) * 1024  # bytes
        rel = int(avail * config.GUARD_BODY_MEM_FRACTION)
        if rel > 0:
            return min(hard, rel)
    return hard


def max_file_read_bytes() -> int:
    """单个文件可读上限 = min(硬上限, 可用内存 × 比例)，用于资源/搜索读取。"""
    hard = config.GUARD_MAX_BODY_BYTES
    info = read_meminfo()
    if info:
        avail = info.get("MemAvailable", 0) * 1024
        rel = int(avail * config.GUARD_BODY_MEM_FRACTION)
        if rel > 0:
            return min(hard, rel)
    return hard


def system_under_pressure() -> tuple[bool, Optional[str]]:
    """返回 (是否逼近极限, 原因)。仅基于实时测量，不假设机器大小。"""
    info = read_meminfo()
    if info:
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", total)
        floor_bytes = config.GUARD_MEM_AVAILABLE_FLOOR_MB * 1024 * 1024
        # 可用内存低于绝对地板：任何规格下都危险
        if avail * 1024 < floor_bytes:
            return True, "mem_floor"
        # 可用内存低于总量比例：小机器早触发、大机器晚触发
        if total and avail < total * config.GUARD_MEM_AVAILABLE_PCT:
            return True, "mem_pct"
    load = read_loadavg_1()
    if load is not None and load > cpu_count() * config.GUARD_LOADAVG_PER_CPU:
        return True, "load"
    return False, None


# 重路由：资源紧张时优先被熔断，保证核心轻路由（登录/日报/计时）可用
HEAVY_PREFIXES = ("/api/search", "/api/resources", "/api/backup", "/api/analysis")


def is_heavy(path: str) -> bool:
    p = path.split("?")[0]
    return any(p.startswith(prefix) for prefix in HEAVY_PREFIXES)


# ---------------------------------------------------------------------------
# 响应快捷构造
# ---------------------------------------------------------------------------
async def _send(send, status: int, headers: list, body: bytes):
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _json_response(send, status: int, detail: str):
    body = json.dumps({"detail": detail, "ok": False}, ensure_ascii=False).encode("utf-8")
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode()),
        (b"cache-control", b"no-store"),
    ]
    await _send(send, status, headers, body)


# ---------------------------------------------------------------------------
# 1) 请求体大小上限中间件（最外层，超大请求最先被拦）
# ---------------------------------------------------------------------------
class MaxBodySizeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method = scope.get("method", "GET")
        if method not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)

        limit = max_body_bytes()
        headers = {k.decode().lower(): v for k, v in scope.get("headers", [])}
        cl = headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > limit:
            return await _json_response(
                send, 413, f"请求体过大（>{limit} 字节），已被拒绝"
            )

        received = 0

        async def wrapped_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > limit:
                    # 立即以 413 终结请求。
                    # 早先的实现是「置 exceeded 标志 + 返回 more=False 截断 body」，
                    # 但那个标志在 self.app() 之后才可能为真，调用前的判断是死代码；
                    # 结果分块超限的请求会拿到残缺 body，由下游报含糊的 400/422，
                    # 而设计中的 413 从不出现。抛异常交给 ExceptionMiddleware
                    # 转成响应，语义才对；异常会向外传播穿过 CORS，浏览器也能读到。
                    raise RequestBodyTooLarge(f"请求体过大（>{limit} 字节），已被拒绝")
            return msg

        return await self.app(scope, wrapped_receive, send)


# ---------------------------------------------------------------------------
# 2) 并发 + 压力护栏中间件（软熔断，绝不雪崩）
# ---------------------------------------------------------------------------
class GuardMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        base = path.split("?")[0].rstrip("/")
        # 健康检查始终放行（且单独计数），便于监控是否触发护栏
        if base == "/api/health" or base.endswith("/api/health"):
            return await self.app(scope, receive, send)

        cap = adaptive_concurrency_cap()
        METRICS["cap"] = cap
        METRICS["in_flight"] += 1
        try:
            # 并发上限：超过直接 503，避免请求堆积把服务器拖垮
            if METRICS["in_flight"] > cap:
                METRICS["shed_reason"] = "concurrency"
                return await _json_response(
                    send, 503, f"服务繁忙（并发超过 {cap}），请稍后再试"
                )
            # 资源逼近极限：重路由优先熔断，轻路由保留
            under, reason = system_under_pressure()
            if under and is_heavy(path):
                METRICS["shed_reason"] = reason
                return await _json_response(
                    send, 503,
                    f"服务器资源紧张（{reason}），该操作暂不可用，请稍后再试",
                )
            METRICS["shed_reason"] = None
            return await self.app(scope, receive, send)
        finally:
            METRICS["in_flight"] -= 1


# ---------------------------------------------------------------------------
# 3) 安全响应头中间件（纵深防御；HSTS/CSP 可开关，避免影响现有前端）
# ---------------------------------------------------------------------------
_BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

# 唯一需要被「同源 iframe 内嵌渲染」的端点：PDF 预览。
# 该端点用短时票据鉴权（见 routers/resources.py），目的就是让
# <iframe src="/api/resources/pdf?..."> 能直连并按 Range 分页加载。
# 若这里仍发 DENY，浏览器会直接拒绝渲染 → 预览区一片空白。
# 收紧为 SAMEORIGIN：只放开同源嵌套，外站依然无法把它套进自己的页面，
# DENY 原本防的「点击劫持」对外站场景没有削弱。
_EMBEDDABLE_PATHS = frozenset({"/api/resources/pdf"})

_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none';"
)


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # scope["path"] 不含 query string，可直接精确比对
        embeddable = scope.get("path") in _EMBEDDABLE_PATHS

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                existing = {k.decode().lower(): v for k, v in message.get("headers", [])}
                for k, v in _BASE_SECURITY_HEADERS.items():
                    if k.lower() in existing:
                        continue
                    if k == "X-Frame-Options" and embeddable:
                        # 下面单独发 SAMEORIGIN，跳过默认的 DENY
                        continue
                    message["headers"].append((k.encode(), v.encode()))
                if embeddable:
                    message["headers"].append((b"x-frame-options", b"SAMEORIGIN"))
                if config.ENABLE_HSTS and b"strict-transport-security" not in existing:
                    message["headers"].append(
                        (b"strict-transport-security",
                         b"max-age=31536000; includeSubDomains")
                    )
                if config.ENABLE_CSP and b"content-security-policy" not in existing:
                    csp = _CSP
                    if embeddable:
                        # frame-ancestors 'self' 与 SAMEORIGIN 对齐，其余指令不放宽
                        csp = csp.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
                    message["headers"].append((b"content-security-policy", csp.encode()))
            await send(message)

        return await self.app(scope, receive, wrapped_send)
