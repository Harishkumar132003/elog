from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment or `backend/.env`."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    app_name: str = "OpBook360 API"
    api_prefix: str = "/api"

    # --- MongoDB ---------------------------------------------------------
    # Names match the keys already present in .env.
    mongo_uri: str = Field(alias="DB_CONNECTION_STRING")
    mongo_db: str = Field(default="elog", alias="DB")

    # --- Auth ------------------------------------------------------------
    jwt_secret: str = Field(default="dev-only-change-me", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 12

    # --- Corti -----------------------------------------------------------
    corti_client_id: str = Field(alias="OPBOOK_CORTI_CLIENT_ID")
    corti_client_secret: str = Field(alias="OPBOOK_CORTI_CLIENT_SECRET")
    corti_environment: str = Field(default="eu", alias="OPBOOK_CORTI_ENVIRONMENT")
    corti_tenant: str = Field(default="base", alias="OPBOOK_CORTI_TENANT")
    # Generation of a full question set has been measured at ~33s and Corti's
    # latency varies several-fold, so 45s aborted real work and silently
    # downgraded it to the scripted fallback.
    corti_timeout_seconds: float = 150.0
    # Tokens live 300s; refresh early so a call never races the expiry.
    corti_token_skew_seconds: int = 45
    corti_enabled: bool = True

    @property
    def corti_token_url(self) -> str:
        return (
            f"https://auth.{self.corti_environment}.corti.app"
            f"/realms/{self.corti_tenant}/protocol/openid-connect/token"
        )

    @property
    def corti_base_url(self) -> str:
        return f"https://api.{self.corti_environment}.corti.app/v2"

    # --- CORS / paging ---------------------------------------------------
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    max_narrative_chars: int = 4000
    default_page_size: int = 25
    max_page_size: int = 100


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings are immutable for the process lifetime, so build them once."""
    return Settings()  # type: ignore[call-arg]
