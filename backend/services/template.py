"""模板库业务逻辑（横切能力 E3）：内置种子 + 用户自建模板的增删改查。

数据落在 config.TEMPLATES_DB（templates.db），与业务模块解耦。
内置模板（builtin=1）不可删除，避免误删种子后无法恢复。
"""

import sqlite3

from .. import config, db
from ..models.template import DEFAULT_SCOPE, PRESET_TEMPLATES, SCOPES


def _get_conn() -> sqlite3.Connection:
    return db.get_conn(config.TEMPLATES_DB)


def seed_templates(conn: sqlite3.Connection) -> None:
    """幂等：模板表为空时写入内置模板。"""
    n = conn.execute("SELECT COUNT(*) AS n FROM templates").fetchone()["n"]
    if n:
        return
    for scope, name, content in PRESET_TEMPLATES:
        conn.execute(
            "INSERT INTO templates (scope, name, content, builtin) VALUES (?, ?, ?, 1)",
            (scope, name, content),
        )


def _norm_scope(scope: str) -> str:
    s = (scope or "").strip()
    return s if s in SCOPES else DEFAULT_SCOPE


def list_templates(scope: str | None = None) -> list[dict]:
    """模板列表；不传 scope 则返回全部（按 scope 分组前排序）。"""
    conn = _get_conn()
    try:
        seed_templates(conn)
        conn.commit()
        if scope:
            rows = conn.execute(
                "SELECT * FROM templates WHERE scope = ? ORDER BY builtin DESC, id",
                (_norm_scope(scope),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM templates ORDER BY scope, builtin DESC, id"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_template(tid: int) -> dict | None:
    conn = _get_conn()
    try:
        r = conn.execute("SELECT * FROM templates WHERE id = ?", (tid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def create_template(scope: str, name: str, content: str = "") -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("模板名不能为空")
    conn = _get_conn()
    try:
        seed_templates(conn)
        cur = conn.execute(
            "INSERT INTO templates (scope, name, content, builtin) VALUES (?, ?, ?, 0)",
            (_norm_scope(scope), name, content or ""),
        )
        conn.commit()
        r = conn.execute("SELECT * FROM templates WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(r)
    finally:
        conn.close()


def update_template(tid: int, name: str | None = None, content: str | None = None) -> dict | None:
    sets: dict[str, object] = {}
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("模板名不能为空")
        sets["name"] = name
    if content is not None:
        sets["content"] = content
    if not sets:
        return get_template(tid)
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE templates SET " + ", ".join(f"{k} = ?" for k in sets) + " WHERE id = ?",
            (*sets.values(), tid),
        )
        if cur.rowcount == 0:
            return None
        conn.commit()
        return get_template(tid)
    finally:
        conn.close()


def delete_template(tid: int) -> bool:
    """删除用户自建模板；内置模板不可删除。"""
    t = get_template(tid)
    if t is None:
        return False
    if t["builtin"]:
        raise ValueError("内置模板不可删除")
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM templates WHERE id = ?", (tid,))
        conn.commit()
        return True
    finally:
        conn.close()
