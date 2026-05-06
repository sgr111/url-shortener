from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_optional_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.analytics import AnalyticsOut
from app.schemas.url import URLCreate, URLListOut, URLOut
from app.services import url_service

router = APIRouter(prefix="/urls", tags=["URLs"])


@router.post("/shorten", response_model=URLOut, status_code=status.HTTP_201_CREATED)
async def shorten_url(
    request: Request,
    body: URLCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    user_id = current_user.id if current_user else None
    return await url_service.create_short_url(db, body, user_id=user_id)


@router.get("/", response_model=URLListOut)
async def list_urls(
    request: Request,
    skip: int = 0,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await url_service.list_urls(db, user_id=current_user.id, skip=skip, limit=limit)


@router.get("/{url_id}/analytics", response_model=AnalyticsOut)
async def get_analytics(
    request: Request,
    url_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analytics = await url_service.get_analytics(db, url_id=url_id, user_id=current_user.id)
    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="URL not found or not owned by you",
        )
    return analytics


@router.delete("/{url_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_url(
    request: Request,
    url_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = await url_service.deactivate_url(db, url_id=url_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="URL not found or not owned by you",
        )
