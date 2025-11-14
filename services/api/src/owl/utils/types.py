import base64

import orjson
from sqlalchemy import TypeDecorator
from sqlmodel import JSON

from jamaibase.utils.types import (  # noqa: F401
    CLI,
    get_enum_validator,
)
from owl.configs import ENV_CONFIG


class RqliteJSON(TypeDecorator):
    impl = JSON

    def process_bind_param(self, value, dialect):
        if value is not None:
            # Encode JSON data as Base64 before storing it
            return base64.b64encode(orjson.dumps(value)).decode("utf-8")
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            # Handle empty strings explicitly
            if value == "":
                return None  # or return an empty dict {} depending on your use case
            # If the value is already a dictionary, return it directly
            if isinstance(value, (list, dict)):
                return value
            # Ensure the value is a string before decoding
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            # Decode Base64 data back to JSON
            return orjson.loads(base64.b64decode(value.encode("utf-8")))
        return value


if ENV_CONFIG.db_dialect == "rqlite":
    JSON = RqliteJSON
elif ENV_CONFIG.db_dialect == "postgresql":
    from sqlalchemy.dialects.postgresql import JSONB

    JSON = JSONB
