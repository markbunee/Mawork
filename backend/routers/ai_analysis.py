"""AI 报告分析路由：读写 workspaces/users/u{uid}/analysis/ 下的 Markdown 报告。

目录约定：
- 每个用户的数据目录下有 analysis/ 目录，支持任意层级子文件夹
- 仅允许读写 .md 文件
- 所有 path 参数为相对 analysis/ 的路径，禁止路径穿越
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# 目录树递归深度上限（与 resources 树的同名常量同一思路）：
# 目录可被用户逐层创建，不设上限则深层目录会触发 RecursionError。
MAX_TREE_DEPTH = 8


def _analysis_root() -> Path:
    """当前用户的报告库目录：{用户数据目录}/analysis。"""
    return config.data_dir() / "analysis"


def _safe_path(rel: str) -> Path:
    """将相对路径解析为 analysis 下的安全绝对路径，防路径穿越。"""
    rel = (rel or "").strip().lstrip("/").replace("\\", "/")
    if not rel:
        raise HTTPException(status_code=422, detail="path 不能为空")
    root = _analysis_root().resolve()
    target = (root / rel).resolve()
    # 目标必须严格位于 analysis 之内（等于根目录也视为非法）
    if target == root or root not in target.parents:
        raise HTTPException(status_code=422, detail="非法路径")
    return target


def _build_tree(root: Path, base: Path | None = None, depth: int = 0) -> list[dict]:
    """递归构建目录树：[{name, path, type: dir|file, children?}]

    path 始终相对于 analysis 根目录（base），保证前端可直接用 path 读写文件。

    depth 上限：用户可自建任意深目录（POST /folder 允许逐层创建），
    无上限递归会在上百层时触发 RecursionError → 整个树接口 500。
    超过上限就当作叶子返回，与 resources 树的 MAX_TREE_DEPTH 同一思路。
    """
    base = base or root
    items = []
    if not root.exists() or depth >= MAX_TREE_DEPTH:
        return items
    for p in sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name)):
        rel = p.relative_to(base)
        if p.is_dir():
            items.append({
                "name": p.name,
                "path": str(rel).replace("\\", "/"),
                "type": "dir",
                "children": _build_tree(p, base, depth + 1),
            })
        elif p.suffix.lower() == ".md":
            try:
                st = p.stat()
            except OSError:
                continue  # 断裂软链 / 刚被删除，跳过而不是让整棵树 500
            items.append({
                "name": p.name,
                "path": str(rel).replace("\\", "/"),
                "type": "file",
                "size": st.st_size,
                "mtime": st.st_mtime,
            })
    return items


@router.get("/tree")
def get_tree():
    """返回 analysis 目录树（不存在时返回空树并自动建目录）。"""
    root = _analysis_root()
    root.mkdir(parents=True, exist_ok=True)
    return {"tree": _build_tree(root)}


@router.get("/file")
def read_file(path: str):
    f = _safe_path(path)
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


@router.put("/file")
def save_file(path: str, payload: FilePayload):
    """保存（新建或覆盖）md 文件，父目录自动创建。"""
    f = _safe_path(path)
    if f.suffix.lower() != ".md":
        raise HTTPException(status_code=422, detail="仅支持 .md 文件")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(payload.content, encoding="utf-8")
    return {"path": path, "ok": True}


class NewItemPayload(BaseModel):
    path: str


@router.post("/folder")
def create_folder(payload: NewItemPayload):
    d = _safe_path(payload.path)
    if d.exists():
        raise HTTPException(status_code=409, detail="文件夹已存在")
    d.mkdir(parents=True)
    return {"path": payload.path, "ok": True}


@router.delete("/item")
def delete_item(path: str):
    """删除文件或空文件夹。"""
    target = _safe_path(path)
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
