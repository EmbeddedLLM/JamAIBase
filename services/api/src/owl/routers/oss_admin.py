from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from loguru import logger
from sqlmodel import Session

from jamaibase.exceptions import ResourceNotFoundError
from owl.configs.manager import CONFIG, ENV_CONFIG
from owl.db import MAIN_ENGINE, UserSQLModel, create_sql_tables
from owl.db.oss_admin import (
    Organization,
    OrganizationRead,
    OrganizationUpdate,
)
from owl.protocol import ModelListConfig, OkResponse
from owl.utils import datetime_now_iso
from owl.utils.crypt import encrypt_random
from owl.utils.exceptions import handle_exception

router = APIRouter()
public_router = APIRouter()  # Dummy router to be compatible with cloud admin


@router.on_event("startup")
async def startup():
    create_sql_tables(UserSQLModel, MAIN_ENGINE)


def _get_session():
    with Session(MAIN_ENGINE) as session:
        yield session


@router.patch("/admin/backend/v1/organizations")
@handle_exception
def update_organization(
    *,
    session: Annotated[Session, Depends(_get_session)],
    request: Request,
    body: OrganizationUpdate,
) -> OrganizationRead:
    body.id = ENV_CONFIG.default_org_id
    org = session.get(Organization, body.id)
    if org is None:
        raise ResourceNotFoundError(f'Organization "{body.id}" is not found.')

    # --- Perform update --- #
    for key, value in body.model_dump(exclude=["id"], exclude_none=True).items():
        if key == "external_keys":
            value = {
                k: encrypt_random(v, ENV_CONFIG.owl_encryption_key_plain) for k, v in value.items()
            }
        setattr(org, key, value)
    org.updated_at = datetime_now_iso()
    session.add(org)
    session.commit()
    session.refresh(org)
    logger.info(f"{request.state.id} - Organization updated: {org}")
    org = OrganizationRead(
        **org.model_dump(),
        projects=org.projects,
    ).decrypt(ENV_CONFIG.owl_encryption_key_plain)
    return org


@router.get("/admin/backend/v1/organizations/{org_id}")
@handle_exception
def get_organization(
    *,
    session: Annotated[Session, Depends(_get_session)],
    org_id: Annotated[str, Path(min_length=1)],
) -> OrganizationRead:
    org = session.get(Organization, org_id)
    if org is None:
        raise ResourceNotFoundError(f'Organization "{org_id}" is not found.')
    org = OrganizationRead(
        **org.model_dump(),
        projects=org.projects,
    ).decrypt(ENV_CONFIG.owl_encryption_key_plain)
    return org


@router.get("/admin/backend/v1/models")
@handle_exception
def get_model_config() -> ModelListConfig:
    # Get model config (exclude org models)
    return CONFIG.get_model_config()


@router.patch("/admin/backend/v1/models")
@handle_exception
def set_model_config(body: ModelListConfig) -> OkResponse:
    CONFIG.set_model_config(body)
    return OkResponse()
