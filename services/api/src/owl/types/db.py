from typing import Annotated

from pwdlib import PasswordHash
from pydantic import BaseModel, BeforeValidator, Field
from sqlmodel import Field as SqlField

from jamaibase import types as t
from jamaibase.types import PricePlan_, SanitisedNonEmptyStr
from owl.utils.crypt import decrypt


def _decrypt(value: str) -> str:
    from owl.configs import ENV_CONFIG

    return decrypt(value, ENV_CONFIG.encryption_key_plain)


def _decrypt_external_keys(value: dict[str, str] | BaseModel) -> dict[str, str]:
    if isinstance(value, BaseModel):
        value = value.model_dump(exclude_unset=True)
    return {k: _decrypt(v) for k, v in value.items()}


class UserUpdate(t.UserUpdate):
    password: SanitisedNonEmptyStr = Field(
        "",
        max_length=72,
        description="Password in plain text.",
    )

    @property
    def password_hash(self) -> str | None:
        if self.password:
            hasher = PasswordHash.recommended()
            return hasher.hash(self.password)
        return None


class UserCreate(t.UserCreate):
    @property
    def password_hash(self) -> str | None:
        if self.password:
            hasher = PasswordHash.recommended()
            return hasher.hash(self.password)
        return None


class Organization_(t.Organization_):
    def get_external_key(self, provider: str) -> str:
        api_key = self.external_keys.get(provider.lower(), "").strip()
        return _decrypt(api_key) if api_key else ""


class OrganizationRead(Organization_):
    price_plan: PricePlan_ | None = Field(
        description="Subscribed plan.",
    )


class OrganizationReadDecrypt(OrganizationRead):
    external_keys: Annotated[dict[str, str], BeforeValidator(_decrypt_external_keys)] = SqlField(
        description="Mapping of external service provider to its API key.",
    )


class ProjectKeyReadDecrypt(t.ProjectKeyRead):
    id: Annotated[str, BeforeValidator(_decrypt)] = Field(
        description="The token after decryption.",
    )
