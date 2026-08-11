"""Voice input for the case narrative.

The resident records a clip in the browser and posts it here; this relays it to
Corti's speech service and streams the words back as they land.

It has to be a stream rather than one long request. Corti refuses audio faster
than real speed, so a 90-second clip costs 90 seconds of wall clock — long enough
for Cloudflare (100s of silence) and nginx (60s between reads) to cut a quiet
connection. A heartbeat every few seconds removes the silence, which is the same
trick `/entries/parse/stream` already relies on.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser
from app.api.sse import HEARTBEAT_SECONDS, STREAM_HEADERS, sse
from app.core.config import get_settings
from app.services.corti import CortiError, corti

router = APIRouter(prefix="/dictation", tags=["dictation"])
logger = logging.getLogger(__name__)
_settings = get_settings()

# What a browser's MediaRecorder actually produces. Anything else is passed
# through unlabelled and left to Corti's own detection.
_KNOWN_FORMATS = ("audio/webm", "audio/ogg", "audio/mp4", "audio/m4a", "audio/mpeg", "audio/wav")

# Corti attaches a segment to nothing when it cannot punctuate the join, so the
# client stitches. These need no leading space.
_LEFT_ATTACHING = ",.:;!?)]}%"
_OPENERS = "([{"


def _normalise_format(mime_type: str | None) -> str | None:
    """Keep the container, drop the codec parameter where Corti disallows it."""
    if not mime_type:
        return None
    base = mime_type.split(";")[0].strip().lower()
    if base not in _KNOWN_FORMATS:
        return None
    # Codec parameters are only accepted on ogg and webm.
    if base in ("audio/webm", "audio/ogg") and "codecs=" in mime_type.lower():
        return mime_type.strip()
    return base


def _join(segments: list[str]) -> str:
    """Stitch Corti's segments into one paragraph.

    Corti publishes the rule rather than doing it: a space between segments,
    unless the next one opens with punctuation that attaches to the left.
    """
    out = ""
    for segment in segments:
        piece = segment.strip()
        if not piece:
            continue
        if out and piece[0] not in _LEFT_ATTACHING and out[-1] not in _OPENERS:
            out += " "
        out += piece
    return out


async def _read_upload(audio: UploadFile, limit: int) -> bytes:
    """Read the clip without trusting the declared length.

    `await audio.read()` with no bound would let a crafted request allocate
    whatever it liked, so the cap is enforced as the bytes arrive.
    """
    chunks: list[bytes] = []
    size = 0
    while chunk := await audio.read(64 * 1024):
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "That recording is too large"
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _events(audio: bytes, mime_type: str | None, seconds: float) -> AsyncIterator[bytes]:
    """Relay the clip, emitting words as they arrive and a pulse in between."""
    started = time.monotonic()
    # Keyed on the segment's own start time: Corti may resend a segment after the
    # end signal, and its guidance is that `start` is the identity, last one wins.
    finals: dict[float, str] = {}
    live = ""
    truncated = False

    async def snapshot() -> str:
        ordered = [finals[key] for key in sorted(finals)]
        return _join([*ordered, live] if live else ordered)

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for message in corti.transcribe(
                audio, mime_type=mime_type, seconds=seconds
            ):
                await queue.put(message)
        finally:
            await queue.put(None)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                # Nothing from Corti for a while: say so, so the connection is
                # never silent long enough for a proxy to give up on it.
                elapsed = time.monotonic() - started
                yield sse(
                    "status",
                    {"elapsed": round(elapsed, 1), "progress": min(elapsed / seconds, 1.0)},
                )
                continue

            if message is None:
                break
            if message["kind"] == "final":
                finals[message.get("start") or time.monotonic()] = message["text"]
                live = ""
            elif message["kind"] == "interim":
                live = message["text"]
            else:
                continue
            yield sse("partial", {"text": await snapshot()})

        # Surface a relay failure that the queue would otherwise swallow.
        if task.done() and (error := task.exception()):
            raise error

        live = ""
        text = await snapshot()
        if len(text) > _settings.max_narrative_chars:
            text = text[: _settings.max_narrative_chars].rsplit(" ", 1)[0]
            truncated = True
        yield sse(
            "result",
            {
                "text": text,
                "truncated": truncated,
                # Not an error — a recording with no speech in it is a thing that
                # happens, and "we didn't catch anything" is the honest reply.
                "reason": None if text else "no_speech",
            },
        )
    except asyncio.CancelledError:
        # The resident navigated away. Corti bills per session, so stop it.
        raise
    except CortiError as exc:
        logger.warning("Dictation failed: %s", exc)
        yield sse("error", {"detail": str(exc)})
    except Exception:
        logger.exception("Unexpected dictation failure")
        yield sse("error", {"detail": "Could not transcribe that recording"})
    finally:
        task.cancel()
        with contextlib.suppress(BaseException):
            await task


@router.post("/transcribe")
async def transcribe(
    user: CurrentUser,
    audio: Annotated[UploadFile, File()],
    duration_ms: Annotated[int, Form()],
    mime_type: Annotated[str | None, Form()] = None,
) -> StreamingResponse:
    """Turn one recorded clip into text, streaming it back as it is produced."""
    # Everything cheap fails as an ordinary HTTP error. Once the stream opens the
    # status code is already sent and problems can only be reported inside it.
    if not (_settings.corti_enabled and _settings.dictation_enabled):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Voice input is unavailable right now"
        )

    seconds = duration_ms / 1000
    if seconds > _settings.dictation_max_seconds:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Recordings are limited to {_settings.dictation_max_seconds} seconds",
        )

    clip = await _read_upload(audio, _settings.dictation_max_bytes)
    if not clip:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That recording was empty")

    return StreamingResponse(
        _events(clip, _normalise_format(mime_type), max(seconds, 0.5)),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
