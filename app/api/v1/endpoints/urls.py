from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_optional_user
from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.analytics import AnalyticsOut
from app.schemas.url import BulkURLResult, URLCreate, URLListOut, URLOut
from app.services import url_service

router = APIRouter(prefix="/urls", tags=["URLs"])


@router.post("/shorten", response_model=URLOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def shorten_url(
    request: Request,
    body: URLCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    user_id = current_user.id if current_user else None
    return await url_service.create_short_url(db, body, user_id=user_id)


MAX_BULK_ROWS = 500


@router.post("/bulk-shorten", response_model=BulkURLResult, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def bulk_shorten_urls(
    request: Request,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """
    Shorten many URLs in one request from an uploaded CSV.
    Expected format: a header row containing an `original_url` column,
    one URL per subsequent row. Bad rows are reported, not fatal —
    see BulkURLResult for the per-row success/failure breakdown.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .csv",
        )

    import csv
    import io

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # handles Excel's UTF-8 BOM too
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must be UTF-8 encoded",
        )

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "original_url" not in reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must have an 'original_url' column header",
        )

    rows = list(reader)
    if len(rows) > MAX_BULK_ROWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max {MAX_BULK_ROWS} rows per upload, got {len(rows)}",
        )

    user_id = current_user.id if current_user else None
    return await url_service.bulk_create_short_urls(db, rows, user_id=user_id)


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


@router.get("/{short_code}/qr")
async def get_qr_code(
    request: Request,
    short_code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a PNG QR code encoding this link's short URL. Public, no auth
    required — same audience as the redirect itself (anyone with the
    short_code can already reach the link, a QR code is just another way
    to reach the same public endpoint).

    Reuses get_url_by_code(), so this benefits from the same Redis cache
    as the redirect path — no separate lookup/caching logic needed.
    """
    import io

    import qrcode

    url = await url_service.get_url_by_code(db, short_code)
    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Short code '{short_code}' not found",
        )

    is_valid, reason = url_service.check_url_validity(url)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=reason)

    short_url = f"{settings.BASE_URL}/{short_code}"
    img = qrcode.make(short_url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")

    return Response(content=buffer.getvalue(), media_type="image/png")