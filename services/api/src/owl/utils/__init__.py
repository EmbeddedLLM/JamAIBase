from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from uuid_extensions import uuid7str as _uuid7_draft2_str
from uuid_utils import uuid7 as _uuid7

from jamaibase.exceptions import ResourceNotFoundError


def get_non_empty(mapping: dict[str, Any], key: str, default: Any):
    value = mapping.get(key, None)
    return value if value else default


def datetime_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def uuid7_draft2_str(prefix: str = "") -> str:
    return f"{prefix}{_uuid7_draft2_str()}"


def uuid7_str(prefix: str = "") -> str:
    return f"{prefix}{_uuid7()}"


def datetime_str_from_uuid7(uuid7_str: str) -> str:
    # Extract the timestamp (first 48 bits)
    timestamp = UUID(uuid7_str).int >> 80
    dt = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)
    return dt.isoformat()


def datetime_str_from_uuid7_draft2(uuid7_str: str) -> str:
    # https://www.ietf.org/archive/id/draft-peabody-dispatch-new-uuid-format-02.html#name-uuidv7-layout-and-bit-order
    # Parse the UUID string
    uuid_obj = UUID(uuid7_str)
    # Extract the unix timestamp (first 36 bits)
    unix_ts = uuid_obj.int >> 92
    # Extract the fractional seconds (next 24 bits)
    frac_secs = (uuid_obj.int >> 68) & 0xFFFFFF
    # Combine unix timestamp and fractional seconds
    total_secs = unix_ts + (frac_secs / 0x1000000)
    # Create a datetime object
    dt = datetime.fromtimestamp(total_secs, tz=timezone.utc)
    return dt.isoformat()


def select_external_api_key(external_api_keys, provider: str) -> str:
    if provider == "ellm":
        return "DUMMY_KEY"
    else:
        try:
            return getattr(external_api_keys, provider) or "DUMMY_KEY"
        except AttributeError:
            raise ResourceNotFoundError(
                f"External API key not found for provider: {provider}"
            ) from None


def mask_string(x: str | None) -> str | None:
    if x is None:
        return None
    if x.startswith("[ERROR]"):
        return x
    return f"len={len(x)} str={x[:5]}***{x[-5:]}"


def mask_content(x: str | list[dict[str, str]] | None) -> str | list[dict[str, str]] | None:
    if isinstance(x, list):
        return [mask_content(v) for v in x]
    if isinstance(x, dict):
        return {k: mask_content(v) for k, v in x.items()}
    if isinstance(x, str):
        return mask_string(x)
    return None
