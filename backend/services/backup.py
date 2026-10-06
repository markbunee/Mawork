"""横切能力 E5：数据导出 / 备份与恢复。

设计要点：
- **按库整表导出**：不写死表名，从 sqlite_master 动态枚举，避免漏表/漏列；
- **导入容错**：目标表不存在则跳过；只写入两表共有的列（字段对齐），
  兼容历史备份与当前 schema 的差异；
- **语义**：导入为「覆盖恢复」——对备份中出现的表先清空再写入，
  备份里没有的表保持原样，避免误删用户数据；
- 只覆盖 SQLite 数据，不含 workspaces 下的资料文件（文件即数据，随目录备份）。
"""

import logging
from datetime import datetime
from pathlib import Path

from .. import config, db

BACKUP_VERSION = 1


def _module_paths() -> dict[str, Path]:
    """每次调用时解析，便于临时库测试与运行期换库。"""
    return {
        "accounting": config.ACCOUNTING_DB,
        "planpool": config.PLANPOOL_DB,
        "daily": config.DAILY_DB,
        "timer": config.TIMER_DB,
        "insight": config.INSIGHT_DB,
        "templates": config.TEMPLATES_DB,
    }


def _table_names(conn) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def _dump_db(db_path: Path) -> dict[str, list]:
    """导出单个库：表名 -> 行列表。"""
    with db.open_conn(db_path) as conn:
        out: dict[str, list] = {}
        for t in _table_names(conn):
            rows = conn.execute(f'SELECT * FROM "{t}"').fetchall()
            out[t] = [dict(r) for r in rows]
        return out


def export_all() -> dict:
    """全量导出：各模块所有库的所有表。

    失败的模块**不会静默消失**：既在 errors 里点名，也记 warning。
    否则用户拿到一份「看着完整」的残缺备份，灾备时才发现缺数据，
    那就等于没有备份。
    """
    modules: dict[str, dict] = {}
    counts: dict[str, int] = {}
    errors: dict[str, str] = {}
    for name, path in _module_paths().items():
        if not path.exists():
            errors[name] = "库文件不存在"
            continue
        try:
            data = _dump_db(path)
        except Exception as e:
            errors[name] = f"{type(e).__name__}: {e}"
            logging.getLogger("mawork").warning("导出备份时模块 %s 失败：%s", name, e)
            continue
        modules[name] = data
        counts[name] = sum(len(v) for v in data.values())
    result = {
        "version": BACKUP_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "counts": counts,
        "modules": modules,
    }
    if errors:
        result["errors"] = errors
    return result


def _restore_db(db_path: Path, tables: dict) -> dict[str, int]:
    """把备份里的表写回目标库（覆盖：先清空该表再写入）。

    安全：表名**只接受目标库中真实存在的表**（白名单来自 sqlite_master），
    绝不把上传内容里的字符串直接拼进 SQL 标识符。
    """
    with db.open_conn(db_path) as conn:
        allowed = set(_table_names(conn))
        stats: dict[str, int] = {}
        for tname, rows in tables.items():
            if not isinstance(tname, str) or tname not in allowed:
                continue  # 目标库无此表 / 非法表名，跳过
            if not isinstance(rows, list):
                continue
            cols = {c["name"] for c in conn.execute(f'PRAGMA table_info("{tname}")').fetchall()}
            if not cols:
                continue
            conn.execute(f'DELETE FROM "{tname}"')
            n = 0
            for r in rows:
                if not isinstance(r, dict):
                    continue
                item = {k: v for k, v in r.items() if k in cols}
                if not item:
                    continue
                keys = ", ".join(f'"{k}"' for k in item)
                ph = ", ".join("?" for _ in item)
                conn.execute(
                    f'INSERT INTO "{tname}" ({keys}) VALUES ({ph})',
                    tuple(item.values()),
                )
                n += 1
            stats[tname] = n
        conn.commit()
        return stats


def import_all(payload: dict) -> dict:
    """从备份恢复。返回各模块各表写入行数。"""
    if not isinstance(payload, dict):
        raise ValueError("备份内容格式不正确")
    modules = payload.get("modules")
    if not isinstance(modules, dict):
        raise ValueError("备份内容缺少 modules 字段")

    # 确保当前用户的库与表都存在（只初始化自己的，不触碰别人）
    db.init_current()

    report: dict[str, dict[str, int]] = {}
    errors: dict[str, str] = {}
    for name, path in _module_paths().items():
        data = modules.get(name)
        if not isinstance(data, dict):
            continue
        try:
            report[name] = _restore_db(path, data)
        except Exception as e:  # 单模块失败不中断其余，但必须如实上报
            errors[name] = str(e)
    if errors:
        # 部分模块失败时不能报 ok，避免调用方误以为已完整恢复
        raise RuntimeError("部分模块恢复失败：" + "；".join(f"{k}: {v}" for k, v in errors.items()))
    return {"ok": True, "restored": report}
