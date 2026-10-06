"""记账领域模型：分类常量与建表 SQL。

账目类型（kind）：
- expense  支出
- income   收入
- reimburse 报销

金额一律以「分」为整数存储，前端展示时除以 100。

分类采用「一级 + 二级」两级结构（见 CATEGORY_TREE）：
- `category`   一级分类（如 餐饮 / 交通 / 居住）
- `category2`  二级分类（如 午饭 / 打车 / 房租），可为空以兼容历史数据
"""

# ---------------------------------------------------------------------------
# 两级分类树
# ---------------------------------------------------------------------------
CATEGORY_TREE: dict[str, dict[str, list[str]]] = {
    "expense": {
        "餐饮": ["早饭", "午饭", "晚饭", "聚餐", "咖啡奶茶", "外卖", "零食"],
        "交通": ["公交地铁", "打车", "加油", "高铁机票", "停车"],
        "居住": ["房租", "水电燃气", "物业", "家居", "维修"],
        "购物": ["服饰", "数码", "日用", "美妆", "其他购物"],
        "学习": ["书籍", "课程", "软件订阅", "考试"],
        "医疗": ["门诊", "药品", "体检", "保险"],
        "娱乐": ["电影演出", "游戏", "旅行", "运动"],
        "人情": ["礼金", "红包", "社交"],
        "其他": ["其他支出"],
    },
    "income": {
        "职业收入": ["工资", "奖金", "补贴", "兼职"],
        "投资回报": ["利息", "分红", "理财", "基金"],
        "项目收入": ["项目结算", "稿费", "外包"],
        "其他收入": ["退款", "红包", "其他"],
    },
    "reimburse": {
        "待报销": ["待报销"],
    },
}

# 账目类型 → 展示名
KIND_LABELS = {
    "expense": "支出",
    "income": "收入",
    "reimburse": "报销",
}

# 各类型的一级分类（保持与旧代码兼容的 CATEGORIES 形态）
CATEGORIES = {k: list(v.keys()) for k, v in CATEGORY_TREE.items()}

# 各类型的一级 → 二级 映射（二级可为空）
CATEGORY2 = {k: v for k, v in CATEGORY_TREE.items()}

# 报销状态：报销已「事件化」（reimburse_events 记录每笔到账），
# 交易自身不再有「已报销」这一分类，故只剩「待报销」一种状态。
REIMBURSE_STATUSES = ["待报销"]


# ---------------------------------------------------------------------------
# 资产账户类型
# ---------------------------------------------------------------------------
ACCOUNT_TYPES = {
    "cash": "现金",
    "bank": "银行卡",
    "alipay": "支付宝",
    "wechat": "微信",
    "other": "其他",
}


# ---------------------------------------------------------------------------
# 建表 SQL
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,              -- expense / income / reimburse
    category    TEXT    NOT NULL,              -- 一级分类
    category2   TEXT    DEFAULT '',            -- 二级分类（可为空，兼容历史数据）
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

-- 资产账户（取代旧的 deposit / saving 两个数字，支持多账户资产负债表）
CREATE TABLE IF NOT EXISTS accounts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL,
    type    TEXT    NOT NULL DEFAULT 'cash',   -- cash / bank / alipay / wechat / other
    balance INTEGER NOT NULL DEFAULT 0         -- 账户余额，单位：分
);

-- 预算：period 为 YYYY-MM，scope = total（总预算）或 category（按一级分类）
CREATE TABLE IF NOT EXISTS budgets (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    period   TEXT    NOT NULL,                 -- YYYY-MM
    scope    TEXT    NOT NULL DEFAULT 'total', -- total / category
    category TEXT    DEFAULT '',               -- scope=category 时的一级分类
    limit_cents INTEGER NOT NULL               -- 预算上限，单位：分
);

CREATE INDEX IF NOT EXISTS idx_budgets_period ON budgets(period);

-- 周期账模板（房租 / 订阅 / 工资 等，可一键生成本月交易）
CREATE TABLE IF NOT EXISTS recurring (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT    NOT NULL,
    category     TEXT    NOT NULL,
    category2    TEXT    DEFAULT '',
    amount       REAL,                          -- 固定金额（元），为空表示每次手动填
    note         TEXT    DEFAULT '',
    freq         TEXT    NOT NULL DEFAULT 'monthly',  -- monthly / weekly
    day_of_month INTEGER DEFAULT 1,            -- 每月几号（monthly）
    account      TEXT    DEFAULT '',           -- 关联账户名（可选）
    active       INTEGER NOT NULL DEFAULT 1,
    last_applied TEXT    DEFAULT ''            -- 最近一次应用的 YYYY-MM
);

-- 全局设置：保留 deposit / saving 列仅用于一次性迁移到 accounts（迁移后弃用）
CREATE TABLE IF NOT EXISTS account_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT DEFAULT (datetime('now', 'localtime'))
);
"""
