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
REIMBURSE_STATUSES = ["待报销"]  # 报销账目只有「待报销」；已报销通过 reimburse_events 事件表表达

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

-- 报销事件：每笔「待报销」的到账记录（支持部分报销、多次报销、可追溯）
CREATE TABLE IF NOT EXISTS reimburse_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_id       INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    amount      INTEGER NOT NULL,              -- 本次报销到账金额，单位：分
    event_date  TEXT    NOT NULL,              -- 报销到账日期 YYYY-MM-DD
    note        TEXT    DEFAULT '',            -- 备注
    created_at  TEXT    DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_reimburse_events_tx ON reimburse_events(tx_id);
CREATE INDEX IF NOT EXISTS idx_reimburse_events_date ON reimburse_events(event_date);

-- 全局设置：存款 / 储蓄（value 单位：分，与 transactions 一致）
CREATE TABLE IF NOT EXISTS account_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT DEFAULT (datetime('now', 'localtime'))
);
"""
