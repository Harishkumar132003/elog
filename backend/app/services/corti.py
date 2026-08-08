"""Corti API client.

Auth is OAuth2 client-credentials against a Keycloak realm; access tokens live
only 300 seconds, so the token is cached in-process and refreshed slightly ahead
of expiry behind a lock (otherwise every concurrent request would refresh).

Every call needs both `Authorization` and `Tenant-Name`. Generation requests also
send `X-Corti-Retention-Policy: none` so no case text is persisted on Corti's side.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


class CortiError(RuntimeError):
    """Any failure talking to Corti. Callers are expected to fall back."""


class CortiClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self._expires_at: datetime = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()

    # --- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=_settings.corti_base_url,
                timeout=_settings.corti_timeout_seconds,
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise CortiError("Corti client not started")
        return self._client

    # --- auth ------------------------------------------------------------
    async def _access_token(self) -> str:
        async with self._lock:
            if self._token and datetime.now(UTC) < self._expires_at:
                return self._token

            try:
                response = await self._http.post(
                    _settings.corti_token_url,
                    data={
                        "grant_type": "client_credentials",
                        "scope": "openid",
                        "client_id": _settings.corti_client_id,
                        "client_secret": _settings.corti_client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise CortiError(f"Corti auth failed: {exc}") from exc

            self._token = payload["access_token"]
            lifetime = int(payload.get("expires_in", 300))
            self._expires_at = datetime.now(UTC) + timedelta(
                seconds=max(30, lifetime - _settings.corti_token_skew_seconds)
            )
            return self._token

    async def _headers(self, **extra: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._access_token()}",
            "Tenant-Name": _settings.corti_tenant,
            "Content-Type": "application/json",
            **extra,
        }

    async def _post(self, path: str, body: dict[str, Any], **extra: str) -> dict[str, Any]:
        try:
            response = await self._http.post(
                path, json=body, headers=await self._headers(**extra)
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise CortiError(
                f"Corti {path} returned {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise CortiError(f"Corti {path} failed: {exc}") from exc

    # --- api -------------------------------------------------------------
    async def extract_facts(self, text: str, language: str = "en") -> list[dict[str, str]]:
        """Grouped clinical facts from free text."""
        payload = await self._post(
            "/tools/extract-facts",
            {"context": [{"type": "text", "text": text}], "outputLanguage": language},
            **{"X-Corti-Retention-Policy": "none"},
        )
        return payload.get("facts", [])

    async def create_section(
        self,
        name: str,
        heading: str,
        content_prompt: str,
        output_schema: dict[str, Any],
    ) -> str:
        payload = await self._post(
            "/documents/sections/",
            {
                "name": name,
                "generation": {
                    "heading": heading,
                    "instructions": {"contentPrompt": content_prompt},
                    "outputSchema": output_schema,
                },
            },
        )
        return payload["id"]

    async def create_template(
        self, name: str, prompt: str, section_ids: list[str]
    ) -> str:
        payload = await self._post(
            "/documents/templates/",
            {
                "name": name,
                "languages": ["en"],
                "publish": True,
                "generation": {
                    "instructions": {"prompt": prompt},
                    "sections": [
                        {"sectionId": section_id, "orderIndex": index}
                        for index, section_id in enumerate(section_ids)
                    ],
                },
            },
        )
        return payload["id"]

    async def generate(
        self, template_id: str, context_blocks: list[str], language: str = "en"
    ) -> dict[str, Any]:
        """Run a stored template. Returns `structuredDocument`, keyed by sectionId."""
        payload = await self._post(
            "/documents/",
            {
                "outputLanguage": language,
                "templateRef": {"templateId": template_id},
                "context": [{"type": "text", "text": block} for block in context_blocks],
            },
            **{"X-Corti-Retention-Policy": "none"},
        )
        return payload.get("document", {}).get("structuredDocument", {}) or {}


corti = CortiClient()
