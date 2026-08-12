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
    # A ceiling for the interactive "suggest" calls, which block a request rather
    # than streaming. It must stay well under Cloudflare's 100s idle limit: the
    # 150s HTTP timeout above is LONGER than that, so a hung Corti call would be
    # cut off as a 524 while this server waited another 50 seconds. Measured
    # latency is 2.7-5.5s, so 30s is six times the worst case and still fails
    # cleanly — the professor writes their own, which is the fallback anyway.
    suggest_timeout_seconds: float = 30.0
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

    # --- dictation -------------------------------------------------------
    dictation_enabled: bool = True
    # Corti refuses audio faster than real speed, so a clip costs its own length
    # in wall clock. 90s keeps the wait tolerable and stays well inside the
    # 4000-character narrative ceiling (~4.5 minutes of speech).
    dictation_max_seconds: int = 90
    dictation_max_bytes: int = 8 * 1024 * 1024
    # Corti asks for 250-500ms of audio per frame. Sized in seconds rather than
    # bytes because a fixed byte count is a different duration at every bitrate —
    # and too long a frame means a short clip arrives with no pacing and comes
    # back empty.
    dictation_chunk_seconds: float = 0.4
    # Stays under both documented limits: 64000 bytes of buffering, 1 MB per frame.
    dictation_max_chunk_bytes: int = 48_000
    # 1.0 = real time. Corti warns that faster "may cause buffering issues,
    # degraded results, or stream termination" — raise only after measuring.
    dictation_speed: float = 1.0
    # "en" is English (US). There is no en-IN model; en-GB is a separate one.
    dictation_language: str = "en"

    @property
    def corti_transcribe_url(self) -> str:
        return f"wss://api.{self.corti_environment}.corti.app/audio-bridge/v2/transcribe"

    # --- CORS / paging ---------------------------------------------------
    # The browser origins allowed to call this API. Only needed when the
    # frontend talks to the backend directly (VITE_API_URL set); through the
    # Vite proxy everything is same-origin and never reaches this check.
    cors_origins: tuple[str, ...] = (
        "http://localhost:7205",
        "http://127.0.0.1:7205",
    )
    max_narrative_chars: int = 4000
    default_page_size: int = 25
    max_page_size: int = 100


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings are immutable for the process lifetime, so build them once."""
    return Settings()  # type: ignore[call-arg]
