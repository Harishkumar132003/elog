import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.constants import Subject
from app.db import mongo
from app.services import catalogue, openai_client, people
from app.services.corti import corti
from app.services.corti_templates import ensure_template, parse_template

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Held so the warm-up task is not garbage collected mid-flight.
_warmup: asyncio.Task | None = None


async def _warm_parse_templates() -> None:
    """Provision each subject's parse template, off the boot path.

    There is one template per subject now, because the competency enum is that
    subject's catalogue. Provisioning all five takes ~35 HTTP calls, which is far
    too long to hold up start-up — but doing it in the background still spares the
    first resident to press Analyse. A failure is not fatal: everything falls back
    to rules.

    OpenAI has nothing to provision — its schema is composed per call — so there
    is no warm-up to run.
    """
    if settings.uses_openai:
        return

    for subject in Subject:
        template = await ensure_template(parse_template(subject.value))
        logger.info(
            "Corti parse template [%s]: %s",
            subject.value,
            template["template_id"] if template else "unavailable (rule-based fallback active)",
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _warmup
    await mongo.connect()

    # One provider writes the text; the other's client is never started, so a
    # missing credential for the unused one cannot cost a connection.
    if settings.uses_openai:
        await openai_client.start()
        logger.info(
            "AI provider: openai (model %s) — Corti is not in use for generation",
            settings.openai_model,
        )
    else:
        await corti.start()
        logger.info("AI provider: corti (tenant %s)", settings.corti_tenant)

    # An empty catalogue gets the specification's five competencies; a loaded one
    # is left alone. Must run before any template is built from it.
    await catalogue.seed_if_empty()

    # The header offers five identities and expects all five to exist. Cheap,
    # idempotent, and on the boot path deliberately: a missing identity is a
    # dead dropdown entry, not something to discover on first click.
    if settings.demo_identities:
        await people.seed()

    _warmup = asyncio.create_task(_warm_parse_templates())

    yield

    if _warmup is not None:
        _warmup.cancel()
    await corti.close()
    await openai_client.close()
    await mongo.close()


app = FastAPI(
    title=settings.app_name,
    version="1.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
