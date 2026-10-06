"""横切能力（search / reminder / tag）共用的小工具。

抽出来的原因：这几个 service 都在做「跨模块扫描 → 扁平条目 → 按模块分组」，
分组逻辑一模一样，散落三处不利于维护。
"""

MODULE_KEY = "module"
LABEL_KEY = "module_label"


def group_by_module(items: list[dict]) -> list[dict]:
    """把扁平条目按 module 分组，保持首次出现的顺序。

    每项需含 `module` 与 `module_label` 两个键。
    返回 [{"module": ..., "module_label": ..., "items": [...]}]。
    """
    grouped: dict[str, list[dict]] = {}
    for it in items:
        grouped.setdefault(it[MODULE_KEY], []).append(it)
    return [
        {
            MODULE_KEY: module,
            LABEL_KEY: entries[0][LABEL_KEY],
            "items": entries,
        }
        for module, entries in grouped.items()
    ]
