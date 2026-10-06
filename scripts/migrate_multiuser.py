#!/usr/bin/env python3
"""把「单用户版」的既有数据挂到多用户版的第一个管理员账号下。

★ 这是**一次性运维脚本**，不属于系统代码：
  - 不放在 backend/ 里，运行时代码不会 import 它；
  - 只做两件事：备份 → 把 workspaces/ 下的业务数据搬进 workspaces/users/u{uid}/，
    并为这些数据的主人建一个管理员账号。

执行前必须**停掉 MaWork 服务**（避免 SQLite WAL 未落盘导致数据不全）。

用法（在 Mawork/ 目录下）：
    python scripts/migrate_multiuser.py                # 交互确认后执行
    python scripts/migrate_multiuser.py --force        # 不询问直接执行
    python scripts/migrate_multiuser.py --dry-run      # 只演练，不动任何文件

可用环境变量指定管理员账号（不设则交互输入）：
    MAWORK_ADMIN_USER        用户名（默认 admin）
    MAWORK_ADMIN_PASSWORD    密码（默认沿用 mawork123，建议显式设置）
    MAWORK_ADMIN_PHONE       手机号（用于日后「同用户名+同手机号」自助改密）

幂等：已迁移过（存在 users.db 且有账号，或 users/u1 已存在）会直接跳过。
回滚：见执行结束时打印的命令，或把 backups/ 下的 zip 解开覆盖回 workspaces/。
"""

import argparse
import getpass
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 让脚本可以直接 `python scripts/migrate_multiuser.py` 跑（把 Mawork/ 加入搜索路径）
MAWORK_DIR = Path(__file__).resolve().parent.parent
if str(MAWORK_DIR) not in sys.path:
    sys.path.insert(0, str(MAWORK_DIR))

from backend import config, db  # noqa: E402
from backend.services import user as user_svc  # noqa: E402

BACKUP_DIR = MAWORK_DIR / "backups"
# 根目录里属于「全局」、不参与搬迁的条目
KEEP_IN_ROOT = {"users.db", "users", "backups"}
# 单用户时代躺在根目录的业务库
LEGACY_DBS = (
    "accounting.db", "planpool.db", "daily.db",
    "timer.db", "insight.db", "templates.db",
)


def _log(msg: str) -> None:
    print(msg, flush=True)


def _human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024
    return f"{size:.1f}GB"


def make_backup(src: Path) -> Path:
    """把整个 workspaces 打包到 backups/ 下，返回 zip 路径。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"workspaces_backup_{stamp}"
    archive = Path(shutil.make_archive(str(target), "zip", root_dir=src.parent, base_dir=src.name))
    _log(f"  备份完成：{archive}（{_human(archive.stat().st_size)}）")
    return archive


def legacy_leftovers() -> list[str]:
    """根目录里还没搬走的旧业务库。"""
    return [n for n in LEGACY_DBS if (config.WORKSPACES_DIR / n).exists()]


def has_marker() -> bool:
    """账号库里是否打过迁移标记。"""
    if not config.USERS_DB.exists():
        return False
    conn = db.get_conn(config.USERS_DB)
    try:
        return conn.execute(
            "SELECT 1 FROM user_meta WHERE key = 'migrated_from_single'"
        ).fetchone() is not None
    finally:
        conn.close()


def already_migrated() -> tuple[bool, str]:
    """幂等判断，返回 (是否已迁移, 原因)。

    注意：只看「有没有账号」是不够的——若服务在迁移前先启动过，
    会自动播种管理员并生成一套**空库**，此时根目录的旧数据还没搬。
    所以只要根目录仍有旧业务库，就一律判定为「未迁移」。
    """
    if has_marker():
        return True, "已存在迁移标记"
    left = legacy_leftovers()
    if left:
        return False, f"根目录仍有旧业务库：{', '.join(left)}"
    if config.USERS_DB.exists() and user_svc.count_users() > 0:
        return True, "账号库已有账号，且根目录无遗留业务库"
    return False, ""


def ask_admin() -> tuple[str, str, str]:
    """确定管理员账号：环境变量优先，缺失则交互输入。"""
    username = (os.getenv("MAWORK_ADMIN_USER") or config.ADMIN_USERNAME or "admin").strip()
    password = os.getenv("MAWORK_ADMIN_PASSWORD") or ""
    phone = (os.getenv("MAWORK_ADMIN_PHONE") or "").strip()
    if not password:
        _log("未设置 MAWORK_ADMIN_PASSWORD，请为管理员设置登录密码：")
        password = getpass.getpass("  密码（至少 8 位）：").strip()
        if password != getpass.getpass("  再输一次：").strip():
            _log("两次输入不一致，已取消")
            sys.exit(1)
    if not phone:
        phone = input("  手机号（选填，用于日后自助改密，直接回车跳过）：").strip()
    return username, password, phone


def resolve_owner(username: str, password: str, phone: str) -> tuple[int, bool]:
    """确定「既有数据的归属人」，返回 (uid, 是否新建)。

    若服务在迁移前启动过并已播种管理员，则复用该账号（不改其密码），
    避免造出两个管理员、把数据挂到空账号上。
    """
    conn = db.get_conn(config.USERS_DB)
    try:
        row = conn.execute("SELECT * FROM users ORDER BY id LIMIT 1").fetchone()
        if row is not None:
            return int(row["id"]), False
        pwd_hash, salt, iters = user_svc.new_secret(password)
        cur = conn.execute(
            "INSERT INTO users (username, phone, pwd_hash, salt, pwd_iter, role, "
            "status, display_name) VALUES (?, ?, ?, ?, ?, 'admin', 'active', ?)",
            (username, phone, pwd_hash, salt, iters, username),
        )
        conn.commit()
        return int(cur.lastrowid), True
    finally:
        conn.close()


def move_into_user_dir(uid: int, dry: bool) -> list[str]:
    """把根目录下的业务数据搬进 users/u{uid}/，返回搬迁条目名。"""
    dest = config.user_dir(uid)
    moved: list[str] = []
    if dry:
        dest = dest  # 仅展示
    else:
        dest.mkdir(parents=True, exist_ok=True)

    for item in sorted(config.WORKSPACES_DIR.iterdir()):
        if item.name in KEEP_IN_ROOT:
            continue
        target = dest / item.name
        if target.exists():
            is_db = item.name in LEGACY_DBS or item.name.endswith(("-wal", "-shm", "-journal"))
            if is_db:
                # 目标多半是服务预先建的空库，以根目录的真实数据为准
                if not dry:
                    target.unlink() if target.is_file() else shutil.rmtree(target)
            else:
                # 非数据库条目：绝不覆盖，改名保留
                backup_name = f"{item.name}.pre-migrate-{datetime.now():%Y%m%d%H%M%S}"
                if not dry:
                    item.rename(config.WORKSPACES_DIR / backup_name)
                    _log(f"  ! 目标已存在，原条目改名为 {backup_name}，未覆盖")
                continue
        if not dry:
            shutil.move(str(item), str(target))
        moved.append(item.name)
    return moved


def main() -> int:
    ap = argparse.ArgumentParser(description="单用户数据 → 多用户（挂到首个管理员账号）")
    ap.add_argument("--force", action="store_true", help="跳过交互确认")
    ap.add_argument("--dry-run", action="store_true", help="只演练，不修改任何文件")
    args = ap.parse_args()

    ws = config.WORKSPACES_DIR
    _log("=" * 68)
    _log("MaWork 单用户 → 多用户 数据迁移")
    _log("=" * 68)
    _log(f"数据目录：{ws}")

    if not ws.exists():
        _log("workspaces 不存在，无需迁移（首次启动会自动初始化）。")
        return 0

    # 账号库可能还不存在，先建表（幂等），再判断是否需要迁移
    if not args.dry_run:
        db.init_global()
    elif not config.USERS_DB.exists():
        _log("（演练模式）users.db 尚不存在，将新建")

    done, why = already_migrated()
    if done:
        _log(f"\n检测到已完成迁移（{why}），无需重复执行。")
        return 0

    if args.dry_run:
        _log("\n[演练] 将要执行：")
        _log("  1) 备份 workspaces/ 到 backups/")
        _log("  2) 新建管理员账号并作为既有数据的归属人")
        _log("  3) 把根目录下的业务数据搬进 workspaces/users/u{uid}/")
        _log("  4) 对该用户跑一次建表/迁移，生成 .inited 标记")
        return 0

    if not args.force:
        _log("\n⚠️  请先确认 MaWork 服务已停止（数据库连接中会丢数据）。")
        ok = input("确认已停止并继续迁移？[y/N] ").strip().lower()
        if ok != "y":
            _log("已取消，未做任何改动。")
            return 0

    _log("\n[1/4] 备份")
    archive = make_backup(ws)

    _log("\n[2/4] 确定既有数据的归属人（管理员账号）")
    username, password, phone = ask_admin()
    uid, created = resolve_owner(username, password, phone)
    if created:
        _log(f"  已创建管理员：{username}（uid={uid}，手机号={phone or '未填'}）")
    else:
        row = user_svc.get_user(uid)
        _log(f"  复用已存在的账号：{row['username']}（uid={uid}），密码保持不变")

    _log("\n[3/4] 搬迁既有数据")
    moved = move_into_user_dir(uid, dry=False)
    if moved:
        for name in moved:
            _log(f"  已搬入 users/u{uid}/：{name}")
    else:
        _log("  根目录没有业务数据，仅为新账号初始化空数据空间")

    _log("\n[4/4] 对该用户建表 / 补迁移")
    db.init_user(uid)
    (config.user_dir(uid) / ".inited").write_text("ok", encoding="utf-8")
    conn = db.get_conn(config.USERS_DB)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO user_meta (key, value, updated_at) "
            "VALUES ('migrated_from_single', ?, datetime('now', 'localtime'))",
            (str(uid),),
        )
        conn.commit()
    finally:
        conn.close()
    _log("  完成")

    _log("\n" + "=" * 68)
    _log("迁移完成。现在启动服务，用上面的管理员账号登录，即可看到原有数据。")
    _log("其他人需用「用户名 + 手机号 + 密码」提交成员申请，由该管理员在")
    _log("「用户管理」中通过后才能登录。")
    _log("\n如需回滚：")
    _log(f"  1) 停止服务，删除 {ws}/users 与 {ws}/users.db")
    _log(f"  2) 把 {archive} 解开覆盖回 {ws.parent}/")
    _log("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
