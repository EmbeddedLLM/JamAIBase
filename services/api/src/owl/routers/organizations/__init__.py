from fastapi import APIRouter

from owl.configs import ENV_CONFIG
from owl.routers.organizations.oss import router as oss_router
from owl.routers.organizations.secrets import router as secrets_router

router = APIRouter()
router.include_router(oss_router)
router.include_router(secrets_router)


if ENV_CONFIG.is_cloud:
    from owl.routers.organizations.cloud import router as cloud_router

    router.include_router(cloud_router)
