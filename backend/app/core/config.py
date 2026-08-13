from functools import lru_cache

from pydantic import Field, model_validator
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

    # --- which engine writes the text ------------------------------------
    # "corti" is the product; "openai" exists so development can continue when
    # the Corti account is unavailable. The six text features switch together —
    # dictation does not, because it is a Corti WebSocket rather than a template.
    ai_provider: str = Field(default="corti", alias="OPBOOK_AI_PROVIDER")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    # Overridable so the same client reaches Azure OpenAI or a local gateway.
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", alias="OPENAI_BASE_URL"
    )
    # One call per feature and no streaming, so this is a plain ceiling. Kept
    # under Cloudflare's 100s idle limit for the same reason the suggest
    # timeouts are.
    openai_timeout_seconds: float = 60.0

    @property
    def uses_openai(self) -> bool:
        return self.ai_provider.strip().lower() == "openai"

    # --- Corti -----------------------------------------------------------
    # Blank-defaulted rather than required, so a machine with only an OpenAI key
    # can boot. Still enforced below when Corti is the active provider — the
    # loudness moves, it does not go away.
    corti_client_id: str = Field(default="", alias="OPBOOK_CORTI_CLIENT_ID")
    corti_client_secret: str = Field(default="", alias="OPBOOK_CORTI_CLIENT_SECRET")
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
    # The same reasoning for the question builder, which writes ONE question per
    # press and so blocks the request. A full set of three has been measured at
    # ~33s, so a single question is roughly a third of that; 45s is a wide margin
    # that still returns the scripted question rather than a 524.
    question_timeout_seconds: float = 45.0
    corti_enabled: bool = True

    # --- identities ------------------------------------------------------
    # Five fixed users picked from a header dropdown, no password. Turning this
    # off closes `/auth/switch` and leaves `/auth/login` as the only way in, so
    # this can never be live by accident in a real deployment.
    demo_identities: bool = True

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

    @model_validator(mode="after")
    def _check_provider(self) -> "Settings":
        """Refuse to start on a provider that cannot possibly work.

        Every AI call in this app degrades to a rule-based answer rather than
        failing, which is right at runtime and wrong at boot: a missing key would
        show up as bland questions and zero marks days later, not as an error.
        The whole point of the switch is to escape that state, so landing back in
        it silently is the one outcome worth refusing.
        """
        provider = self.ai_provider.strip().lower()
        if provider not in {"corti", "openai"}:
            raise ValueError(
                f"OPBOOK_AI_PROVIDER must be 'corti' or 'openai', not {self.ai_provider!r}"
            )
        if provider == "openai" and not self.openai_api_key.strip():
            raise ValueError(
                "OPBOOK_AI_PROVIDER=openai needs OPENAI_API_KEY set in backend/.env"
            )
        if provider == "corti" and not (self.corti_client_id and self.corti_client_secret):
            raise ValueError(
                "OPBOOK_CORTI_CLIENT_ID and OPBOOK_CORTI_CLIENT_SECRET are required "
                "when OPBOOK_AI_PROVIDER is 'corti' (the default). Set "
                "OPBOOK_AI_PROVIDER=openai to develop without them."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings are immutable for the process lifetime, so build them once."""
    return Settings()  # type: ignore[call-arg]
