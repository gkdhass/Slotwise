"""Typed application settings.

Security notes:
- Every secret is sourced from the environment (or a developer .env file).
- The literals below are *development sentinels*, never usable outside ``dev``/``test``.
- Settings are deliberately grouped so later phases can add fields without leaking
  unrelated configuration into a service.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Non-production sentinels. Any environment other than dev/test rejects these.
# bandit: these are not credentials; they are deliberately invalid placeholders.
DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me"  # noqa: S105  # nosec B105
DEV_MINIO_SECRET_KEY = "dev-only-minio-password-change-me"  # noqa: S105  # nosec B105

Environment = Literal["dev", "test", "staging", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_ENV_FILES = (".env", "../.env")


class _EnvSettings(BaseSettings):
    """Common environment-file behaviour for every settings group."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


class AppSettings(_EnvSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    name: str = "Slotwise"
    env: Environment = "dev"
    version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    log_level: LogLevel = "INFO"
    debug: bool = False
    docs_enabled: bool = True
    dependency_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver", "api", "nginx"]
    )
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "https://localhost"]
    )

    @field_validator("allowed_hosts", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @property
    def is_dev_like(self) -> bool:
        return self.env in {"dev", "test"}


class DatabaseSettings(_EnvSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    url: str = "postgresql+asyncpg://slotwise:change-me@postgres:5432/slotwise"
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=20, ge=0, le=100)
    pool_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    pool_recycle_seconds: int = Field(default=1800, ge=60)
    echo: bool = False

    @field_validator("url")
    @classmethod
    def _require_async_postgres_url(cls, value: str) -> str:
        if not value.startswith(("postgresql+asyncpg://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use an async PostgreSQL driver")
        return value


class RedisSettings(_EnvSettings):
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    url: str = "redis://redis:6379/0"
    socket_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    queue_names: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["celery"])
    queue_depth_refresh_seconds: float = Field(default=15.0, ge=5, le=300)

    @field_validator("url")
    @classmethod
    def _require_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("REDIS_URL must be a redis://, rediss:// or unix:// URL")
        return value

    @field_validator("queue_names", mode="before")
    @classmethod
    def _split_queue_names(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


class OpenSearchSettings(_EnvSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPENSEARCH_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    url: str = "http://opensearch:9200"
    username: str | None = None
    password: SecretStr | None = None
    index_prefix: str = "slotwise"
    verify_certs: bool = True
    timeout_seconds: float = Field(default=3.0, gt=0, le=30)


class MinioSettings(_EnvSettings):
    model_config = SettingsConfigDict(
        env_prefix="MINIO_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    endpoint: str = "http://minio:9000"
    access_key: str = "slotwise"
    secret_key: SecretStr = SecretStr(DEV_MINIO_SECRET_KEY)
    bucket: str = "slotwise-artifacts"
    secure: bool = False
    timeout_seconds: float = Field(default=3.0, gt=0, le=30)


class MLflowSettings(_EnvSettings):
    model_config = SettingsConfigDict(
        env_prefix="MLFLOW_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    tracking_uri: str = "http://mlflow:5000"
    experiment_name: str = "slotwise"
    health_path: str = "/health"
    timeout_seconds: float = Field(default=3.0, gt=0, le=30)


class SecuritySettings(_EnvSettings):
    model_config = SettingsConfigDict(
        env_prefix="SECURITY_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    secret_key: SecretStr = SecretStr(DEV_SECRET_KEY)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=120)
    max_request_body_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)

    @field_validator("secret_key")
    @classmethod
    def _secret_not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("SECURITY_SECRET_KEY must not be blank")
        return value


class FeatureSettings(_EnvSettings):
    """Feature gates.

    The Phase 1 contract mandates the flat names MODULE_B_ENABLED and
    ALLOW_SELF_APPROVAL, so this group intentionally uses no environment prefix.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    module_b_enabled: bool = False
    allow_self_approval: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    mlflow: MLflowSettings = Field(default_factory=MLflowSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    features: FeatureSettings = Field(default_factory=FeatureSettings)

    @model_validator(mode="after")
    def _reject_development_secrets_outside_dev(self) -> Settings:
        if self.app.is_dev_like:
            return self

        insecure: list[str] = []
        if self.security.secret_key.get_secret_value() == DEV_SECRET_KEY:
            insecure.append("SECURITY_SECRET_KEY")
        if self.minio.secret_key.get_secret_value() == DEV_MINIO_SECRET_KEY:
            insecure.append("MINIO_SECRET_KEY")
        if "change-me" in self.database.url or "slotwise:slotwise@" in self.database.url:
            insecure.append("DATABASE_URL")
        if insecure:
            joined = ", ".join(insecure)
            raise ValueError(
                f"Insecure development defaults are not allowed in {self.app.env}: {joined}"
            )

        if len(self.security.secret_key.get_secret_value()) < 32:
            raise ValueError("SECURITY_SECRET_KEY must be at least 32 characters outside dev")
        return self

    @property
    def features_enabled(self) -> FeatureSettings:
        """Read-only accessor kept explicit for feature-gating call sites."""
        return self.features


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide validated settings.

    Validation happens on first use, which makes bad production configuration
    fail fast at startup instead of surfacing on the first request.
    """
    return Settings()


def reset_settings_cache() -> None:
    """Test helper; production code never needs to reset settings."""
    get_settings.cache_clear()
