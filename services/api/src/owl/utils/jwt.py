from datetime import datetime, timezone
from typing import Any

import jwt
from loguru import logger

from jamaibase.exceptions import AuthorizationError
from owl.configs.manager import ENV_CONFIG


def encode_jwt(data: dict[str, Any], expiry: datetime) -> str:
    data.update({"iat": datetime.now(tz=timezone.utc), "exp": expiry})
    token = jwt.encode(data, f"{ENV_CONFIG.owl_encryption_key_plain}_secret", algorithm="HS256")
    return token


def decode_jwt(
    token: str,
    expired_token_message: str,
    invalid_token_message: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    try:
        data = jwt.decode(
            token,
            f"{ENV_CONFIG.owl_encryption_key_plain}_secret",
            algorithms=["HS256"],
        )
        return data
    except jwt.exceptions.ExpiredSignatureError as e:
        raise AuthorizationError(expired_token_message) from e
    except jwt.exceptions.PyJWTError as e:
        raise AuthorizationError(invalid_token_message) from e
    except Exception as e:
        if request_id is None:
            logger.exception(f'Failed to decode "{token}" due to {e.__class__.__name__}: {e}')
        else:
            logger.exception(
                f'{request_id} - Failed to decode "{token}" due to {e.__class__.__name__}: {e}'
            )
        raise AuthorizationError(invalid_token_message) from e
