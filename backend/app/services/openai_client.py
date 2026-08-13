"""OpenAI as a stand-in generation provider, for development.

Corti is the product; this exists so work can continue when that account is
unavailable. It is deliberately a *translation* rather than a second design: the
template specs in `corti_templates.py` describe what to generate, and this module
renders one of them as a single structured-output request.

The translation is nearly free because Corti's section schemas are already JSON
Schema. Where Corti provisions a template of N sections and returns a value per
`sectionId`, this composes the same N sections into one object schema and gets
them back in one call — so `run_template` hands back an identical
`{key: value}` mapping either way, and no caller can tell the difference.

Two deliberate constraints:

* **The flat section shape is kept.** Corti cannot return objects, which is why
  question generation uses `q1_prompt` / `q1_cognitive` / `q1_affective` rather
  than an array. OpenAI could express that better, but matching the existing
  shape means one parsing path, one set of fallbacks, and output directly
  comparable between the two providers.
* **Strict mode requires every field**, so "nothing found" arrives as an empty
  string — which the section prompts already ask for and `run_template` already
  filters out.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.corti import AiError

logger = logging.getLogger(__name__)
_settings = get_settings()

_client: httpx.AsyncClient | None = None


async def start() -> None:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=_settings.openai_base_url.rstrip("/"),
            timeout=_settings.openai_timeout_seconds,
            headers={"Authorization": f"Bearer {_settings.openai_api_key}"},
        )


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _http() -> httpx.AsyncClient:
    if _client is None:
        raise AiError("OpenAI client not started")
    return _client


def _schema_for(spec: dict[str, Any]) -> dict[str, Any]:
    """One object with a property per section.

    `strict` demands that every property is listed in `required` and that
    `additionalProperties` is false, so the model cannot omit a field or invent
    one — the same closure Corti's per-section schemas gave us.
    """
    sections = spec["sections"]
    return {
        "type": "object",
        "properties": {section["key"]: dict(section["schema"]) for section in sections},
        "required": [section["key"] for section in sections],
        "additionalProperties": False,
    }


def _instructions(spec: dict[str, Any]) -> str:
    """The template prompt, then each section's own prompt against its field name.

    Corti attaches a `contentPrompt` to every section and generates them
    separately. Here they share one call, so each instruction has to name the
    field it governs or the model has no way to tell them apart.
    """
    lines = [spec["prompt"], "", "Return one JSON object with these fields:"]
    for section in spec["sections"]:
        lines.append(f"\n- `{section['key']}` — {section['heading']}\n  {section['prompt']}")
    lines += [
        "",
        "Every field must be present. Where a field's instruction says to return "
        "an empty string or an empty list when there is nothing to report, do "
        "exactly that rather than inventing a value or omitting the field.",
    ]
    return "\n".join(lines)


def _schema_name(spec: dict[str, Any]) -> str:
    """OpenAI accepts `[A-Za-z0-9_-]` here; the spec names already comply."""
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in str(spec["name"]))[:64]


async def generate(spec: dict[str, Any], context_blocks: list[str]) -> dict[str, Any] | None:
    """Run one template spec. Returns values keyed by our own section keys.

    Returns None on any failure, exactly as the Corti path does when a template
    cannot be provisioned — callers already treat that as "fall back to rules".
    """
    body = {
        "model": _settings.openai_model,
        "messages": [
            {"role": "system", "content": _instructions(spec)},
            {"role": "user", "content": "\n\n".join(block for block in context_blocks if block)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": _schema_name(spec),
                "strict": True,
                "schema": _schema_for(spec),
            },
        },
    }

    try:
        response = await _http().post("/chat/completions", json=body)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise AiError(
            f"OpenAI returned {exc.response.status_code}: {exc.response.text[:300]}"
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise AiError(f"OpenAI request failed: {exc}") from exc

    choice = (payload.get("choices") or [{}])[0]
    # A refusal is a normal, documented outcome of structured output, not an
    # error — treat it as "no answer" so the caller falls back rather than 500s.
    if (choice.get("message") or {}).get("refusal"):
        logger.warning("OpenAI refused to generate %s", spec.get("name"))
        return None

    content = (choice.get("message") or {}).get("content")
    if not content:
        return None

    try:
        fields = json.loads(content)
    except ValueError as exc:
        raise AiError(f"OpenAI returned content that is not JSON: {exc}") from exc
    if not isinstance(fields, dict):
        return None

    # Same contract as the Corti path: only keys we asked for, empties dropped.
    wanted = {section["key"] for section in spec["sections"]}
    return {
        key: value
        for key, value in fields.items()
        if key in wanted and value not in (None, "", [])
    }
