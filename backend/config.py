"""MaWork 后端配置：路径与常量。"""

from pathlib import Path

# Mawork/ 目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录：Mawork/workspaces/
WORKSPACES_DIR = BASE_DIR / "workspaces"

# SQLite 数据库文件
ACCOUNTING_DB = WORKSPACES_DIR / "accounting.db"   # 记账
PLANPOOL_DB = WORKSPACES_DIR / "planpool.db"       # 日程任务

# 兼容旧引用：config.DB_PATH 仍指向记账库
DB_PATH = ACCOUNTING_DB

# 日报作者
AUTHOR = "马炫轩"
