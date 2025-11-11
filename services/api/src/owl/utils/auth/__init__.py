from owl.configs import ENV_CONFIG

if ENV_CONFIG.is_oss:
    from owl.utils.auth.oss import (  # noqa: F401
        auth_service_key,
        auth_user,
        auth_user_project,
        auth_user_service_key,
        has_permissions,
    )
else:
    from owl.utils.auth.cloud import (  # noqa: F401
        auth_service_key,
        auth_user,
        auth_user_project,
        auth_user_service_key,
        has_permissions,
    )
