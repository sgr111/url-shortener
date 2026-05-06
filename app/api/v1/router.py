from fastapi import APIRouter

from app.api.v1.endpoints import auth, urls

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(urls.router)
