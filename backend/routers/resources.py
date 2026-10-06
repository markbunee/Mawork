"""资料浏览路由：浏览 workspaces 下的文件夹结构，读取 md/pdf 内容。

安全：所有路径都解析在 workspaces 根内，禁止目录穿越。

PDF 预览为什么需要「短时票据」（2026-10-05 性能优化）：
`<iframe src="...">` 无法携带 Authorization 头，而本路由组是强制鉴权的。
若沿用「fetch 带令牌 → 拿 blob → createObjectURL」的旧做法会带来三个问题：
1. 必须等**整份文件下载完**才能开始渲染，首字节延迟 = 文件大小 / 带宽；
2. blob: 协议下浏览器 PDF 阅读器**无法发起 HTTP Range 请求**，
   只能整份拉完，无法按需分页加载；
3. 每次切换文件都重新全量下载，零缓存，且内存里常驻一份完整副本。

因此改为：前端先用带令牌的接口换一个**短期 HMAC 票据**，
再把「真实 URL + 票据」直接交给 iframe，由后端按 Range 边下边给。
"""

import hashlib
import hmac
import os
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import (APIRouter, Body, Depends, File, Header, HTTPException, Query,
                     UploadFile)
from fastapi.responses import Response, StreamingResponse

from .. import config, ctx, guard
from ..auth import require_auth
from ..services import user as user_svc

router = APIRouter(prefix="/api/resources", tags=["resources"])

# md / txt：可在线预览与编辑
MD_EXTS = {".md", ".markdown", ".txt"}
# pdf：可内嵌预览（走 Range 流式，见 _file_response）
PDF_EXTS = {".pdf"}

def _root() -> Path:
    """当前用户的资料根目录（随请求用户变化，故不能用模块级常量）。"""
    return config.data_dir()


def _resolve(rel: str) -> Path:
    """把相对路径解析为资料根内的绝对路径，并做安全校验。"""
    root = _root()
    # 规范化，防止 .. 穿越
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="非法路径")
    return target


# ---------------------------------------------------------------------------
# 短时访问票据：让 <iframe> 免 Authorization 头直连
# ---------------------------------------------------------------------------
# 票据 = uid.exp.HMAC-SHA256(secret, uid|exp|path)[:32]
# 绑定「用户 + 路径 + 过期时间」：既不能跨用户复用，也不能改 path 换文件。
# uid 显式编进票据，是为了让 iframe 请求（无登录态）也能还原出数据空间。
# TTL 取 30 分钟：够读完一份长文档，又不会成为长期有效凭据；
# 前端还会在到期前静默续期（见 ResourcesView.vue 的 startRenew）。
TICKET_TTL = 1800


def _ticket_mac(uid: int, exp: int, rel: str) -> str:
    msg = f"{uid}|{exp}|{rel}".encode("utf-8")
    return hmac.new(
        config.AUTH_SECRET.encode("utf-8"), msg, hashlib.sha256
    ).hexdigest()[:32]


def _issue_ticket(uid: int, rel: str) -> str:
    exp = int(time.time()) + TICKET_TTL
    return f"{uid}.{exp}.{_ticket_mac(uid, exp, rel)}"


def _verify_ticket(ticket: str, rel: str) -> int | None:
    """校验票据并返回其绑定的 uid；无效/过期/改过 path 一律返回 None。"""
    try:
        uid_s, exp_s, mac = (ticket or "").split(".", 2)
        uid, exp = int(uid_s), int(exp_s)
    except (ValueError, AttributeError):
        return None
    if not mac or exp < int(time.time()):
        return None
    # compare_digest 防时序侧信道
    if not hmac.compare_digest(mac, _ticket_mac(uid, exp, rel)):
        return None
    return uid


# ---------------------------------------------------------------------------
# HTTP Range：浏览器 PDF 阅读器靠它按需分页加载
# ---------------------------------------------------------------------------
# PDF 走 Range 后**不再把文件读进内存**，因此可以放宽体积上限。
PDF_MAX_BYTES = 512 * 1024 * 1024
CHUNK = 64 * 1024  # 每次读 64KB，内存占用恒定


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """解析 Range: bytes=...，返回闭区间 (start, end)；不合法返回 None。

    支持三种写法：bytes=0-100 / bytes=100- / bytes=-500（末尾 500 字节）。
    """
    if not header:
        return None
    spec = header.partition("=")[2].split(",")[0].strip()
    start_s, sep, end_s = spec.partition("-")
    if not sep:
        return None
    start_s, end_s = start_s.strip(), end_s.strip()

    if not start_s:
        # bytes=-N：最后 N 字节
        if not end_s.isdigit():
            return None
        n = int(end_s)
        if n <= 0:
            return None
        start, end = max(0, size - n), size - 1
    else:
        if not start_s.isdigit():
            return None
        start = int(start_s)
        if not end_s:
            end = size - 1
        else:
            if not end_s.isdigit():
                return None
            end = min(int(end_s), size - 1)

    if start >= size or start > end:
        return None
    return start, end


def _iter_file(path: Path, start: int, end: int):
    """从 start 读到 end 的块迭代器：内存占用恒定，不随文件大小增长。"""
    remaining = end - start + 1
    with path.open("rb") as f:
        f.seek(start)
        while remaining > 0:
            buf = f.read(min(CHUNK, remaining))
            if not buf:
                break
            remaining -= len(buf)
            yield buf


def _file_response(target: Path, range_header: str | None,
                   if_none_match: str | None) -> Response:
    """带 Range / ETag / 缓存头的文件响应（PDF 预览专用）。"""
    st = target.stat()
    size = st.st_size
    etag = f'"{st.st_mtime_ns:x}-{size:x}"'

    # 304：命中浏览器缓存，连 206 都不用发
    if if_none_match and if_none_match.strip() == etag:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": "private, max-age=3600"},
        )

    base_headers = {
        "ETag": etag,
        # private：数据属当前用户，浏览器可缓存，共享代理不得缓存
        "Cache-Control": "private, max-age=3600",
        "Accept-Ranges": "bytes",  # 声明支持 Range，浏览器才会尝试分页加载
    }

    rng = _parse_range(range_header, size)
    if range_header and rng is None:
        # 请求了 Range 但无法满足（越界 / 格式错）
        return Response(
            status_code=416,
            headers={**base_headers, "Content-Range": f"bytes */{size}"},
        )

    if rng is None:
        start, end = 0, size - 1
        status = 200
    else:
        start, end = rng
        status = 206
        base_headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    cd_name = quote(target.name)
    headers = {
        **base_headers,
        "Content-Length": str(end - start + 1),
        # inline 才能内嵌预览；filename* 兼容中文名
        "Content-Disposition": f"inline; filename*=UTF-8''{cd_name}",
    }
    return StreamingResponse(
        _iter_file(target, start, end),
        status_code=status,
        media_type="application/pdf",
        headers=headers,
    )


# 目录树中需要忽略的文件
IGNORE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORE_EXTS = {".db", ".db-journal", ".db-wal", ".db-shm"}

# 目录树递归深度上限，避免异常深的目录结构导致递归爆栈/内存暴涨
MAX_TREE_DEPTH = 8


def _visible(child: Path) -> bool:
    if child.name.startswith(".") or child.name in IGNORE_NAMES:
        return False
    if child.is_file() and child.suffix.lower() in IGNORE_EXTS:
        return False
    return True


def _build_node(target: Path, depth: int = 0) -> dict:
    """递归构建目录树节点（限制深度，超深目录不再展开）。"""
    node = {
        "name": target.name,
        "path": str(target.relative_to(_root())).replace("\\", "/") if target != _root() else "",
        "type": "dir",
        "ext": "",
        "children": [],
    }
    if depth >= MAX_TREE_DEPTH:
        return node
    children = sorted(
        (c for c in target.iterdir() if _visible(c)),
        key=lambda p: (not p.is_dir(), p.name.lower()),
    )
    for child in children:
        if child.is_dir():
            node["children"].append(_build_node(child, depth + 1))
        else:
            node["children"].append({
                "name": child.name,
                "path": str(child.relative_to(_root())).replace("\\", "/"),
                "type": "file",
                "ext": child.suffix.lower(),
                "children": [],
            })
    return node


@router.get("/tree")
def get_tree(_: dict = Depends(require_auth)):
    """返回 workspaces 的完整目录树（递归，限制深度）。

    返回：{ name, path, type: dir, children: [...] }
    """
    root = _root()
    if not root.exists():
        raise HTTPException(status_code=404, detail="资料目录不存在")
    return _build_node(root)


@router.get("/content")
def read_content(
    path: str,
    range_header: str | None = Header(default=None, alias="Range"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    _: dict = Depends(require_auth),
):
    """读取文件内容。md/txt 返回文本；pdf 按 Range 边下边给（支持分页/断点/304）。

    体积上限按类型区分：
    - md/txt 要整份读进内存渲染，沿用按可用内存自适应的上限；
    - pdf 走 Range 流式，**不占内存**，因此用独立且宽松的硬上限。
    """
    target = _resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    ext = target.suffix.lower()
    size = target.stat().st_size

    if ext in PDF_EXTS:
        if size > PDF_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"文件过大（{size} 字节 > 上限 {PDF_MAX_BYTES}），请下载后查看",
            )
        return _file_response(target, range_header, if_none_match)

    limit = guard.max_file_read_bytes()
    if size > limit:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{size} 字节 > 上限 {limit}），服务器暂不预览，请下载后查看",
        )

    if ext in MD_EXTS:
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = target.read_text(encoding="gbk", errors="replace")
        return {"type": "markdown", "name": target.name, "content": content}
    raise HTTPException(status_code=415, detail="不支持的文件类型")


# ---------------------------------------------------------------------------
# PDF 预览：票据换取可直连的 URL
# ---------------------------------------------------------------------------
@router.get("/pdf-token")
def pdf_token(path: str = Query(..., description="相对路径"),
              user: dict = Depends(require_auth)):
    """用登录态换一个**短时票据**，拼出 iframe 可直连的真实 URL。

    浏览器 PDF 阅读器只认 URL，没法带 Authorization 头；而 blob: 方案又会让它
    失去 Range 能力（整份下载完才渲染，且每次重下）。票据把「鉴权」压缩进 URL，
    从而既保留 Bearer 保护，又能让 <iframe src> 直接走 Range。
    """
    target = _resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if target.suffix.lower() not in PDF_EXTS:
        raise HTTPException(status_code=415, detail="仅 PDF 需要此接口")

    ticket = _issue_ticket(int(user["id"]), path)
    query = urlencode({"path": path, "ticket": ticket})
    return {
        # 相对路径，浏览器经 nginx /api 反代到后端
        "url": f"{router.prefix}/pdf?{query}",
        "expires_in": TICKET_TTL,
    }


@router.get("/pdf")
def stream_pdf(
    path: str = Query(..., description="相对路径"),
    ticket: str = Query(..., description="pdf-token 签发的短时票据"),
    range_header: str | None = Header(default=None, alias="Range"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    """凭票据流式返回 PDF，**免 Authorization 头**（供 iframe 直接 src 使用）。

    鉴权强度等价于一次登录：票据 30 分钟过期、HMAC 绑定当前用户与该文件路径，
    改 path 或换账号都无法复用。

    ⚠️ 必须先用票据里的 uid 绑定数据空间：iframe 请求没有登录态，
    ctx.current_uid() 为 None 时 data_dir() 会退回 workspaces 根目录，
    那样 _resolve() 的用户隔离就形同虚设了。
    """
    uid = _verify_ticket(ticket, path)
    if uid is None:
        raise HTTPException(status_code=403, detail="预览链接无效或已过期，请重新打开")

    # 票据本身只证明「签名没被篡改」，不反映账号的**当前**状态。
    # 必须回查一次：账号被停用/删除、或管理员重置了密码后，
    # 此前签发的票据不应继续可用（与 require_auth 的检查保持一致）。
    rec = user_svc.get_raw(uid)
    if rec is None or rec["status"] != "active":
        raise HTTPException(status_code=403, detail="账号不存在或已停用")

    token = ctx.set_uid(uid)
    try:
        target = _resolve(path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        if target.suffix.lower() not in PDF_EXTS:
            raise HTTPException(status_code=415, detail="仅支持 PDF")
        if target.stat().st_size > PDF_MAX_BYTES:
            raise HTTPException(status_code=413, detail="文件过大，请下载后查看")
        return _file_response(target, range_header, if_none_match)
    finally:
        ctx.reset_uid(token)


# ---------------------------------------------------------------------------
# 文件管理：下载 / 上传 / 删除 / 重命名 / 新建目录 / md 保存
# ---------------------------------------------------------------------------
# 设计要点：
# - 一切路径都过 _resolve()，越界（.. / 绝对路径 / 符号链接逃逸）一律 403；
# - 所有写操作串行化到 _WRITE_LOCK，防止并发的删/改名/上传互相踩踏；
# - 上传与保存都走「同目录临时文件 + 原子改名」，中途失败不留半截文件；
# - 删除只允许落在用户目录内，且目录需为空才可删（防误删整棵树）。
#
# 边界：单文件删除与覆盖上传**不可撤销**（整目录快照备份已下线）。
# 删除有前端二次确认兜底，覆盖上传有预检确认——这是目前仅剩的防误操作手段。
_WRITE_LOCK = threading.RLock()

# 单个上传文件大小上限：与请求体上限同源，但这里给一个明确的独立值，
# 便于将来单独调整。走 multipart 时整体还受 guard.MaxBodySizeMiddleware 约束。
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MiB
# 单次拖拽最多几个文件（防止一次拖几百个把内存/句柄打满）
MAX_UPLOAD_FILES = 50


def _ensure_parent(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)


def _guard_size(name: str, size: int) -> None:
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"「{name}」过大（{size} 字节 > 上限 {MAX_UPLOAD_BYTES}），请改用 zip 批量上传",
        )


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


@router.get("/download")
def download_file(path: str = Query(..., description="相对路径"),
                  range_header: str | None = Header(default=None, alias="Range"),
                  _: dict = Depends(require_auth)):
    """**指定文件**下载（取代整目录打包）。

    走 Bearer 头即可（前端 fetchBlobUrl 拿 blob 再触发保存），因此不需要票据。
    Range / ETag 复用 _file_response，与 PDF 预览同一套逻辑，大文件不占内存。
    """
    target = _resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    size = target.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{_human(size)} > {_human(MAX_UPLOAD_BYTES)}），请用 zip 批量下载",
        )
    resp = _file_response(target, range_header, None)
    # 下载而非内嵌预览：改成 attachment，文件名做 RFC 5987 编码以兼容中文
    resp.headers["content-disposition"] = (
        f"attachment; filename*=UTF-8''{quote(target.name)}"
    )
    return resp


# zip 流式打包的临时文件上限：超过此体积直接 413，避免把磁盘/内存打爆。
ZIP_MAX_BYTES = 200 * 1024 * 1024  # 200 MiB
ZIP_CHUNK = 64 * 1024


@router.get("/zip")
def download_all_zip(_: dict = Depends(require_auth)):
    """把**当前用户**资料目录下的全部文件打包成 zip 下载（整目录完整备份）。

    与目录树不同：这里**包含** .db 等用户数据文件——浏览树为整洁会剔除它们，
    但备份应当能还原整个资料目录，所以 db 一并打包。仅跳过 .DS_Store 等
    系统垃圾文件。用临时文件承载 zip（zipfile 写模式需要可寻址的文件对象），
    写完再分块流式吐出，临时文件在生成器结束时删除，断连也不会留垃圾。
    """
    root = _root()
    if not root.exists():
        raise HTTPException(status_code=404, detail="资料目录不存在")

    # 先估算总体积，超过上限直接拒绝（避免打包炸盘）
    total = 0
    members: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        # 完整备份：保留用户的 .db 等数据文件；仅跳过系统垃圾文件
        if p.name in IGNORE_NAMES:
            continue
        try:
            total += p.stat().st_size
        except OSError:
            continue
        members.append(p)
        if total > ZIP_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"文件总体积过大（{_human(total)} > {_human(ZIP_MAX_BYTES)}），请逐个下载",
            )

    tmp = tempfile.NamedTemporaryFile(prefix="mawork-zip-", suffix=".zip", delete=False)
    tmp_path = tmp.name
    tmp.close()
    uid = ctx.current_uid()
    fname = f"u{uid}-files.zip" if uid else "workspaces-files.zip"
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in members:
                arc = p.relative_to(root).as_posix()
                zf.write(p, arc)
        size = os.path.getsize(tmp_path)

        def iter_zip():
            try:
                with open(tmp_path, "rb") as f:
                    while True:
                        buf = f.read(ZIP_CHUNK)
                        if not buf:
                            break
                        yield buf
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        return StreamingResponse(
            iter_zip(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}",
                "Content-Length": str(size),
            },
        )
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _safe_basename(name: str) -> str:
    """校验上传文件名，返回**纯文件名**；不合法直接 422 拒绝。

    这里刻意**不做静默净化**：早期实现是把 "../../evil.txt" 截成 "evil.txt"
    再保存，虽然不会越界，但若用户目录里恰好已有 evil.txt，就会被静默覆盖——
    数据丢了而用户完全不知情。改成拒绝 + 明确报错更安全。

    正常浏览器拖拽上传时 File.name 本就是纯文件名，不会触发此分支。
    """
    raw = (name or "").replace("\\", "/")
    base = raw.split("/")[-1].strip()
    if not base or base in (".", "..") or base.startswith("."):
        raise HTTPException(status_code=422, detail=f"非法的文件名：{name or '(空)'}")
    if "\x00" in base or any(c in base for c in ("\\", "/")):
        raise HTTPException(status_code=422, detail=f"非法的文件名：{name}")
    if raw != base:
        # 原名带路径成分（客户端传了完整路径 / 有人构造穿越）
        raise HTTPException(
            status_code=422,
            detail=f"文件名不能包含路径，请只上传文件本身：{name}",
        )
    return base


@router.post("/upload")
def upload_files(
    dir: str = Query("", description="目标目录（相对路径，空=根目录）"),
    files: list[UploadFile] = File(..., description="一个或多个文件"),
    _: dict = Depends(require_auth),
):
    """**拖拽上传**：一次可传多个文件到指定目录。

    语义与用户直觉一致：
    - 同名 → 覆盖（明确回报哪些被覆盖）；
    - 新名 → 新增；
    - 不影响未出现在本次上传里的任何文件。

    写入用「同目录临时文件 + 原子改名」，中途失败不会留下写了一半的文件。
    """
    if not files:
        raise HTTPException(status_code=422, detail="未选择文件")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=413, detail=f"一次最多上传 {MAX_UPLOAD_FILES} 个文件"
        )

    rel_dir = (dir or "").strip().strip("/")
    base = _resolve(rel_dir) if rel_dir else _root()
    if not base.is_dir():
        raise HTTPException(status_code=404, detail="目标目录不存在")

    saved: list[dict] = []
    with _WRITE_LOCK:
        for f in files:
            name = _safe_basename(f.filename or "")
            # 复用统一校验：拼上目录后 resolve，越界即 403
            target = _resolve(f"{rel_dir}/{name}" if rel_dir else name)
            data = f.file.read(MAX_UPLOAD_BYTES + 1)
            _guard_size(name, len(data))
            existed = target.exists()
            tmp = target.with_name(f".{target.name}.part")
            try:
                with open(tmp, "wb") as out:
                    out.write(data)
                tmp.replace(target)  # 同目录 rename，原子生效
            except OSError as e:
                tmp.unlink(missing_ok=True)
                raise HTTPException(status_code=500, detail=f"保存「{name}」失败：{e}")
            saved.append({
                "name": name,
                "path": target.relative_to(_root().resolve()).as_posix(),
                "size": len(data),
                "overwritten": existed,
            })
    return {
        "ok": True,
        "saved": saved,
        "uploaded": len(saved),
        "overwritten": sum(1 for s in saved if s["overwritten"]),
        "total_size": _human(sum(s["size"] for s in saved)),
    }


@router.delete("/item")
def delete_item(path: str = Query(..., description="相对路径"),
                _: dict = Depends(require_auth)):
    """删除文件或**空**目录。

    目录必须为空才允许删——不提供递归删除，避免一个误操作把整棵子树清掉。
    要删整棵目录，请逐个删其中文件。
    """
    target = _resolve(path)
    if target == _root().resolve():
        raise HTTPException(status_code=403, detail="不能删除数据根目录")
    if not target.exists():
        raise HTTPException(status_code=404, detail="目标不存在")
    with _WRITE_LOCK:
        if target.is_dir():
            try:
                target.rmdir()
            except OSError:
                raise HTTPException(status_code=409, detail="文件夹非空，请先删除其中文件")
        else:
            try:
                target.unlink()
            except OSError as e:
                raise HTTPException(status_code=500, detail=f"删除失败：{e}")
    return {"ok": True, "deleted": path}


@router.post("/rename")
def rename_item(payload: dict, _: dict = Depends(require_auth)):
    """重命名 / 移动（源 path → 目标 new_path，均为相对路径）。"""
    src_rel = str(payload.get("path") or "").strip()
    dst_rel = str(payload.get("new_path") or "").strip()
    if not src_rel or not dst_rel:
        raise HTTPException(status_code=422, detail="path 与 new_path 均不能为空")
    src = _resolve(src_rel)
    dst = _resolve(dst_rel)
    if not src.exists():
        raise HTTPException(status_code=404, detail="源不存在")
    if src == _root().resolve():
        raise HTTPException(status_code=403, detail="不能重命名数据根目录")
    if dst.exists():
        raise HTTPException(status_code=409, detail=f"目标已存在：{dst_rel}")
    with _WRITE_LOCK:
        _ensure_parent(dst)
        try:
            src.replace(dst)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"重命名失败：{e}")
    return {"ok": True, "path": dst_rel}


@router.post("/folder")
def create_folder(payload: dict, _: dict = Depends(require_auth)):
    """新建目录（父目录自动创建）。"""
    rel = str(payload.get("path") or "").strip().strip("/")
    if not rel:
        raise HTTPException(status_code=422, detail="path 不能为空")
    d = _resolve(rel)
    if d.exists():
        raise HTTPException(status_code=409, detail="同名文件或目录已存在")
    with _WRITE_LOCK:
        try:
            d.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise HTTPException(status_code=409, detail="同名文件或目录已存在")
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"新建目录失败：{e}")
    return {"ok": True, "path": rel}


@router.put("/file")
def save_text_file(payload: dict, _: dict = Depends(require_auth)):
    """保存 md/txt **在线编辑**内容。

    - 必须是 .md/.markdown/.txt（与可预览类型一致），避免被当成任意文件写；
    - 「临时文件 + 原子改名」，中途失败不会破坏原文件；
    - 超过按可用内存自适应的上限直接 413，不硬塞。
    """
    rel = str(payload.get("path") or "").strip()
    content = payload.get("content")
    if not rel:
        raise HTTPException(status_code=422, detail="path 不能为空")
    if not isinstance(content, str):
        raise HTTPException(status_code=422, detail="content 必须是字符串")
    target = _resolve(rel)
    if target.suffix.lower() not in MD_EXTS:
        raise HTTPException(status_code=415, detail="仅支持编辑 md / markdown / txt")
    size = len(content.encode("utf-8"))
    limit = guard.max_file_read_bytes()
    if size > limit:
        raise HTTPException(status_code=413, detail=f"内容过大（{_human(size)} > {_human(limit)}）")
    with _WRITE_LOCK:
        existed = target.is_file()
        _ensure_parent(target)
        tmp = target.with_name(f".{target.name}.saving")
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            tmp.replace(target)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"保存失败：{e}")
    return {"ok": True, "path": rel, "size": size, "created": not existed}


# ---------------------------------------------------------------------------
# 上传预检：覆盖前先告诉前端哪些文件会重名
# ---------------------------------------------------------------------------
@router.post("/upload/precheck")
def precheck_upload(
    dir: str = Query("", description="目标目录（相对路径，空=根目录）"),
    payload: dict = Body(..., description="{ names: [...] }"),
    _: dict = Depends(require_auth),
):
    """上传前预检：返回「已存在会被覆盖」与「可新增」两类清单。

    前端据此弹一次确认（全部覆盖 / 跳过重名 / 取消），
    避免用户稀里糊涂覆盖掉同名文件却不知情。
    """
    rel_dir = (dir or "").strip().strip("/")
    base = _resolve(rel_dir) if rel_dir else _root()
    if not base.is_dir():
        raise HTTPException(status_code=404, detail="目标目录不存在")

    names = payload.get("names") or []
    if not isinstance(names, list):
        raise HTTPException(status_code=422, detail="names 必须是数组")

    conflicts: list[dict] = []
    fresh: list[str] = []
    for raw in names[:MAX_UPLOAD_FILES]:
        try:
            name = _safe_basename(str(raw))
        except HTTPException:
            continue
        target = base / name
        if target.exists():
            try:
                st = target.stat()
                conflicts.append({
                    "name": name,
                    "size": st.st_size,
                    "is_dir": target.is_dir(),
                    "mtime": int(st.st_mtime),
                })
            except OSError:
                conflicts.append({"name": name, "size": 0, "is_dir": False, "mtime": 0})
        else:
            fresh.append(name)
    return {
        "ok": True,
        "dir": rel_dir,
        "conflicts": conflicts,
        "fresh": fresh,
        "has_conflict": len(conflicts) > 0,
    }
