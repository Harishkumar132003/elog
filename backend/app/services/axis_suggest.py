"""Screen 3 · which axes to put in front of the professor first.

The specification's rule is that a professor *prunes* the closed set (§2A), so
this proposes a shortlist and a candidate fatal error — it never decides, and it
never reaches outside the axes already offered for this entry.

Two guards, because a suggestion that names an unoffered axis would quietly break
the closure rule:

1. Corti's `outputSchema` enum is the axis catalogue, so it cannot invent an id.
2. Anything not in *this entry's* role-filtered candidate set is dropped here.
"""

from __future__ import annotations

import logging
from typing import Any

from app.data.axes import BY_ID as AXIS_BY_ID
from app.data.axes import candidate_axes
from app.services.corti import CortiError
from app.services.corti_templates import AXIS_TEMPLATE, MAX_SUGGESTIONS, run_template
from app.services.exercise import case_context

logger = logging.getLogger(__name__)


def _allowed_context(entry: dict[str, Any]) -> tuple[str, set[str]]:
    axes = candidate_axes(entry["subject"], entry["role"])
    allowed = {axis["id"] for axis in axes}
    lines = [
        "ALLOWED AXES — choose only from these ids:",
        *(f"- {axis['id']} · {axis['label']} — {axis['varies']}" for axis in axes),
    ]
    return "\n".join(lines), allowed


async def suggest_axes(entry: dict[str, Any]) -> dict[str, Any]:
    """Return `{suggestions: [...], critical_axis, critical_why}`.

    Empty suggestions are a normal outcome: the professor then works from the
    full offered list, exactly as before.
    """
    context, allowed = _allowed_context(entry)

    try:
        fields = await run_template(AXIS_TEMPLATE, [case_context(entry), context])
    except CortiError as exc:
        logger.warning("Corti axis suggestion unavailable: %s", exc)
        fields = None
    except Exception:
        logger.exception("Unexpected error suggesting axes")
        fields = None

    if not fields:
        return {"suggestions": [], "critical_axis": None, "critical_why": "", "source": "none"}

    shortlist = fields.get("shortlist")
    if not isinstance(shortlist, list):
        shortlist = []

    suggestions: list[dict[str, str]] = []
    seen: set[str] = set()
    for axis_id in shortlist[: MAX_SUGGESTIONS * 2]:
        axis_id = str(axis_id).strip()
        if axis_id not in allowed or axis_id in seen:
            continue
        seen.add(axis_id)
        axis = AXIS_BY_ID[axis_id]
        suggestions.append(
            {
                "axis_id": axis_id,
                "label": axis["label"],
                # Wording comes from the closed catalogue, not the model: it is
                # accurate by construction and cannot drift from the axis it labels.
                "reason": axis["varies"],
                "example": axis["example"],
            }
        )
        if len(suggestions) == MAX_SUGGESTIONS:
            break

    critical = (fields.get("critical_axis") or "").strip()
    if critical not in seen:
        # The fatal error has to be one of the axes actually being proposed.
        critical = suggestions[0]["axis_id"] if suggestions else None

    return {
        "suggestions": suggestions,
        "critical_axis": critical,
        "critical_why": (fields.get("critical_why") or "").strip(),
        "source": "corti",
    }
