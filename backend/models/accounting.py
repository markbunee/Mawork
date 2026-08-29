"""记账领域模型：分类常量与建表 SQL。

账目类型（kind）：
- expense  支出
- income   收入
- reimburse 报销

金额一律以「分」为整数存储，前端展示时除以 100。
"""

# ---------------------------------------------------------------------------
# 分类常量
# ---------------------------------------------------------------------------
EXPENSE_CATEGORIES = ["餐饮", "购物", "交通", "住宿", "发展", "医疗", "家庭"]
INCOME_CATEGORIES = ["职业收入", "投资回报", "项目收入"]
REIMBURSE_STATUSES = ["待报销", "已报销"]

# 账目类型 → 展示名
KIND_LABELS = {
    "expense": "支出",
    "income": "收入",
    "reimburse": "报销",
}

# 各类型的子分类
CATEGORIES = {
    "expense": EXPENSE_CATEGORIES,
    "income": INCOME_CATEGORIES,
    "reimburse": REIMBURSE_STATUSES,
}


# ---------------------------------------------------------------------------
# 建表 SQL
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,              -- expense / income / reimburse
    category    TEXT    NOT NULL,              -- 子分类（报销时为 待报销/已报销）
    amount      INTEGER NOT NULL,              -- 金额，单位：分
    note        TEXT    DEFAULT '',            -- 说明
    date        TEXT    NOT NULL,              -- YYYY-MM-DD
    created_at  TEXT    DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_kind ON transactions(kind);
"""
