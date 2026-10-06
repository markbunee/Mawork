"""SQLite 数据库连接与建表。

各业务模块（记账、日程等）各自维护建表 SQL 与独立数据库文件，
这里提供统一的连接与初始化入口。
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config, ctx

# 启动巡检中初始化失败的用户：{uid: 错误信息}。
# 由 init_db() 填充，/api/health 对外暴露，让「某个用户的库迁移到一半」
# 这类问题在运维巡检时就能发现，而不是等用户打开某页面报 500。
DB_INIT_ERRORS: dict[int, str] = {}


def get_conn(path: Path | None = None) -> sqlite3.Connection:
    """返回一个 SQLite 连接。

    path 缺省时使用记账库（config.DB_PATH）。
    自动建目录、开启外键与行工厂。
    """
    db_path = path or config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # —— 性能/健壮性 PRAGMA（对机器规格无感，必做）——
    # WAL：写不阻塞读、降低 2 核下写锁整库的雪崩风险；
    # busy_timeout：写冲突时等待而非立刻报错；
    # cache_size=-8000 约 8MB 页缓存；temp_store=MEMORY 排序/临时表走内存。
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA cache_size = -8000")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


@contextmanager
def open_conn(path: Path | None = None):
    """上下文管理器版 get_conn：自动关闭连接。

    各 service 原先到处写 `conn = get_conn(...); try: ... finally: conn.close()`，
    样板重复且容易漏关连接，统一收敛到这里。
    """
    conn = get_conn(path)
    try:
        yield conn
    finally:
        conn.close()


def init_global() -> None:
    """初始化全局库（账号库 users.db，不属于任何用户）。"""
    from .models.user import SCHEMA_SQL as user_sql

    conn = get_conn(config.USERS_DB)
    try:
        conn.executescript(user_sql)
        conn.commit()
    finally:
        conn.close()


def init_user(uid: int) -> None:
    """初始化**某个用户**的全部业务库（幂等）。

    uid **必填**且必须是真实用户 id：这里会临时切换 ctx 的用户上下文，
    让 config.X_DB 指向该用户目录。一旦允许 None，就会在「当前无用户上下文」
    的情况下建库，而 config.data_dir() 此时会退回 workspaces 根目录，
    于是凭空多出 workspaces/accounting.db 之类的错位文件，且不报错。
    """
    from .models.accounting import SCHEMA_SQL as accounting_sql
    from .models.planpool import SCHEMA_SQL as planpool_sql

    if uid is None:
        raise ValueError("init_user() 必须显式传入 uid，不允许在无用户上下文下建库")

    token = ctx.set_uid(uid)
    try:
        _init_user_dbs(accounting_sql, planpool_sql)
    finally:
        ctx.reset_uid(token)


def _init_user_dbs(accounting_sql: str, planpool_sql: str) -> None:
    # 记账库：config.DB_PATH
    conn = get_conn()
    try:
        conn.executescript(accounting_sql)
        _migrate_reimburse_events(conn)
        _migrate_accounting(conn)
        conn.commit()
    finally:
        conn.close()

    # 日程库：config.PLANPOOL_DB（任务表 + 日历文本格）
    from .models.calday import SCHEMA_SQL as calday_sql
    from .models.habit import SCHEMA_SQL as habit_sql

    conn = get_conn(config.PLANPOOL_DB)
    try:
        conn.executescript(planpool_sql)
        conn.executescript(calday_sql)
        conn.executescript(habit_sql)
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
        _migrate_timer(conn)
        conn.commit()
    finally:
        conn.close()

    # 洞察库：config.INSIGHT_DB（目标 KPI）
    from .models.insight import SCHEMA_SQL as insight_sql

    conn = get_conn(config.INSIGHT_DB)
    try:
        conn.executescript(insight_sql)
        conn.commit()
    finally:
        conn.close()

    # 模板库：config.TEMPLATES_DB（横切能力 E3：日报/周报/月报/任务表统一模板）
    from .models.template import SCHEMA_SQL as template_sql
    from .services.template import seed_templates

    conn = get_conn(config.TEMPLATES_DB)
    try:
        conn.executescript(template_sql)
        seed_templates(conn)
        conn.commit()
    finally:
        conn.close()

    # 文章库：config.ARTICLES_DB（Markdown 文章，每篇一条记录，按 year/date 组织）
    from .models.articles import SCHEMA_SQL as articles_sql

    conn = get_conn(config.ARTICLES_DB)
    try:
        conn.executescript(articles_sql)
        # 迁移：移除已弃用的 archived 列（文章归档功能已下线）
        cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
        if "archived" in cols:
            # DROP COLUMN 需要 SQLite >= 3.35。旧版本必须容错——本函数也在请求
            # 链路（init_current → 备份恢复）执行，抛错会直接变成 500。
            try:
                conn.execute("ALTER TABLE articles DROP COLUMN archived")
            except sqlite3.OperationalError:
                pass  # 旧版本 SQLite：保留该列，不影响读写
        conn.commit()
    finally:
        conn.close()


def init_current() -> None:
    """初始化**当前上下文用户**的业务库（请求内按需调用）。"""
    from .models.accounting import SCHEMA_SQL as accounting_sql
    from .models.planpool import SCHEMA_SQL as planpool_sql

    # 同样要防「无用户上下文」：此时建库会落到 workspaces 根目录。
    # 与 init_user 不同，这里语义上就是当前用户，因此显式要求 ctx 已绑定。
    if config.MULTI_USER and ctx.current_uid() is None:
        raise RuntimeError("init_current() 在未绑定用户的上下文中被调用，拒绝建库")
    _init_user_dbs(accounting_sql, planpool_sql)


def init_db() -> None:
    """启动入口：全局账号库 → 播种首个管理员 → 逐个用户巡检业务库。

    逐个巡检的意义：日后新增表/列的迁移，升级后重启一次就会对所有人生效，
    不需要每个用户登录触发。

    巡检范围取「账号表里的 uid」∪「磁盘上已存在的 u* 目录」：
    只认账号表会漏掉孤儿目录（账号被删但目录残留、或目录先于账号建立），
    这些目录将永远拿不到 schema 迁移。
    """
    init_global()

    from .scope import each_user_dir
    from .services.user import ensure_admin_seeded, list_uids

    ensure_admin_seeded()

    uids = set(list_uids())
    uids.update(uid for uid, _ in each_user_dir())

    for uid in sorted(uids):
        try:
            init_user(uid)
        except Exception as e:  # 单个用户损坏不影响其它人启动
            DB_INIT_ERRORS[uid] = f"{type(e).__name__}: {e}"
            logging.getLogger("mawork").error(
                "用户 u%s 数据初始化失败（其业务库可能处于半迁移状态，"
                "相关页面会报错）：%s", uid, e, exc_info=True,
            )

    if DB_INIT_ERRORS:
        # 集中汇总一次：逐行 warning 容易被淹没，且「半迁移」问题必须显眼。
        # 同时由 /api/health 暴露，便于运维主动巡检。
        logging.getLogger("mawork").error(
            "⚠️ 有 %d 个用户数据初始化失败：%s。请检查其库文件，"
            "必要时先备份再删除对应 .db 让其按新 schema 重建。",
            len(DB_INIT_ERRORS),
            ", ".join(f"u{u}({msg})" for u, msg in sorted(DB_INIT_ERRORS.items())),
        )
    else:
        logging.getLogger("mawork").info("所有用户数据初始化完成（%d 个）", len(uids))


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


def _migrate_accounting(conn: sqlite3.Connection) -> None:
    """记账表结构迁移（幂等）：

    1. transactions 增加 category2 列（二级分类，旧数据为空）
    2. 把旧的 account_settings（deposit / saving 两个数字）迁移为 accounts 多账户
    """
    # 1) category2 列
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(transactions)").fetchall()}
    if "category2" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN category2 TEXT DEFAULT ''")

    # 2) deposit / saving → accounts
    #    以 migrated_accounts 标记位为准，**不能只看 accounts 是否为空**：
    #    否则用户手动删光全部账户后，下次启动会被旧设置「复活」出账户。
    migrated = conn.execute(
        "SELECT 1 FROM account_settings WHERE key = 'migrated_accounts'"
    ).fetchone()
    if not migrated:
        rows = conn.execute(
            "SELECT key, value FROM account_settings WHERE key IN ('deposit', 'saving')"
        ).fetchall()
        if rows:
            # deposit（存款）→ 储蓄账户；saving（储蓄）→ 活期账户，语义上都是期初余额
            mapping = {"deposit": ("储蓄账户", "other"), "saving": ("活期账户", "cash")}
            for r in rows:
                name, atype = mapping.get(r["key"], (r["key"], "other"))
                cents = int(r["value"]) if r["value"] else 0
                conn.execute(
                    "INSERT INTO accounts (name, type, balance) VALUES (?, ?, ?)",
                    (name, atype, cents),
                )
        # 无论是否有旧数据都要打标记：迁移只应发生一次
        conn.execute(
            "INSERT OR REPLACE INTO account_settings (key, value, updated_at) "
            "VALUES ('migrated_accounts', '1', datetime('now', 'localtime'))"
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

    # 灵活列种子（内置列 + 系统模板），幂等
    from .services.planpool import _seed_columns

    _seed_columns(conn)


def _migrate_timer(conn: sqlite3.Connection) -> None:
    """计时表结构迁移（幂等）：补 source_type / source_ref 两列（日程↔计时联动用）。"""
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(timers)").fetchall()}
    if "source_type" not in cols:
        conn.execute("ALTER TABLE timers ADD COLUMN source_type TEXT NOT NULL DEFAULT ''")
    if "source_ref" not in cols:
        conn.execute("ALTER TABLE timers ADD COLUMN source_ref TEXT NOT NULL DEFAULT ''")


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
    # 废弃表 calendar_sync 只删一次：破坏性 DDL 不该每次启动都重复执行。
    # 「表还在才删」本身就是一次性守卫（删掉后后续启动不再命中），
    # 无需额外标记位——注意 account_settings 只存在于记账库，本连接是 planpool 库。
    present = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='calendar_sync'"
    ).fetchone()
    if present:
        conn.execute("DROP TABLE calendar_sync")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_calday_src "
        "ON calendar_lines(date, source, source_ref)"
    )
