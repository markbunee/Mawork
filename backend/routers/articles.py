"""文章路由。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import articles

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("/{year}")
def list_articles(year: str):
    """列出某年全部文章。"""
    items = articles.list_articles(year)
    return {"year": year, "articles": items}


@router.get("/{year}/{title}")
def get_article(year: str, title: str):
    """获取某篇（按 year + title）。标题含特殊字符会自动 URL 解码。"""
    art = articles.get_article(year, title)
    if art is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    return art


class ArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = ""            # Markdown 正文
    date: str = Field(default="", max_length=10)  # YYYY-MM-DD，可空


@router.put("/{year}/{title}")
def upsert_article(year: str, title: str, payload: ArticleIn):
    """新建或更新。路径 title 为主键；payload.title 与路径不同则改名。"""
    try:
        return articles.upsert_article(
            year, title, payload.content, payload.date, new_title=payload.title
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.post("/{year}")
def create_article(year: str, payload: ArticleIn):
    """新建一篇（标题在 payload 中）。"""
    try:
        return articles.upsert_article(year, payload.title, payload.content, payload.date)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.delete("/{year}/{title}")
def delete_article(year: str, title: str):
    if not articles.delete_article(year, title):
        raise HTTPException(status_code=404, detail="文章不存在")
    return {"ok": True}



