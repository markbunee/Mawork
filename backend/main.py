"""MaWork 后端入口。

启动（必须在 Mawork/ 目录下，使 backend 作为包被导入）：
    cd Mawork && uvicorn backend.main:app --port 8001 --reload
    cd Mawork && python -m backend.main
"""

import sys
from pathlib import Path

# 把 Mawork/ 加入模块搜索路径，保证 backend 作为包可导入
MAWORK_DIR = Path(__file__).resolve().parent.parent
if str(MAWORK_DIR) not in sys.path:
    sys.path.insert(0, str(MAWORK_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .routers import accounting, articles, daily, planpool, resources

app = FastAPI(title="MaWork API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db.init_db()


@app.get("/api/health")
def health():
    return {"ok": True}


app.include_router(daily.router)
app.include_router(accounting.router)
app.include_router(planpool.router)
app.include_router(articles.router)
app.include_router(resources.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8001, reload=True)
