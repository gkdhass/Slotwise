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
    # Alembic uses a DDL-capable role; the API/worker use the least-privilege
    # application role in ``url``. When omitted, migrations reuse ``url``
    # (convenient for a single-role local cluster).
    migration_url: str | None = None
    app_role: str = "slotwise_app"
    migration_role: str = "slotwise_migrator"
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=20, ge=0, le=100)
    pool_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    pool_recycle_seconds: int = Field(default=1800, ge=60)
    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    statement_timeout_ms: int = Field(default=15_000, ge=0, le=600_000)
    application_name: str = "slotwise-api"
    echo: bool = False

    @field_validator("url", "migration_url")
    @classmethod
    def _require_async_postgres_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith(("postgresql+asyncpg://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use an async PostgreSQL driver")
        return value

    @property
    def effective_migration_url(self) -> str:
        return self.migration_url or self.url


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
    # ``jwt_secret_key`` is optional so existing deployments keep signing with
    # SECURITY_SECRET_KEY. When set, it becomes the active signing key.
    jwt_secret_key: SecretStr | None = None
    jwt_key_id: str = "dev-1"
    # Rotation: "kid:secret,kid:secret" parsed into a mapping. Old keys stay
    # accepted for verification until the operator removes them.
    jwt_previous_keys: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)
    jwt_issuer: str = "slotwise"
    jwt_audience: str = "slotwise-api"
    jwt_leeway_seconds: int = Field(default=30, ge=0, le=300)
    access_token_expire_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_expire_hours: int = Field(default=8, ge=1, le=168)
    ws_ticket_ttl_seconds: int = Field(default=30, ge=5, le=300)
    max_request_body_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)

    password_min_length: int = Field(default=12, ge=12, le=128)
    argon2_time_cost: int = Field(default=3, ge=1, le=10)
    argon2_memory_cost: int = Field(default=65_536, ge=8192, le=1_048_576)
    argon2_parallelism: int = Field(default=4, ge=1, le=16)

    lockout_threshold: int = Field(default=5, ge=1, le=100)
    lockout_minutes: int = Field(default=15, ge=1, le=1440)

    rate_limit_login_per_minute: int = Field(default=10, ge=1, le=10_000)
    rate_limit_login_account_per_minute: int = Field(default=5, ge=1, le=10_000)
    rate_limit_refresh_per_minute: int = Field(default=20, ge=1, le=10_000)
    rate_limit_ticket_per_minute: int = Field(default=30, ge=1, le=10_000)
    rate_limit_sensor_per_minute: int = Field(default=60, ge=1, le=10_000)

    # ``__Secure-`` (not ``__Host-``): __Host- mandates Path=/ and forbids a
    # Domain attribute, which conflicts with scoping the refresh cookie to the
    # auth path. __Secure- still requires the Secure attribute, so the cookie
    # cannot be sent over plaintext HTTP in production.
    refresh_cookie_name: str = "__Secure-slotwise_refresh"
    refresh_cookie_path: str = "/api/v1/auth"
    refresh_cookie_secure: bool = True
    refresh_cookie_samesite: Literal["strict", "lax", "none"] = "strict"
    csrf_header_name: str = "X-Requested-With"
    csrf_header_value: str = "slotwise-dashboard"

    @field_validator("secret_key")
    @classmethod
    def _secret_not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("SECURITY_SECRET_KEY must not be blank")
        return value

    @field_validator("jwt_previous_keys", mode="before")
    @classmethod
    def _parse_previous_keys(cls, value: object) -> object:
        if isinstance(value, str):
            if not value.strip():
                return {}
            parsed: dict[str, str] = {}
            for part in value.split(","):
                if not part.strip():
                    continue
                kid, separator, secret = part.partition(":")
                if not separator or not kid.strip() or not secret.strip():
                    raise ValueError("SECURITY_JWT_PREVIOUS_KEYS must be 'kid:secret[,kid:secret]'")
                parsed[kid.strip()] = secret.strip()
            return parsed
        return value

    @property
    def active_jwt_secret(self) -> str:
        value = self.jwt_secret_key or self.secret_key
        return value.get_secret_value()

    @property
    def jwt_signing_keys(self) -> dict[str, str]:
        """All accepted verification keys, active key last."""
        keys = dict(self.jwt_previous_keys)
        keys[self.jwt_key_id] = self.active_jwt_secret
        return keys


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


class SeedSettings(_EnvSettings):
    """Bootstrap account settings. The password is never defaulted."""

    model_config = SettingsConfigDict(
        env_prefix="SEED_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    admin_email: str = "admin@slotwise.local"
    admin_password: SecretStr | None = None
    admin_name: str = "Slotwise Administrator"
    demo: bool = False
    # Demo principal passwords. They are only consulted by ``seed --demo`` in a
    # dev/test environment and are never defaulted, so a non-dev deployment
    # cannot silently create a known account.
    analyst_email: str = "analyst@slotwise.local"
    analyst_password: SecretStr | None = None
    viewer_email: str = "viewer@slotwise.local"
    viewer_password: SecretStr | None = None


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
    seed: SeedSettings = Field(default_factory=SeedSettings)

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
        
        # Check for placeholder JWT secret
        jwt_secret = self.security.active_jwt_secret
        if "change-me" in jwt_secret.lower() or jwt_secret == DEV_SECRET_KEY:
            insecure.append("JWT secret (still using placeholder/dev value in production)")
            
        if insecure:
            joined = ", ".join(insecure)
            raise ValueError(
                f"Insecure development defaults are not allowed in {self.app.env}: {joined}"
            )

        if len(self.security.secret_key.get_secret_value()) < 32:
            raise ValueError("SECURITY_SECRET_KEY must be at least 32 characters outside dev")
        if len(self.security.active_jwt_secret) < 32:
            raise ValueError("The JWT signing key must be at least 32 characters outside dev")
        for kid, secret in self.security.jwt_previous_keys.items():
            if len(secret) < 32:
                raise ValueError(f"JWT rotation key {kid!r} is too short outside dev")
        if not self.security.refresh_cookie_secure:
            raise ValueError("SECURITY_REFRESH_COOKIE_SECURE must be true outside dev")
            
        # Require strong admin password outside dev
        if self.seed.admin_password is None:
            raise ValueError("SEED_ADMIN_PASSWORD is required in non-dev environments")
        admin_pwd = self.seed.admin_password.get_secret_value()
        if len(admin_pwd) < self.security.password_min_length:
            raise ValueError(
                f"SEED_ADMIN_PASSWORD must meet password complexity requirements "
                f"(min length {self.security.password_min_length})"
            )
            
        # Require explicit CORS origin allow-list outside dev
        if not self.app.cors_origins or self.app.cors_origins == ["http://localhost:5173", "https://localhost"]:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must be explicitly set in non-dev environments "
                "(APP_CORS_ORIGINS environment variable)"
            )
            
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
