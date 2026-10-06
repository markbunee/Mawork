"""横切能力 E4：提醒通知路由（派生，受保护）。"""

from fastapi import APIRouter

from ..services import reminder as svc

router = APIRouter(prefix="/api/reminder", tags=["reminder"])


@router.get("/list")
def list_reminders():
    return svc.get_reminders()
