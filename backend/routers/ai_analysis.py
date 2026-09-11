"""AI 报告分析路由：读写 workspaces/{year}/analysis/ 下的 Markdown 报告。

目录约定：
- 每个年份文件夹下可有 analysis/ 目录，支持任意层级子文件夹
- 仅允许读写 .md 文件
- 所有 path 参数为相对 analysis/ 的路径，禁止路径穿越
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _analysis_root(year: str) -> Path:
    return config.WORKSPACES_DIR / year / "analysis"


def _safe_path(year: str, rel: str) -> Path:
    """将相对路径解析为 analysis 下的安全绝对路径，防路径穿越。"""
    rel = (rel or "").strip().lstrip("/").replace("\\", "/")
    if not rel:
        raise HTTPException(status_code=422, detail="path 不能为空")
    root = _analysis_root(year).resolve()
    target = (root / rel).resolve()
    if root != target and root not in target.parents:
        raise HTTPException(status_code=422, detail="非法路径")
    return target


def _build_tree(root: Path, base: Path | None = None) -> list[dict]:
    """递归构建目录树：[{name, path, type: dir|file, children?}]

    path 始终相对于 analysis 根目录（base），保证前端可直接用 path 读写文件。
    """
    base = base or root
    items = []
    if not root.exists():
        return items
    for p in sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name)):
        rel = p.relative_to(base)
        if p.is_dir():
            items.append({
                "name": p.name,
                "path": str(rel).replace("\\", "/"),
                "type": "dir",
                "children": _build_tree(p, base),
            })
        elif p.suffix.lower() == ".md":
            items.append({
                "name": p.name,
                "path": str(rel).replace("\\", "/"),
                "type": "file",
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            })
    return items


@router.get("/years")
def list_years():
    """列出 workspaces 下的年份文件夹。"""
    if not config.WORKSPACES_DIR.exists():
        return {"years": []}
    years = [
        d.name for d in sorted(config.WORKSPACES_DIR.iterdir(), reverse=True)
        if d.is_dir() and d.name.isdigit()
    ]
    return {"years": years}


@router.get("/{year}/tree")
def get_tree(year: str):
    """返回该年 analysis 目录树（不存在时返回空树并自动建目录）。"""
    root = _analysis_root(year)
    root.mkdir(parents=True, exist_ok=True)
    return {"year": year, "tree": _build_tree(root)}


@router.get("/{year}/file")
def read_file(year: str, path: str):
    f = _safe_path(year, path)
    if not f.exists() or not f.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if f.suffix.lower() != ".md":
        raise HTTPException(status_code=422, detail="仅支持 .md 文件")
    return {
        "path": path,
        "name": f.name,
        "content": f.read_text(encoding="utf-8"),
    }


class FilePayload(BaseModel):
    content: str = ""


@router.put("/{year}/file")
def save_file(year: str, path: str, payload: FilePayload):
    """保存（新建或覆盖）md 文件，父目录自动创建。"""
    f = _safe_path(year, path)
    if f.suffix.lower() != ".md":
        raise HTTPException(status_code=422, detail="仅支持 .md 文件")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(payload.content, encoding="utf-8")
    return {"path": path, "ok": True}


class NewItemPayload(BaseModel):
    path: str


@router.post("/{year}/folder")
def create_folder(year: str, payload: NewItemPayload):
    d = _safe_path(year, payload.path)
    if d.exists():
        raise HTTPException(status_code=409, detail="文件夹已存在")
    d.mkdir(parents=True)
    return {"path": payload.path, "ok": True}


@router.delete("/{year}")
def delete_item(year: str, path: str):
    """删除文件或空文件夹。"""
    target = _safe_path(year, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="目标不存在")
    if target.is_dir():
        try:
            target.rmdir()  # 仅允许删除空目录，防误删
        except OSError:
            raise HTTPException(status_code=409, detail="文件夹非空，请先删除其中文件")
    else:
        target.unlink()
    return {"ok": True}
