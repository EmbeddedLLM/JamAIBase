from fastapi import APIRouter

from owl.configs import ENV_CONFIG
from owl.routers.users.oss import router as oss_router

router = APIRouter()
router.include_router(oss_router)

if ENV_CONFIG.is_cloud:
    from owl.routers.users.cloud import router as cloud_router

    router.include_router(cloud_router)
