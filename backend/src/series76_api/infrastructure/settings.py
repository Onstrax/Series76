"""Application settings read from the environment (Spec 3, Req 12.3).

Uses ``pydantic-settings`` so every value comes from the environment or an
``.env`` file — no secret is committed to source or baked into the image. The
KEK is read here but is never persisted to PostgreSQL (design: DEK/KEK).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime configuration for the API and worker processes.

    All fields have env-overridable names. Secrets (``kek_base64``,
    ``openrouter_api_key``, ``gemini_api_key``) default to empty so the
    processes can start even when a provider is unreachable; readiness reflects
    degraded dependencies rather than crashing (Req 12.5).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database (app connects as app_writer; migrations use a privileged URL).
    database_url: str = Field(
        default="postgresql+psycopg://series76_app:CHANGE_ME@localhost:5432/series76",
        alias="DATABASE_URL",
    )

    # --- Crypto: the Key-Encryption-Key, held OUTSIDE the database. ---
    # ``ENCRYPTION_KEK`` is the canonical name in the design; we also accept the
    # pre-existing ``KEK_BASE64`` placeholder. Base64 of 32 random bytes.
    kek_base64: str = Field(default="", alias="ENCRYPTION_KEK")
    kek_base64_legacy: str = Field(default="", alias="KEK_BASE64")

    # --- Auth / token policy. ---
    auth_token_policy: str = Field(default="opaque-sha256", alias="AUTH_TOKEN_POLICY")
    access_token_ttl_seconds: int = Field(default=900, alias="ACCESS_TOKEN_TTL_SECONDS")
    refresh_token_ttl_seconds: int = Field(
        default=1209600, alias="REFRESH_TOKEN_TTL_SECONDS"
    )

    # --- Agent / LLM (faked in CI; declared for config completeness). ---
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    agent_model: str = Field(default="", alias="AGENT_MODEL")
    interpreter_model: str = Field(default="", alias="INTERPRETER_MODEL")
    answer_model: str = Field(default="", alias="ANSWER_MODEL")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")

    # --- Queue / cost / time limits (Half B honors these; declared here). ---
    pending_job_cap: int = Field(default=5, ge=1, le=100, alias="PENDING_JOB_CAP")
    job_lease_seconds_min: int = Field(default=30, alias="JOB_LEASE_SECONDS_MIN")
    job_lease_seconds_max: int = Field(default=120, alias="JOB_LEASE_SECONDS_MAX")
    turn_budget_usd: float = Field(default=0.50, alias="TURN_BUDGET_USD")
    turn_timeout_seconds: int = Field(default=120, alias="TURN_TIMEOUT_SECONDS")

    def resolve_kek_base64(self) -> str:
        """Return the configured KEK (base64), preferring ``ENCRYPTION_KEK``.

        Returns an empty string when no KEK is configured; callers that need
        key material must fail closed (:class:`KeyUnavailableError`).
        """

        return self.kek_base64 or self.kek_base64_legacy


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance (composition-root singleton)."""

    return Settings()


__all__ = ["Settings", "get_settings"]
