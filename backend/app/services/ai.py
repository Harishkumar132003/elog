"""Entry analysis: Corti first, rule-based always.

The deterministic parser runs on every request — it costs microseconds and produces
the exact shape the UI consumes. Corti's answer is then merged over the top, field
by field. If Corti is slow, broken, or returns an empty section, that field simply
keeps its rule-based value.

This is §5.1's "scripted fallbacks so a demo never dead-ends": there is no path
where the entry screen fails to return an analysis.
"""

from __future__ import annotations

import hashlib
import logging
import time
from copy import deepcopy
from typing import Any

from app.core.config import get_settings
from app.services import catalogue
from app.services.corti import CortiError
from app.services.corti_templates import parse_template, run_template
from app.services.parser import parse_narrative

logger = logging.getLogger(__name__)
_settings = get_settings()

# Mirrors OMISSION_CHECKS in lexicon.py so both paths label gaps identically.
_OMISSION_LABELS: dict[str, tuple[str, str]] = {
    "laterality": ("Side", "Side not documented"),
    "consent": ("Consent", "Consent not recorded"),
    "anaesthesia": ("Anaesthesia", "Anaesthesia not recorded"),
    "indication": ("Mechanism", "Mechanism or indication not stated"),
    "complication": ("Complications", "Complications not commented on"),
    "followup": ("Plan", "Post-procedure plan not recorded"),
}

def _competency_context(items: list[dict[str, str]]) -> str:
    return "CANDIDATE COMPETENCIES (choose exactly one id):\n" + "\n".join(
        f"- {item['id']} — {item['title']}" for item in items
    )


async def _baseline(narrative: str, subject: str) -> dict[str, Any]:
    """The rule-based answer, before Corti gets a say.

    When a subject has exactly one competency — a fresh catalogue, or a subject the
    professor has not loaded yet — that one is the answer and there is nothing to
    choose. With a real curriculum loaded there are dozens, and no deterministic
    rule picks between them: leave it unset and let Corti propose, or the resident
    choose from the dropdown. An unanswerable question is better left open than
    guessed at.
    """
    items = await catalogue.list_for(subject)
    only = items[0] if len(items) == 1 else None
    return {
        "parsed": parse_narrative(narrative),
        "competency": only,
        "confidence": 1.0 if only else 0.0,
        "source": "rules",
    }


async def _merge(result: dict[str, Any], fields: dict[str, Any], subject: str) -> dict[str, Any]:
    """Overlay Corti's fields onto the rule-based result, field by field."""
    parsed = result["parsed"]

    diagnosis = (fields.get("diagnosis") or "").strip()
    if diagnosis:
        parsed["diagnosis"] = {"core": diagnosis, "qualifiers": [], "display": diagnosis}

    procedure = (fields.get("procedure") or "").strip()
    if procedure:
        existing = parsed.get("procedure") or {}
        parsed["procedure"] = {
            "name": procedure,
            "detail": None,
            "display": procedure,
            "steps": existing.get("steps", []),
        }

    # Age arrives as digits in a string: Corti's outputSchema has no integer type.
    raw_age = str(fields.get("patient_age") or "").strip()
    age = int(raw_age) if raw_age.isdigit() and 0 < int(raw_age) <= 120 else None
    sex = fields.get("patient_sex")
    sex = None if sex in (None, "", "unknown") else sex
    if age or sex:
        display = f"{age} · {sex}" if age and sex else (str(age) if age else str(sex))
        parsed["patient"] = {"age": age, "sex": sex, "display": display}

    omissions = fields.get("omissions")
    if isinstance(omissions, list):
        parsed["omissions"] = [
            {"id": key, "short": _OMISSION_LABELS[key][0], "label": _OMISSION_LABELS[key][1]}
            for key in omissions
            if key in _OMISSION_LABELS
        ]

    # Corti's pick is now the answer, not a cross-check: the enum it chose from is
    # this subject's own catalogue, so it cannot name another subject's competency
    # and cannot invent one. The resident still gets the last word on the review step.
    picked = await catalogue.by_slug(fields.get("competency") or "")
    if picked and picked["subject"] == subject:
        result["competency"] = picked
        result["confidence"] = 0.9

    result["source"] = "corti"
    return result


# The resident presses Analyse, reviews, then saves — and the save re-parses the
# identical text. Memoising the AI answer for a few minutes turns that second
# parse into a cache hit, halving the calls per saved entry.
_PARSE_TTL_SECONDS = 900
_PARSE_CACHE_MAX = 256
_parse_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_key(narrative: str, subject: str, competency_ids: list[str]) -> str:
    """Keyed on the catalogue too, so editing it does not serve a stale pick.

    The cached answer names a competency. If a professor removes or replaces one,
    a key that ignored the catalogue would keep handing out the old choice until
    the TTL ran down.
    """
    catalogue_state = "\x1f".join(competency_ids)
    return hashlib.sha256(
        f"{subject}\x00{catalogue_state}\x00{narrative}".encode()
    ).hexdigest()


def _cache_get(key: str) -> dict[str, Any] | None:
    hit = _parse_cache.get(key)
    if hit is None:
        return None
    stored_at, value = hit
    if time.monotonic() - stored_at > _PARSE_TTL_SECONDS:
        _parse_cache.pop(key, None)
        return None
    # Callers mutate `parsed` (corrections are applied over it), so never hand
    # out the cached object itself.
    return deepcopy(value)


def _cache_put(key: str, value: dict[str, Any]) -> None:
    if len(_parse_cache) >= _PARSE_CACHE_MAX:
        oldest = min(_parse_cache, key=lambda k: _parse_cache[k][0])
        _parse_cache.pop(oldest, None)
    _parse_cache[key] = (time.monotonic(), deepcopy(value))


async def baseline_for(narrative: str, subject: str) -> dict[str, Any]:
    """The deterministic answer alone, without waiting for Corti.

    Costs microseconds, so the streaming endpoint can put diagnosis, procedure
    and patient on screen immediately and let the AI refine them a few seconds
    later. `analyse_entry` still computes its own — the parser is far cheaper
    than the branch that would be needed to share one.
    """
    return await _baseline(narrative, subject)


async def analyse_entry(narrative: str, subject: str) -> dict[str, Any]:
    """Parse an e-log entry and choose the competency it is evidence for."""
    result = await _baseline(narrative, subject)

    if not _settings.corti_enabled or not narrative.strip():
        return result

    items = await catalogue.list_for(subject)
    key = _cache_key(narrative, subject, [item["id"] for item in items])
    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        fields = await run_template(
            parse_template(subject), [narrative, _competency_context(items)]
        )
        if not fields:
            result["source"] = "rules-fallback"
            return result
        merged = await _merge(result, fields, subject)
        # Only a real AI answer is worth caching — caching a fallback would pin a
        # degraded result in place for the whole TTL.
        _cache_put(key, merged)
        return merged
    except CortiError as exc:
        logger.warning("Corti analysis unavailable, using rules: %s", exc)
        result["source"] = "rules-fallback"
        return result
    except Exception:  # never let the entry screen fail on an AI problem
        logger.exception("Unexpected error during Corti analysis")
        result["source"] = "rules-fallback"
        return result
