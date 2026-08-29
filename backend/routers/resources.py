"""资料浏览路由：浏览 workspaces 下的文件夹结构，读取 md/pdf 内容。

安全：所有路径都解析在 workspaces 根内，禁止目录穿越。
"""

import io
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import config

router = APIRouter(prefix="/api/resources", tags=["resources"])

# 可预览的文件扩展名
PREVIEW_EXTS = {".md", ".markdown", ".pdf", ".txt"}
# md 相关扩展
MD_EXTS = {".md", ".markdown", ".txt"}
PDF_EXTS = {".pdf"}

ROOT = config.WORKSPACES_DIR


def _resolve(rel: str) -> Path:
    """把相对路径解析为 ROOT 内的绝对路径，并做安全校验。"""
    # 规范化，防止 .. 穿越
    target = (ROOT / rel).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="非法路径")
    return target


# 目录树中需要忽略的文件
IGNORE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORE_EXTS = {".db", ".db-journal", ".db-wal", ".db-shm"}


def _visible(child: Path) -> bool:
    if child.name.startswith(".") or child.name in IGNORE_NAMES:
        return False
    if child.is_file() and child.suffix.lower() in IGNORE_EXTS:
        return False
    return True


def _build_node(target: Path) -> dict:
    """递归构建目录树节点。"""
    node = {
        "name": target.name,
        "path": str(target.relative_to(ROOT)).replace("\\", "/") if target != ROOT else "",
        "type": "dir",
        "ext": "",
        "children": [],
    }
    children = sorted(
        (c for c in target.iterdir() if _visible(c)),
        key=lambda p: (not p.is_dir(), p.name.lower()),
    )
    for child in children:
        if child.is_dir():
            node["children"].append(_build_node(child))
        else:
            node["children"].append({
                "name": child.name,
                "path": str(child.relative_to(ROOT)).replace("\\", "/"),
                "type": "file",
                "ext": child.suffix.lower(),
                "children": [],
            })
    return node


@router.get("/tree")
def get_tree():
    """返回 workspaces 的完整目录树（递归）。

    返回：{ name, path, type: dir, children: [...] }
    """
    if not ROOT.exists():
        raise HTTPException(status_code=404, detail="workspaces 目录不存在")
    return _build_node(ROOT)


@router.get("/content")
def read_content(path: str):
    """读取文件内容。md/txt 返回文本，pdf 返回二进制流。"""
    target = _resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    ext = target.suffix.lower()
    if ext in PDF_EXTS:
        data = target.read_bytes()
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename={target.name}"},
        )
    if ext in MD_EXTS:
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = target.read_text(encoding="gbk", errors="replace")
        return {"type": "markdown", "name": target.name, "content": content}
    raise HTTPException(status_code=415, detail="不支持的文件类型")
