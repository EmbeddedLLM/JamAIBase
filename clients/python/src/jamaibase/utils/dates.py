from datetime import date, datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def now(tz: str = "UTC") -> datetime:
    return datetime.now(ZoneInfo(tz))


def now_iso(tz: str = "UTC") -> str:
    return now(tz).isoformat()


def now_tz_naive(tz: str = "UTC") -> datetime:
    return datetime.now(ZoneInfo(tz)).replace(tzinfo=None)


def earliest(tz: str = "UTC") -> datetime:
    return datetime.min.replace(tzinfo=ZoneInfo(tz))


def utc_iso_from_string(dt: str) -> str:
    parsed_dt: datetime = datetime.fromisoformat(dt)  # Explicitly declare type
    if parsed_dt.tzinfo is None:
        raise ValueError("Input datetime string is not timezone aware.")
    return parsed_dt.astimezone(timezone.utc).isoformat()


def utc_iso_from_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("Input datetime object is not timezone aware.")
    return dt.astimezone(timezone.utc).isoformat()


def utc_datetime_from_iso(dt: str) -> datetime:
    parsed_dt: datetime = datetime.fromisoformat(dt)  # Explicitly declare type
    if parsed_dt.tzinfo is None:
        raise ValueError("Input datetime string is not timezone aware.")
    return parsed_dt.astimezone(timezone.utc)


def utc_iso_from_uuid7(uuid7_str: str) -> str:
    # from uuid_utils import uuid7
    # Extract the timestamp (first 48 bits)
    timestamp = UUID(uuid7_str).int >> 80
    dt = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)
    return dt.isoformat()


def utc_iso_from_uuid7_draft2(uuid7_str: str) -> str:
    # from uuid_extensions import uuid7str
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


def date_to_utc(d: date, tz: str = "UTC") -> datetime:
    try:
        return datetime.combine(d, time.min, ZoneInfo(tz)).astimezone(timezone.utc)
    except ZoneInfoNotFoundError as e:
        raise ValueError(f"Invalid timezone: {tz}") from e


def date_to_utc_iso(d: date, tz: str = "UTC") -> str:
    return date_to_utc(d, tz).isoformat()


def ensure_utc_timezone(value: str) -> str:
    dt = datetime.fromisoformat(value)
    tz = str(dt.tzinfo)
    if tz != "UTC":
        raise ValueError(f'Time zone must be UTC, but received "{tz}".')
    return value
