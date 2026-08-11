"""Corti API client.

Auth is OAuth2 client-credentials against a Keycloak realm; access tokens live
only 300 seconds, so the token is cached in-process and refreshed slightly ahead
of expiry behind a lock (otherwise every concurrent request would refresh).

Every call needs both `Authorization` and `Tenant-Name`. Generation requests also
send `X-Corti-Retention-Policy: none` so no case text is persisted on Corti's side.

Speech-to-text is the exception to "this is a REST client": `/transcribe` is a
WebSocket. It lives here anyway, because its connect URL carries the access token
and this module is the only place that token is allowed to exist.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from websockets.asyncio.client import connect as ws_connect

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

    # --- speech to text --------------------------------------------------
    # `/transcribe` is a WebSocket, not REST, and it is stateless: no interaction
    # or recording object is created on Corti's side. It lives on this class
    # rather than in its own module because the connect URL carries the access
    # token, and `_access_token` is deliberately private to this file.

    def _transcribe_url(self, token: str) -> str:
        # quote_plus would render the space in "Bearer xxx" as '+'; Corti's own
        # example uses %20, so force plain quoting.
        query = urlencode(
            {"tenant-name": _settings.corti_tenant, "token": f"Bearer {token}"},
            quote_via=quote,
        )
        return f"{_settings.corti_transcribe_url}?{query}"

    async def _send_audio(
        self, socket: Any, audio: bytes, seconds: float | None
    ) -> None:
        """Feed the clip through at roughly the speed it was spoken.

        Corti: "Streaming audio faster than real time is not recommended and may
        cause buffering issues, degraded results, or stream termination." So the
        pace is deliberate, and measured against the wall clock rather than a
        fixed sleep, so send-time jitter cannot accumulate into a drift.
        """
        total = len(audio)
        # Opus is near constant-bitrate, so bytes map linearly enough to seconds.
        # This is a rate limit, not a synchronisation contract.
        per_byte = (seconds / total) if seconds and total else (1 / 4000)
        speed = max(0.5, _settings.dictation_speed)

        # Chunk by DURATION, not by a fixed byte count. Corti asks for 250-500ms
        # per frame; a flat 32 KB is roughly eight seconds of Opus, which sends a
        # short clip in one burst with no pacing at all — and Corti returns an
        # empty transcript for it. Measured: 5s clips came back silent, 15s did not.
        chunk = int(_settings.dictation_chunk_seconds / per_byte) if per_byte else 4096
        chunk = max(1024, min(chunk, _settings.dictation_max_chunk_bytes))
        # The first frame has to carry the container header for Corti to identify
        # the format, so it is never one of the small ones.
        first = min(max(chunk, 8192), total)

        loop = asyncio.get_running_loop()
        started = loop.time()
        offset = 0
        while offset < total:
            size = first if offset == 0 else chunk
            await socket.send(audio[offset : offset + size])
            offset = min(offset + size, total)
            if offset >= total:
                break
            behind = (offset * per_byte / speed) - (loop.time() - started)
            if behind > 0:
                await asyncio.sleep(behind)

        # Never just close: "Ungraceful disconnection may result in incomplete
        # transcripts or lost final results."
        await socket.send(json.dumps({"type": "end"}))

    async def transcribe(
        self,
        audio: bytes,
        *,
        mime_type: str | None = None,
        seconds: float | None = None,
        language: str | None = None,
        keyterms: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Relay one recorded clip through `/transcribe`.

        Yields `{"kind": "interim"|"final"|"event", ...}` as Corti produces them.
        Raises `CortiError` on any failure; callers fall back to typing.
        """
        configuration: dict[str, Any] = {
            "primaryLanguage": language or _settings.dictation_language,
            "interimResults": True,
            # NOT spokenPunctuation — that means the speaker says the word
            # "comma", and it silently overrides this one when both are set.
            "automaticPunctuation": True,
        }
        if mime_type:
            # Corti warns that auto-detection "can fail silently on unsupported
            # formats", so the browser's own mimeType is passed through.
            configuration["audioFormat"] = mime_type
        if keyterms:
            configuration["keyterms"] = {"terms": [{"term": t} for t in keyterms[:1000]]}

        url = self._transcribe_url(await self._access_token())
        try:
            socket = await ws_connect(
                url,
                additional_headers={"X-Corti-Retention-Policy": "none"},
                open_timeout=15,
                close_timeout=10,
                ping_interval=20,
                max_size=2**20,
            )
        except Exception as exc:
            # The URL holds a live bearer token and this app logs at INFO, so the
            # exception is never allowed to carry it into the log.
            raise CortiError(f"Could not open the transcription stream: {type(exc).__name__}") from None

        async with socket:
            await socket.send(json.dumps({"type": "config", "configuration": configuration}))
            try:
                ack = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
            except (TimeoutError, ValueError) as exc:
                raise CortiError("The transcription service did not accept the request") from exc
            if ack.get("type") != "CONFIG_ACCEPTED":
                raise CortiError(f"Transcription rejected: {ack.get('type', 'unknown')}")

            pump = asyncio.create_task(self._send_audio(socket, audio, seconds))
            try:
                async for raw in socket:
                    if isinstance(raw, bytes):
                        continue
                    message = json.loads(raw)
                    kind = message.get("type")
                    if kind == "transcript":
                        data = message.get("data", {})
                        yield {
                            "kind": "final" if data.get("isFinal") else "interim",
                            "start": data.get("start"),
                            "text": data.get("text") or "",
                        }
                    elif kind == "audioEvent":
                        yield {"kind": "event", "data": message.get("data", {})}
                    elif kind == "ended":
                        break
                    elif kind == "error":
                        raise CortiError(str(message.get("error", {}).get("details", "failed")))
                    elif isinstance(kind, str) and kind.startswith("CONFIG_"):
                        raise CortiError(f"Transcription rejected: {kind}")
                    # usage / delta_usage / flushed are informational
                # Surface a send failure that the read loop would otherwise mask.
                if pump.done() and pump.exception():
                    raise CortiError("The transcription stream dropped") from pump.exception()
            finally:
                pump.cancel()
                with contextlib.suppress(BaseException):
                    await pump


corti = CortiClient()
