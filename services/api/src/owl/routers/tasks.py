from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from owl.configs import CACHE
from owl.types import UserAuth
from owl.utils.auth import auth_user_service_key
from owl.utils.exceptions import handle_exception

router = APIRouter()


@router.get(
    "/v2/progress",
    summary="Get progress data.",
    description="Permissions: None as long as signed-in.",
)
@handle_exception
async def get_progress(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    key: Annotated[str, Query(min_length=1, description="Progress key.")],
) -> dict[str, Any]:
    del user
    return (await CACHE.get_progress(key, None)) or {}
