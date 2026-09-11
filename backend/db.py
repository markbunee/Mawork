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
        _migrate_reimburse_events(conn)
        conn.commit()
    finally:
        conn.close()

    # 日程库：config.PLANPOOL_DB（任务表 + 日历文本格）
    from .models.calday import SCHEMA_SQL as calday_sql

    conn = get_conn(config.PLANPOOL_DB)
    try:
        conn.executescript(planpool_sql)
        conn.executescript(calday_sql)
        _migrate_planpool(conn)
        _migrate_calday(conn)
        conn.commit()
    finally:
        conn.close()

    # 日报库：config.DAILY_DB
    from .models.daily import SCHEMA_SQL as daily_sql
    from .services.daily import import_legacy_md

    conn = get_conn(config.DAILY_DB)
    try:
        conn.executescript(daily_sql)
        conn.commit()
    finally:
        conn.close()

    # 存量 Markdown 一次性导入（幂等）
    import_legacy_md()

    # 计时库：config.TIMER_DB（倒计时/正计时/倒数日/正数日 + 耗时日志）
    from .models.timer import SCHEMA_SQL as timer_sql

    conn = get_conn(config.TIMER_DB)
    try:
        conn.executescript(timer_sql)
        conn.commit()
    finally:
        conn.close()


def _migrate_reimburse_events(conn: sqlite3.Connection) -> None:
    """一次性迁移：报销从「覆盖状态」改为「事件化」。

    旧模型里「已报销」是通过覆盖 category 表达；新模型由 reimburse_events 表
    记录每一次到账。迁移把存量「已报销」记录按其原金额、原日期生成一条事件，
    记录本身改回「待报销」。幂等：以 account_settings 标记位控制。
    """
    mark = conn.execute(
        "SELECT 1 FROM account_settings WHERE key = 'migrated_reimburse_events'"
    ).fetchone()
    if mark:
        return
    conn.execute(
        """
        INSERT INTO reimburse_events (tx_id, amount, event_date, note, created_at)
        SELECT id, amount, date, COALESCE(note, '') || '（历史已报销）', created_at
        FROM transactions
        WHERE kind = 'reimburse' AND category = '已报销'
        """
    )
    conn.execute(
        "UPDATE transactions SET category = '待报销' WHERE kind = 'reimburse' AND category = '已报销'"
    )
    conn.execute(
        "INSERT INTO account_settings (key, value, updated_at) "
        "VALUES ('migrated_reimburse_events', '1', datetime('now', 'localtime'))"
    )


def _migrate_planpool(conn: sqlite3.Connection) -> None:
    """日程任务表结构迁移（幂等）：扁平化为「一级计划 + 任务名 + 手动完成度」。

    1. level2 -> title（原二级计划即现在的任务名）
    2. 删除 plan_type（日 / 周 / 月度计划类型，改由日历的月 / 周计划承担）
    3. 恢复 level1（一级计划，作为分类列；曾随扁平化一并删除，现只恢复列、
       不恢复历史数据，存量任务的一级计划留空由用户补填）
    4. 新增 completion 列（用户手填的完成度）
    """
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if not cols:
        return

    if "title" not in cols and "level2" in cols:
        conn.execute("ALTER TABLE tasks RENAME COLUMN level2 TO title")
        cols.discard("level2")
        cols.add("title")

    # 历史遗留列清理：只删 plan_type（日 / 周 / 月度计划类型）
    conn.execute("DROP INDEX IF EXISTS idx_tasks_level1")
    if "plan_type" in cols:
        try:
            conn.execute("ALTER TABLE tasks DROP COLUMN plan_type")
        except sqlite3.OperationalError:
            # 旧版本 SQLite 不支持 DROP COLUMN：保留列，不影响读写
            pass

    # 恢复「一级计划」列（扁平化时删过，现在作为分类列加回来）
    if "level1" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN level1 TEXT NOT NULL DEFAULT ''")
        cols.add("level1")

    if "completion" not in cols:
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN completion INTEGER NOT NULL DEFAULT 0"
        )

    # 旧四态（完成 / 未完成 / 进行中 / 搁置）收敛为三态（未完成 / 进行中 / 已完成）
    conn.execute("UPDATE tasks SET progress = '已完成' WHERE progress = '完成'")
    conn.execute("UPDATE tasks SET progress = '未完成' WHERE progress = '搁置'")


def _migrate_calday(conn: sqlite3.Connection) -> None:
    """日历文本格迁移（幂等）：加来源标记，废弃旧的 md 幂等表。

    - source / source_ref：区分「用户手写行」与「由日报明日计划自动写入的行」；
    - calendar_sync：以前记录写入日报 Markdown 的渲染缓存，日报入库后不再需要。
    """
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(calendar_lines)").fetchall()}
    if not cols:
        return
    if "source" not in cols:
        conn.execute(
            "ALTER TABLE calendar_lines ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
        )
    if "source_ref" not in cols:
        conn.execute(
            "ALTER TABLE calendar_lines ADD COLUMN source_ref TEXT NOT NULL DEFAULT ''"
        )
    conn.execute("DROP TABLE IF EXISTS calendar_sync")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_calday_src "
        "ON calendar_lines(date, source, source_ref)"
    )
