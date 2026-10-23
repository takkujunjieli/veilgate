"""Versioned, strict operator configuration. No configuration API is exposed."""

import os
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from veilgate.errors import StartupError

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Column = Annotated[str, Field(min_length=1, max_length=128)]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class Principal(StrictModel):
    id: Identifier
    token_env: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")]


class Resource(StrictModel):
    id: Identifier
    path: str
    allowed_principals: Annotated[list[Identifier], Field(min_length=1, max_length=100)]
    published_fields: Annotated[list[Column], Field(min_length=1, max_length=100)]
    operation: Literal["read_redacted"] = "read_redacted"

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        parts = value.split("/")
        if (
            not value
            or len(value) > 1024
            or PurePosixPath(value).is_absolute()
            or any(part in ("", ".", "..") for part in parts)
            or "\\" in value
            or "\x00" in value
            or not value.endswith(".csv")
        ):
            raise ValueError("invalid resource path")
        return value

    @field_validator("published_fields", "allowed_principals")
    @classmethod
    def unique_values(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(
            any(ord(char) < 32 or ord(char) == 127 for char in value) for value in values
        ):
            raise ValueError("invalid or duplicate values")
        return values


class Limits(StrictModel):
    max_file_bytes: int = Field(default=1_048_576, ge=1, le=10_485_760)
    max_rows: int = Field(default=1000, ge=1, le=10_000)
    max_columns: int = Field(default=100, ge=1, le=500)
    max_output_bytes: int = Field(default=1_048_576, ge=128, le=10_485_760)
    max_concurrent_requests: int = Field(default=4, ge=1, le=32)


class Settings(StrictModel):
    schema_version: Literal[1]
    policy_version: Identifier
    data_root: str
    principals: Annotated[list[Principal], Field(min_length=1, max_length=100)]
    resources: Annotated[list[Resource], Field(min_length=1, max_length=100)]
    limits: Limits = Field(default_factory=Limits)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value

    @field_validator("data_root")
    @classmethod
    def absolute_root(cls, value: str) -> str:
        if not value.startswith("/") or "\x00" in value or ".." in value.split("/"):
            raise ValueError("absolute data root required")
        return value

    @model_validator(mode="after")
    def references(self) -> Self:
        ids = [p.id for p in self.principals]
        envs = [p.token_env for p in self.principals]
        resources = [r.id for r in self.resources]
        if any(len(values) != len(set(values)) for values in (ids, envs, resources)):
            raise ValueError("duplicate configuration identifier")
        if any(not set(r.allowed_principals).issubset(ids) for r in self.resources):
            raise ValueError("unknown principal")
        return self


def load_settings(path: Path) -> Settings:
    try:
        with path.open("rb") as file:
            raw = file.read(262_145)
        if len(raw) > 262_144:
            raise ValueError("configuration too large")
        settings = Settings.model_validate(tomllib.loads(raw.decode("utf-8")))
        # Explicit environment override supports read-only container mounts.
        root = os.environ.get("VEILGATE_DATA_ROOT")
        if root is not None:
            settings = Settings.model_validate({**settings.model_dump(), "data_root": root})
        return settings
    except (OSError, ValueError, ValidationError):
        raise StartupError("invalid_configuration") from None


def load_tokens(settings: Settings) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for principal in settings.principals:
        token = os.environ.get(principal.token_env, "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token) or token in tokens.values():
            raise StartupError("invalid_credentials")
        tokens[principal.id] = token
    return tokens
