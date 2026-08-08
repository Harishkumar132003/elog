"""Read a curriculum PDF and pull the competency statements out of it.

    bytes -> pypdf text -> excerpts -> Corti (concurrently) -> clean -> dedupe

The professor picks the subject before uploading, so nothing here has to work out
which subject a statement belongs to — only what the statements are.

Extraction returns one free-string array per excerpt (see `EXTRACT_TEMPLATE`), so
an excerpt yields as many competencies as it contains rather than a fixed number
of slots. What comes back is a *proposal*: it lands in the Configuration editor for
the professor to correct before anything is saved. That is why this leans towards
returning too much rather than too little — a wrong row is one click to remove, a
missing one is invisible.

The PDF itself is never stored. Text is extracted from the uploaded bytes and the
bytes are dropped.
"""

from __future__ import annotations

import asyncio
import logging
import re
from io import BytesIO
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.corti_templates import EXTRACT_TEMPLATE, run_template

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 80
# Excerpts are generous because one array section has no per-excerpt limit; the
# ceiling is how much text Corti reads well in one pass, not how many slots exist.
CHUNK_CHARS = 6000
CHUNK_OVERLAP = 400
MAX_CHUNKS = 40
CONCURRENCY = 4

# A competency is a sentence about doing something. These bounds drop page
# headers, bare topic names and stray table cells without needing a model.
MIN_TITLE = 15
MAX_TITLE = 220


class ImportError_(Exception):
    """A problem with the upload the professor can act on."""


def read_pdf_text(data: bytes) -> tuple[str, int, int]:
    """Extract text from PDF bytes. Returns (text, pages_read, pages_total)."""
    if not data.startswith(PDF_MAGIC):
        raise ImportError_("That file is not a PDF.")
    if len(data) > MAX_BYTES:
        raise ImportError_(f"That PDF is larger than {MAX_BYTES // (1024 * 1024)} MB.")

    try:
        reader = PdfReader(BytesIO(data))
        total = len(reader.pages)
        pages = [(page.extract_text() or "") for page in reader.pages[:MAX_PAGES]]
    except (PdfReadError, ValueError, OSError) as exc:
        raise ImportError_(f"That PDF could not be read: {exc}") from exc

    text = "\n".join(pages)
    if len(text.strip()) < 200:
        # Almost always a scan. Saying "0 competencies found" would blame the
        # document's content for what is really a missing text layer.
        raise ImportError_(
            "This PDF has no text in it — it looks like a scan of a printed page. "
            "Text recognition is not available, so try a text-based PDF."
        )
    return text, min(total, MAX_PAGES), total


def chunk(text: str) -> tuple[list[str], bool]:
    """Split into overlapping excerpts on line boundaries.

    Overlap matters because a competency that straddles a boundary would otherwise
    be truncated in both excerpts and cleaned away by the length filter.
    Returns (chunks, truncated).
    """
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        current.append(line)
        size += len(line) + 1
        if size >= CHUNK_CHARS:
            chunks.append("\n".join(current))
            tail, kept = [], 0
            for previous in reversed(current):
                if kept >= CHUNK_OVERLAP:
                    break
                tail.append(previous)
                kept += len(previous) + 1
            current = list(reversed(tail))
            size = kept
    if current:
        chunks.append("\n".join(current))

    return chunks[:MAX_CHUNKS], len(chunks) > MAX_CHUNKS


_LEADING_NUMBER = re.compile(r"^\s*(?:\(?[0-9]+(?:\.[0-9]+)*\)?|\(?[a-zA-Z]\)|[-–—•*·])\s+")
_WHITESPACE = re.compile(r"\s+")


def clean_title(raw: str) -> str | None:
    """Normalise one extracted line, or reject it."""
    title = _WHITESPACE.sub(" ", str(raw or "")).strip()
    # Numbering sometimes survives the prompt; strip it repeatedly for "2.1 (a) …".
    for _ in range(3):
        stripped = _LEADING_NUMBER.sub("", title)
        if stripped == title:
            break
        title = stripped
    title = title.strip(" .;:-–—").strip()

    if not (MIN_TITLE <= len(title) <= MAX_TITLE):
        return None
    if " " not in title:
        return None
    letters = [character for character in title if character.isalpha()]
    # A heading shouts; a competency statement does not.
    if letters and sum(character.isupper() for character in letters) / len(letters) > 0.7:
        return None
    return title[0].upper() + title[1:]


def dedupe_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


async def _extract_chunk(excerpt: str, index: int) -> list[str]:
    try:
        fields = await run_template(EXTRACT_TEMPLATE, [excerpt])
    except Exception:
        # One bad excerpt out of forty must not lose the other thirty-nine.
        logger.exception("Competency extraction failed for excerpt %s", index)
        return []
    if not fields:
        return []
    found = fields.get("competencies")
    return [str(item) for item in found] if isinstance(found, list) else []


async def extract(
    text: str,
    known: set[str],
    on_progress: Any = None,
) -> tuple[list[str], bool]:
    """Competency titles found in `text`, minus anything already in `known`.

    `known` holds dedupe keys for the subject's existing catalogue, so a re-import
    proposes only what is genuinely new.
    """
    excerpts, truncated = chunk(text)
    limiter = asyncio.Semaphore(CONCURRENCY)
    done = 0
    lock = asyncio.Lock()

    async def run(excerpt: str, index: int) -> list[str]:
        nonlocal done
        async with limiter:
            result = await _extract_chunk(excerpt, index)
        async with lock:
            done += 1
            if on_progress:
                await on_progress(done, len(excerpts))
        return result

    batches = await asyncio.gather(*(run(excerpt, i) for i, excerpt in enumerate(excerpts)))

    # Order follows the document, so the professor reviews the list in the order
    # they would read the curriculum.
    seen = set(known)
    titles: list[str] = []
    for batch in batches:
        for raw in batch:
            title = clean_title(raw)
            if title is None:
                continue
            key = dedupe_key(title)
            if key in seen:
                continue
            seen.add(key)
            titles.append(title)

    return titles, truncated
