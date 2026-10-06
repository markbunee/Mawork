"""数据导出 / 恢复路由（受保护）。

只保留**表级 JSON 导出 / 导入**这一对能力：把各业务库的表数据导成一个
JSON 文件，便于换机迁移或灾难恢复。

原先这里还有一整套「整目录 zip 打包上传/下载 + 自动快照 + 一键回滚」，
现已全部下线——整目录打包对个人自用场景收益低、风险高（一个嵌套目录
就会让上传静默失效），而自动快照在文件级操作下要为每个文件拷几十 MB。
文件级的增删改查请走「知识 · 文件」页（`/api/resources/*`）。

安全：一律要求有效 Bearer 令牌；表名只取目标库中真实存在的表
（白名单来自 sqlite_master），绝不把上传内容里的字符串拼进 SQL 标识符。
"""

from fastapi import APIRouter, HTTPException

from ..services import backup as svc

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/export")
def export():
    """全量导出：返回包含各模块所有表数据的 JSON。

    某个模块导出失败不会静默消失：会在响应的 ``errors`` 字段里点名，
    并记 warning。否则用户拿到一份「看着完整」的残缺备份，灾备时才发现。
    """
    return svc.export_all()


@router.post("/import")
def import_backup(payload: dict):
    """从备份 JSON 恢复（覆盖备份中出现的表）。"""
    try:
        return svc.import_all(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
