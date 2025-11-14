from typing import Any

from pydantic import BaseModel


class LogQueryResponse(BaseModel):
    logs: list[dict[str, Any]]
