"""文章路由。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import articles

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("/{year}")
def list_articles(year: str):
    """列出某年全部文章标题。"""
    items = articles.list_articles(year)
    return {"year": year, "articles": items}


@router.get("/{year}/{title}")
def get_article(year: str, title: str):
    """获取某篇（按标题）。标题含特殊字符会自动 URL 解码。"""
    art = articles.get_article(year, title)
    if art is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    return art


class ArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""


@router.put("/{year}/{title}")
def upsert_article(year: str, title: str, payload: ArticleIn):
    """新建或更新。路径中的 title 为主键，正文用 payload.body。"""
    return articles.upsert_article(year, title, payload.body)


@router.post("/{year}")
def create_article(year: str, payload: ArticleIn):
    """新建一篇（标题在 payload 中，追加到末尾）。"""
    return articles.upsert_article(year, payload.title, payload.body)


@router.delete("/{year}/{title}")
def delete_article(year: str, title: str):
    if not articles.delete_article(year, title):
        raise HTTPException(status_code=404, detail="文章不存在")
    return {"ok": True}
