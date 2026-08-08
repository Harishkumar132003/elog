"""The professor's view of a resident's evidence.

Everything here is already recorded elsewhere in the loop; none of it was ever
aggregated. The four signals worth a professor's attention:

  coverage       — which competencies have no evidence at all (§4A)
  critical       — how often the fatal-error item was failed (§3.4)
  axes           — which *kind* of variation the resident loses marks on
  documentation  — what they habitually leave out of their entries (§4A.1)

The last one is the omission signal: it has been captured on every entry since the
first screen was built and, until now, only ever shown as chips on a single case.
Across ten entries it says something a single case cannot.
"""

from typing import Annotated, Any

from bson import ObjectId
from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentProfessor, entry_filter_for, to_object_id
from app.core.constants import EntryStatus, Role, Subject
from app.data.axes import BY_ID as AXIS_BY_ID
from app.data.axes import FAMILY_LABELS, Family
from app.data.bloom import COGNITIVE_LEVELS, COGNITIVE_TARGET
from app.db import mongo
from app.schemas.dashboard import Dashboard
from app.services import catalogue

router = APIRouter(prefix="/professor", tags=["dashboard"])

RECENT_CASES = 5


def _entry_facets() -> dict[str, Any]:
    return {
        "by_status": [{"$group": {"_id": "$status", "n": {"$sum": 1}}}],
        "by_competency": [{"$group": {"_id": "$competency_id", "n": {"$sum": 1}}}],
        "by_resident": [{"$group": {"_id": "$resident_id", "n": {"$sum": 1}}}],
        # The omission signal, finally counted.
        "documentation": [
            {"$unwind": "$parsed.omissions"},
            {
                "$group": {
                    "_id": "$parsed.omissions.id",
                    "label": {"$first": "$parsed.omissions.short"},
                    "n": {"$sum": 1},
                }
            },
        ],
    }


def _attempt_facets() -> dict[str, Any]:
    return {
        "totals": [
            {
                "$group": {
                    "_id": None,
                    "n": {"$sum": 1},
                    "critical": {"$sum": {"$cond": ["$summary.critical_failed", 1, 0]}},
                }
            }
        ],
        "outcomes": [{"$group": {"_id": "$summary.outcome", "n": {"$sum": 1}}}],
        "by_resident": [
            {
                "$group": {
                    "_id": "$resident_id",
                    "n": {"$sum": 1},
                    "critical": {"$sum": {"$cond": ["$summary.critical_failed", 1, 0]}},
                }
            }
        ],
        "by_axis": [
            {"$unwind": "$results"},
            {
                "$group": {
                    "_id": "$results.axis_id",
                    "label": {"$first": "$results.axis_label"},
                    "questions": {"$sum": 1},
                    "awarded": {"$sum": "$results.marks_awarded"},
                    "available": {"$sum": "$results.marks"},
                }
            },
        ],
        "cognitive": [
            {"$unwind": "$results"},
            {
                "$group": {
                    "_id": "$results.cognitive",
                    "asked": {"$sum": 1},
                    "correct": {
                        "$sum": {"$cond": [{"$eq": ["$results.verdict", "correct"]}, 1, 0]}
                    },
                }
            },
        ],
    }


async def _facet(collection: str, match: dict[str, Any], facets: dict[str, Any]) -> dict[str, Any]:
    rows = await mongo.get_db()[collection].aggregate(
        [{"$match": match}, {"$facet": facets}]
    ).to_list(length=1)
    return rows[0] if rows else {}


@router.get("/dashboard", response_model=Dashboard)
async def get_dashboard(
    professor: CurrentProfessor,
    resident_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Aggregated evidence for the professor's residents, or for one of them."""
    # Same query filter as everywhere else, so a professor can only ever reach
    # their own residents even if they pass someone else's id.
    scope = entry_filter_for(professor)
    if resident_id:
        scope = scope | {"resident_id": to_object_id(resident_id)}

    entries = await _facet("entries", scope, _entry_facets())
    attempts = await _facet("attempts", scope | {"marking": {"$ne": True}}, _attempt_facets())

    def rows(facet: dict[str, Any], key: str) -> list[dict[str, Any]]:
        return facet.get(key, []) or []

    # --- who ------------------------------------------------------------
    roster = mongo.users().find(
        {"professor_id": ObjectId(professor["id"]), "role": Role.RESIDENT.value}
    ).sort("name", 1)
    cases_by_resident = {r["_id"]: r["n"] for r in rows(entries, "by_resident")}
    attempts_by_resident = {r["_id"]: r for r in rows(attempts, "by_resident")}

    residents = []
    async for person in roster:
        stat = attempts_by_resident.get(person["_id"], {})
        residents.append(
            {
                "id": str(person["_id"]),
                "name": person["name"],
                "year": person.get("year"),
                "department": person.get("department"),
                "cases": cases_by_resident.get(person["_id"], 0),
                "answered": stat.get("n", 0),
                "critical_failures": stat.get("critical", 0),
            }
        )

    # --- pipeline --------------------------------------------------------
    by_status = {r["_id"]: r["n"] for r in rows(entries, "by_status")}
    totals = {
        "cases": sum(by_status.values()),
        "awaiting_certification": by_status.get(EntryStatus.LOGGED.value, 0),
        "in_review": by_status.get(EntryStatus.CERTIFIED.value, 0),
        "ready_to_answer": by_status.get(EntryStatus.RELEASED.value, 0),
        "reasoned": by_status.get(EntryStatus.ANSWERED.value, 0),
    }

    # --- coverage, grouped by subject ------------------------------------
    # A loaded curriculum runs to dozens of competencies per subject, so listing
    # every one would bury the handful with evidence under two hundred blanks. The
    # subject carries the ratio; underneath it, only what has actually been logged.
    logged = {r["_id"]: r["n"] for r in rows(entries, "by_competency")}
    coverage: list[dict[str, Any]] = []
    for value in Subject:
        items = await catalogue.list_for(value.value)
        live = {item["id"] for item in items}
        evidenced = [
            {"id": item["id"], "title": item["title"], "logged": logged[item["id"]], "retired": False}
            for item in items
            if logged.get(item["id"])
        ]

        # Cases logged against a competency the professor has since removed still
        # happened. They are shown as retired rather than quietly dropped, but they
        # do not count towards the ratio — that measures the current curriculum.
        retired = await catalogue.retired_with_slugs(
            value.value, [slug for slug in logged if slug not in live]
        )
        evidenced += [
            {"id": item["id"], "title": item["title"], "logged": logged[item["id"]], "retired": True}
            for item in retired
        ]
        evidenced.sort(key=lambda c: (c["retired"], -c["logged"]))

        covered = sum(1 for c in evidenced if not c["retired"])
        coverage.append(
            {
                "subject": value.value,
                "total": len(items),
                "covered": covered,
                "percentage": round(100 * covered / len(items)) if items else 0,
                "competencies": evidenced,
            }
        )

    # --- marking ---------------------------------------------------------
    attempt_totals = (rows(attempts, "totals") or [{}])[0]
    outcomes = sorted(
        (
            {"key": r["_id"] or "Not scored", "label": r["_id"] or "Not scored", "count": r["n"]}
            for r in rows(attempts, "outcomes")
        ),
        key=lambda b: -b["count"],
    )

    axes = []
    for row in rows(attempts, "by_axis"):
        axis = AXIS_BY_ID.get(row["_id"])
        available = row["available"] or 0
        axes.append(
            {
                "axis_id": row["_id"],
                "label": row.get("label") or (axis["label"] if axis else row["_id"]),
                "family": FAMILY_LABELS[Family(axis["family"])][0] if axis else "—",
                "questions": row["questions"],
                "awarded": row["awarded"],
                "available": available,
                "percentage": round(100 * row["awarded"] / available) if available else 0,
            }
        )
    axes.sort(key=lambda a: (a["percentage"], -a["questions"]))  # weakest first

    seen = {r["_id"]: r for r in rows(attempts, "cognitive")}
    cognitive = [
        {
            "level": level,
            "asked": seen.get(level, {}).get("asked", 0),
            "correct": seen.get(level, {}).get("correct", 0),
            # §3.1 — the levels reasoning questions should be landing on.
            "target": level in COGNITIVE_TARGET,
        }
        for level in COGNITIVE_LEVELS
    ]

    # --- documentation habits -------------------------------------------
    total_entries = totals["cases"]
    documentation = sorted(
        (
            {
                "id": r["_id"],
                "label": r.get("label") or r["_id"],
                "missing": r["n"],
                "of": total_entries,
                "percentage": round(100 * r["n"] / total_entries) if total_entries else 0,
            }
            for r in rows(entries, "documentation")
        ),
        key=lambda d: -d["missing"],
    )

    # --- the log ---------------------------------------------------------
    names = {r["id"]: r["name"] for r in residents}
    summaries = {
        a["entry_id"]: a.get("summary", {})
        async for a in mongo.attempts().find(
            scope | {"marking": {"$ne": True}}, {"entry_id": 1, "summary": 1}
        )
    }
    recent = []
    # Just the latest few — the dashboard is a summary; "All cases" is the log.
    async for entry in mongo.entries().find(scope).sort("created_at", -1).limit(RECENT_CASES):
        summary = summaries.get(entry["_id"], {})
        recent.append(
            {
                "id": str(entry["_id"]),
                "resident_id": str(entry["resident_id"]),
                "resident_name": names.get(str(entry["resident_id"])),
                "diagnosis": entry.get("diagnosis"),
                "competency_title": entry.get("competency_title"),
                "subject": entry["subject"],
                "status": entry.get("status", EntryStatus.LOGGED.value),
                "outcome": summary.get("outcome"),
                "percentage": summary.get("percentage"),
                "critical_failed": bool(summary.get("critical_failed")),
                "created_at": entry["created_at"],
            }
        )

    return {
        "resident_id": resident_id,
        "residents": residents,
        "totals": totals,
        "coverage": coverage,
        "outcomes": outcomes,
        "critical_failed": attempt_totals.get("critical", 0),
        "attempts": attempt_totals.get("n", 0),
        "axes": axes,
        "cognitive": cognitive,
        "documentation": documentation,
        "recent": recent,
    }
