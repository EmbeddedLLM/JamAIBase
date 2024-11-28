from functools import lru_cache
from secrets import compare_digest
from typing import Annotated, AsyncGenerator

from fastapi import Header, Request, Response
from httpx import RequestError
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from jamaibase import JamAIAsync
from jamaibase.exceptions import (
    AuthorizationError,
    ForbiddenError,
    ResourceNotFoundError,
    ServerBusyError,
    UnexpectedError,
    UpgradeTierError,
)
from jamaibase.protocol import (
    EmbeddingModelConfig,
    LLMModelConfig,
    ModelDeploymentConfig,
    OrganizationRead,
    PATRead,
    ProjectRead,
    RerankingModelConfig,
    UserRead,
)
from owl.billing import BillingManager
from owl.configs.manager import CONFIG, ENV_CONFIG
from owl.protocol import ExternalKeys, ModelListConfig
from owl.utils import datetime_now_iso, get_non_empty

CLIENT = JamAIAsync(token=ENV_CONFIG.service_key_plain, timeout=60.0)
WRITE_METHODS = {"PUT", "PATCH", "POST", "DELETE", "PURGE"}
JAMAI_CLOUD_URL = "https://cloud.jamaibase.com"
NO_PROJECT_ID_MESSAGE = (
    "You didn't provide a project ID. "
    'You need to provide your project ID in an "X-PROJECT-ID" header '
    "(i.e. X-PROJECT-ID: PROJECT_ID). "
    f"You can retrieve your project ID via API or from {JAMAI_CLOUD_URL}"
)
NO_TOKEN_MESSAGE = (
    "You didn't provide an authorization token. "
    "You need to provide your either your Personal Access Token or organization API key (deprecated) "
    'in an "Authorization" header using Bearer auth (i.e. "Authorization: Bearer TOKEN"). '
    f"You can obtain your token from {JAMAI_CLOUD_URL}"
)
INVALID_TOKEN_MESSAGE = (
    "You provided an invalid authorization token. "
    "You need to provide your either your Personal Access Token or organization API key (deprecated) "
    'in an "Authorization" header using Bearer auth (i.e. "Authorization: Bearer TOKEN"). '
    f"You can obtain your token from {JAMAI_CLOUD_URL}"
)
ORG_API_KEY_DEPRECATE_MESSAGE = (
    "Usage of organization API key is deprecated and will be removed soon. "
    "Authenticate using your Personal Access Token instead."
)


@retry(
    retry=retry_if_exception_type(RequestError),
    wait=wait_random_exponential(multiplier=1, min=0.1, max=3),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _get_project_with_retries(project_id: str) -> ProjectRead:
    return await CLIENT.admin.organization.get_project(project_id)


async def _get_project(request: Request, project_id: str) -> ProjectRead:
    try:
        return await _get_project_with_retries(project_id)
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.') from e
    except RequestError as e:
        logger.warning(
            f'{request.state.id} - Error fetching project "{project_id}" due to {e.__class__.__name__}: {e}'
        )
        raise ServerBusyError(f"{e.__class__.__name__}: {e}") from e
    except Exception as e:
        raise UnexpectedError(f"{e.__class__.__name__}: {e}") from e


@retry(
    retry=retry_if_exception_type(RequestError),
    wait=wait_random_exponential(multiplier=1, min=0.1, max=3),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _get_organization_with_retries(org_id_or_token: str) -> OrganizationRead:
    return await CLIENT.admin.backend.get_organization(org_id_or_token)


async def _get_organization(request: Request, org_id_or_token: str) -> OrganizationRead:
    try:
        return await _get_organization_with_retries(org_id_or_token)
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Organization "{org_id_or_token}" is not found.') from e
    except RequestError as e:
        logger.warning(
            f'{request.state.id} - Error fetching organization "{org_id_or_token}" due to {e.__class__.__name__}: {e}'
        )
        raise ServerBusyError(f"{e.__class__.__name__}: {e}") from e
    except Exception as e:
        raise UnexpectedError(f"{e.__class__.__name__}: {e}") from e


@retry(
    retry=retry_if_exception_type(RequestError),
    wait=wait_random_exponential(multiplier=1, min=0.1, max=3),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _get_user_with_retries(user_id_or_token: str) -> UserRead:
    return await CLIENT.admin.backend.get_user(user_id_or_token)


async def _get_user(request: Request, user_id_or_token: str) -> UserRead:
    try:
        return await _get_user_with_retries(user_id_or_token)
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'User "{user_id_or_token}" is not found.') from e
    except RequestError as e:
        logger.warning(
            f'{request.state.id} - Error fetching user "{user_id_or_token}" due to {e.__class__.__name__}: {e}'
        )
        raise ServerBusyError(f"{e.__class__.__name__}: {e}") from e
    except Exception as e:
        raise UnexpectedError(f"{e.__class__.__name__}: {e}") from e


@retry(
    retry=retry_if_exception_type(RequestError),
    wait=wait_random_exponential(multiplier=1, min=0.1, max=3),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _get_pat_with_retries(token: str) -> PATRead:
    return await CLIENT.admin.backend.get_pat(token)


async def _get_pat(request: Request, token: str) -> PATRead:
    try:
        return await _get_pat_with_retries(token)
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'PAT "{token}" is not found.') from e
    except RequestError as e:
        logger.warning(
            f'{request.state.id} - Error fetching PAT "{token}" due to {e.__class__.__name__}: {e}'
        )
        raise ServerBusyError(f"{e.__class__.__name__}: {e}") from e
    except Exception as e:
        raise UnexpectedError(f"{e.__class__.__name__}: {e}") from e


def _get_external_keys(organization: OrganizationRead) -> ExternalKeys:
    ext_keys = organization.external_keys
    return ExternalKeys(
        custom=get_non_empty(ext_keys, "custom", ENV_CONFIG.custom_api_key_plain),
        openai=get_non_empty(ext_keys, "openai", ENV_CONFIG.openai_api_key_plain),
        anthropic=get_non_empty(ext_keys, "anthropic", ENV_CONFIG.anthropic_api_key_plain),
        gemini=get_non_empty(ext_keys, "gemini", ENV_CONFIG.gemini_api_key_plain),
        cohere=get_non_empty(ext_keys, "cohere", ENV_CONFIG.cohere_api_key_plain),
        groq=get_non_empty(ext_keys, "groq", ENV_CONFIG.groq_api_key_plain),
        together_ai=get_non_empty(ext_keys, "together_ai", ENV_CONFIG.together_api_key_plain),
        jina=get_non_empty(ext_keys, "jina", ENV_CONFIG.jina_api_key_plain),
        voyage=get_non_empty(ext_keys, "voyage", ENV_CONFIG.voyage_api_key_plain),
        hyperbolic=get_non_empty(ext_keys, "hyperbolic", ENV_CONFIG.hyperbolic_api_key_plain),
        cerebras=get_non_empty(ext_keys, "cerebras", ENV_CONFIG.cerebras_api_key_plain),
        sambanova=get_non_empty(ext_keys, "sambanova", ENV_CONFIG.sambanova_api_key_plain),
    )


async def auth_internal_oss() -> str:
    return ""


async def auth_internal_cloud(
    bearer_token: Annotated[str, Header(alias="Authorization", description="Service key.")] = "",
) -> str:
    bearer_token = bearer_token.strip().split("Bearer ")
    if len(bearer_token) < 2 or bearer_token[1].strip() == "":
        raise AuthorizationError(NO_TOKEN_MESSAGE)
    token = bearer_token[1].strip()
    if not (
        compare_digest(token, ENV_CONFIG.service_key_plain)
        or compare_digest(token, ENV_CONFIG.service_key_alt_plain)
    ):
        raise AuthorizationError(INVALID_TOKEN_MESSAGE)
    return token


auth_internal = auth_internal_oss if ENV_CONFIG.is_oss else auth_internal_cloud


AuthReturn = tuple[UserRead | None, OrganizationRead | None]


async def auth_user_oss() -> AuthReturn:
    return None, None


async def auth_user_cloud(
    request: Request,
    response: Response,
    bearer_token: Annotated[
        str,
        Header(
            alias="Authorization",
            description="One of: Service key, user PAT or organization API key.",
        ),
    ] = "",
    user_id: Annotated[str, Header(alias="X-USER-ID", description="User ID.")] = "",
) -> AuthReturn:
    bearer_token = bearer_token.strip()
    bearer_token = bearer_token.split("Bearer ")
    if len(bearer_token) < 2 or bearer_token[1].strip() == "":
        raise AuthorizationError(NO_TOKEN_MESSAGE)

    # Authenticate
    user = org = None
    token = bearer_token[1].strip()
    if (
        compare_digest(token, ENV_CONFIG.service_key_plain)
        or compare_digest(token, ENV_CONFIG.service_key_alt_plain)
        or token.startswith("jamai_sk_")
    ):
        if token.startswith("jamai_sk_"):
            org = await _get_organization(request, token)
            response.headers["Warning"] = f'299 - "{ORG_API_KEY_DEPRECATE_MESSAGE}"'
        if user_id:
            user = await _get_user(request, user_id)

    elif token.startswith("jamai_pat_"):
        user = await _get_user(request, token)

    elif user := request.session.get("user", None) is not None:
        user = UserRead(**user)

    else:
        raise AuthorizationError(INVALID_TOKEN_MESSAGE)
    return user, org


auth_user = auth_user_oss if ENV_CONFIG.is_oss else auth_user_cloud


def _get_valid_deployments(
    model: LLMModelConfig | EmbeddingModelConfig | RerankingModelConfig,
    valid_providers: list[str],
) -> list[ModelDeploymentConfig]:
    valid_deployments = []
    for deployment in model.deployments:
        if deployment.provider in valid_providers:
            valid_deployments.append(deployment)
    return valid_deployments


@lru_cache(maxsize=64)
def _get_valid_modellistconfig(all_models: str, external_keys: str) -> ModelListConfig:
    all_models = ModelListConfig.model_validate_json(all_models)
    external_keys = ExternalKeys.model_validate_json(external_keys)
    # define all possible api providers
    available_providers = [
        "openai",
        "anthropic",
        "together_ai",
        "cohere",
        "sambanova",
        "cerebras",
        "hyperbolic",
    ]
    # remove providers without credentials
    available_providers = [
        provider for provider in available_providers if getattr(external_keys, provider) != ""
    ]
    # add custom and ellm providers as allow no credentials
    available_providers.extend(
        [
            "custom",
            "ellm",
        ]
    )

    # Initialize lists to hold valid models
    valid_llm_models = []
    valid_embed_models = []
    valid_rerank_models = []

    # Iterate over the llm, embed, rerank list
    for m in all_models.llm_models:
        valid_deployments = _get_valid_deployments(m, available_providers)
        if len(valid_deployments) > 0:
            m.deployments = valid_deployments
            valid_llm_models.append(m)

    for m in all_models.embed_models:
        valid_deployments = _get_valid_deployments(m, available_providers)
        if len(valid_deployments) > 0:
            m.deployments = valid_deployments
            valid_embed_models.append(m)

    for m in all_models.rerank_models:
        valid_deployments = _get_valid_deployments(m, available_providers)
        if len(valid_deployments) > 0:
            m.deployments = valid_deployments
            valid_rerank_models.append(m)

    # Create a new ModelListConfig with the valid models
    valid_model_list_config = ModelListConfig(
        llm_models=valid_llm_models,
        embed_models=valid_embed_models,
        rerank_models=valid_rerank_models,
    )

    return valid_model_list_config


async def auth_user_project_oss(
    request: Request,
    project_id: Annotated[
        str, Header(alias="X-PROJECT-ID", description='Project ID "proj_xxx".')
    ] = "default",
) -> AsyncGenerator[ProjectRead, None]:
    project_id = project_id.strip()
    if project_id == "":
        raise AuthorizationError(NO_PROJECT_ID_MESSAGE)

    # Fetch project
    project = await _get_project(request, project_id)
    organization = project.organization

    # Set some state
    request.state.org_id = organization.id
    request.state.project_id = project.id
    request.state.external_keys = _get_external_keys(organization)
    request.state.org_models = ModelListConfig.model_validate(organization.models)
    all_models = request.state.org_models + CONFIG.get_model_config()
    request.state.all_models = _get_valid_modellistconfig(
        all_models.model_dump_json(), request.state.external_keys.model_dump_json()
    )
    request.state.billing = BillingManager(request=request)

    yield project


async def auth_user_project_cloud(
    request: Request,
    response: Response,
    project_id: Annotated[
        str, Header(alias="X-PROJECT-ID", description='Project ID "proj_xxx".')
    ] = "",
    bearer_token: Annotated[
        str,
        Header(
            alias="Authorization",
            description="One of: Service key, user PAT or organization API key.",
        ),
    ] = "",
    user_id: Annotated[str, Header(alias="X-USER-ID", description="User ID.")] = "",
) -> AsyncGenerator[ProjectRead, None]:
    route = request.url.path
    user_id = ""
    project_id = project_id.strip()
    bearer_token = bearer_token.strip()
    user_id = user_id.strip()
    if project_id == "":
        raise AuthorizationError(NO_PROJECT_ID_MESSAGE)

    # Fetch project
    project = await _get_project(request, project_id)
    organization = project.organization

    # Set some state
    request.state.org_id = organization.id
    request.state.project_id = project.id
    request.state.external_keys = _get_external_keys(organization)
    request.state.org_models = ModelListConfig.model_validate(organization.models)
    all_models = request.state.org_models + CONFIG.get_model_config()
    request.state.all_models = _get_valid_modellistconfig(
        all_models.model_dump_json(), request.state.external_keys.model_dump_json()
    )
    # Check if token is provided
    bearer_token = bearer_token.split("Bearer ")
    if len(bearer_token) < 2 or bearer_token[1].strip() == "":
        raise AuthorizationError(NO_TOKEN_MESSAGE)

    user_roles = {u.user_id: u.role for u in organization.members}
    # Non-activated orgs can only perform GET requests
    if (not organization.active) and (request.method != "GET"):
        raise UpgradeTierError(f'Your organization "{organization.id}" is not activated.')

    # Authenticate
    token = bearer_token[1].strip()
    if compare_digest(token, ENV_CONFIG.service_key_plain) or compare_digest(
        token, ENV_CONFIG.service_key_alt_plain
    ):
        pass
    elif token.startswith("jamai_sk_"):
        _org = await _get_organization(request, token)
        if project.organization.id != _org.id:
            raise AuthorizationError(
                f'Your provided project "{project.id}" does not belong to organization "{_org.id}".'
            )
        response.headers["Warning"] = f'299 - "{ORG_API_KEY_DEPRECATE_MESSAGE}"'

    elif token.startswith("jamai_pat_"):
        pat = await _get_pat(request, token)
        if pat.expiry != "" and datetime_now_iso() > pat.expiry:
            raise AuthorizationError(
                "Your Personal Access Token has expired. Please generate a new token."
            )
        user_id = pat.user_id

    elif logged_in_user := request.session.get("user", None) is not None:
        logged_in_user = UserRead(**logged_in_user)
        user_id = logged_in_user.id

    else:
        raise AuthorizationError(INVALID_TOKEN_MESSAGE)

    # Role-based access control
    if user_id:
        user_role = user_roles.get(user_id, None)
        if user_role is None:
            raise ForbiddenError(f'You do not have access to organization "{organization.id}".')
        if user_role == "guest" and request.method in WRITE_METHODS:
            raise ForbiddenError(
                f'You do not have write access to organization "{organization.id}".'
            )
        if user_role != "admin" and "api/admin/org" in route:
            raise ForbiddenError(
                f'You do not have admin access to organization "{organization.id}".'
            )

    # Billing
    request.state.billing = BillingManager(
        organization=organization,
        project_id=project.id,
        user_id=user_id,
        request=request,
    )

    # If quota ran out then allow read access only
    if request.method in WRITE_METHODS:
        request.state.billing.check_egress_quota()
        request.state.billing.check_db_storage_quota()
        request.state.billing.check_file_storage_quota()

    yield project

    # Add egress events
    request.state.billing.create_egress_events(
        float(response.headers.get("content-length", 0)) / (1024**3)
    )
    # Process all billing events
    await request.state.billing.process_all()

    # Set project updated at datetime
    if "gen_tables" in route and request.method in WRITE_METHODS:
        try:
            await CLIENT.admin.organization.set_project_updated_at(project_id)
        except Exception as e:
            logger.warning(
                f'{request.state.id} - Error setting project "{project_id}" last updated time: {e}'
            )


auth_user_project = auth_user_project_oss if ENV_CONFIG.is_oss else auth_user_project_cloud
