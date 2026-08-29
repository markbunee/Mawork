"""SQLite 数据库连接与建表。

各业务模块（记账、日程等）各自维护建表 SQL 与独立数据库文件，
这里提供统一的连接与初始化入口。
"""

import sqlite3
from pathlib import Path

from . import config


def get_conn(path: Path | None = None) -> sqlite3.Connection:
    """返回一个 SQLite 连接。

    path 缺省时使用记账库（config.DB_PATH）。
    自动建目录、开启外键与行工厂。
    """
    db_path = path or config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """初始化所有业务模块的表（幂等）。"""
    from .models.accounting import SCHEMA_SQL as accounting_sql
    from .models.planpool import SCHEMA_SQL as planpool_sql

    # 记账库：config.DB_PATH
    conn = get_conn()
    try:
        conn.executescript(accounting_sql)
        conn.commit()
    finally:
        conn.close()

    # 日程库：config.PLANPOOL_DB
    conn = get_conn(config.PLANPOOL_DB)
    try:
        conn.executescript(planpool_sql)
        conn.commit()
    finally:
        conn.close()
