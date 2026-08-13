"""Screen 3 · concrete ways to vary this case along one chosen axis.

The axis says what *kind* of variation to test; the parameter says what the
variation actually is for this patient. Writing one is the slowest part of
certifying, and the AI has already read the case to shortlist the axes — so it
can propose here too.

It proposes; the professor decides. Every parameter arrives editable and
removable, and the professor can ignore all of them and type their own. That is
the same relationship as the axis shortlist (§2A) — the earlier note in
`axis_suggest.py` that the parameter is deliberately never model-generated
described the old one-parameter screen and no longer holds.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.data.axes import BY_ID as AXIS_BY_ID
from app.core.config import get_settings
from app.data.axes import candidate_axes
from app.services.corti import CortiError
from app.services.corti_templates import MAX_PARAMETERS, PARAMETER_TEMPLATE, run_template
from app.services.exercise import case_context

logger = logging.getLogger(__name__)
_settings = get_settings()

# Long enough for a real clinical variation, short enough to stay a parameter
# rather than becoming the question itself.
_MAX_CHARS = 160
_MIN_CHARS = 8


def _axis_brief(axis: dict[str, str], existing: list[str]) -> str:
    lines = [
        "THE AXIS TO VARY ALONG",
        f"{axis['label']} — {axis['varies']}",
        f"For example: {axis['example']}",
        "",
        "Every parameter must be a variation of THIS axis. Do not drift to a "
        "different kind of variation, however interesting.",
    ]
    if existing:
        # Without this the model proposes the same obvious variation every time,
        # and a professor filling a third row gets three repeats to discard.
        lines += [
            "",
            "ALREADY CHOSEN for this axis — propose something genuinely different, "
            "not these reworded:",
            *(f"- {text}" for text in existing),
        ]
    return "\n".join(lines)


def _clean(value: Any) -> str:
    """Trim a proposal down to a parameter, or nothing."""
    text = " ".join(str(value).split())
    # The model occasionally answers with the question rather than the variation.
    text = text.lstrip("-•*0123456789.() ").strip()
    if text.endswith("?"):
        return ""
    return text if _MIN_CHARS <= len(text) <= _MAX_CHARS else ""


async def suggest_parameters(
    entry: dict[str, Any], axis_id: str, existing: list[str] | None = None
) -> dict[str, Any]:
    """Return `{parameters: [...], source}` for one axis of one case.

    `existing` is whatever the professor already has on that axis. It is sent to
    the model so it proposes something new, and filtered again on the way back —
    the instruction is a request, not a guarantee.

    An empty list is a normal outcome, not an error: the professor then writes
    their own, exactly as before this existed.
    """
    already = [text.strip() for text in (existing or []) if text and text.strip()][:20]
    seen: set[str] = {text.lower() for text in already}
    # The axis must be one actually offered for this entry — the same closure
    # rule the shortlist and the certify endpoint enforce.
    allowed = {axis["id"] for axis in candidate_axes(entry["subject"], entry["role"])}
    axis = AXIS_BY_ID.get(axis_id)
    if axis is None or axis_id not in allowed:
        return {"parameters": [], "source": "none"}

    try:
        async with asyncio.timeout(_settings.suggest_timeout_seconds):
            fields = await run_template(
            PARAMETER_TEMPLATE, [case_context(entry), _axis_brief(axis, already)]
            )
    except TimeoutError:
        logger.warning("Corti took longer than %ss; falling back", _settings.suggest_timeout_seconds)
        fields = None
    except CortiError as exc:
        logger.warning("Corti parameter suggestion unavailable: %s", exc)
        fields = None
    except Exception:
        logger.exception("Unexpected error suggesting parameters")
        fields = None

    if not fields:
        return {"parameters": [], "source": "none"}

    proposed = fields.get("parameters")
    if not isinstance(proposed, list):
        proposed = []

    parameters: list[str] = []
    for item in proposed:
        text = _clean(item)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        parameters.append(text)
        if len(parameters) == MAX_PARAMETERS:
            break

    return {"parameters": parameters, "source": _settings.ai_provider if parameters else "none"}
