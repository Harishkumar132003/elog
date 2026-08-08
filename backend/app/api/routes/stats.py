from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUser, entry_filter_for
from app.core.constants import DopsRole, EntryStatus, role_labels
from app.db import mongo
from app.schemas.entry import Stats

router = APIRouter(tags=["stats"])

# Role ids are shared across subject classes; label them with the clinical wording.
_ROLE_LABEL = {role.value: label for role, (label, _) in role_labels("clinical").items()}
_ROLE_LABEL[DopsRole.TOPIC.value] = "Topic-based"


@router.get("/stats", response_model=Stats)
async def get_stats(user: CurrentUser) -> dict[str, Any]:
    """Aggregated in MongoDB — documents are never pulled into Python to count."""
    scope = entry_filter_for(user)

    pipeline = [
        {"$match": scope},
        {
            "$facet": {
                "totals": [
                    {
                        "$group": {
                            "_id": None,
                            "total": {"$sum": 1},
                            "certified": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$in": [
                                                "$status",
                                                [
                                                    EntryStatus.CERTIFIED.value,
                                                    EntryStatus.RELEASED.value,
                                                    EntryStatus.ANSWERED.value,
                                                ],
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "answered": {
                                "$sum": {
                                    "$cond": [
                                        {"$eq": ["$status", EntryStatus.ANSWERED.value]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    }
                ],
                "by_subject": [
                    {"$group": {"_id": "$subject", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "by_role": [{"$group": {"_id": "$role", "count": {"$sum": 1}}}],
                "by_competency": [
                    {"$match": {"competency_id": {"$ne": None}}},
                    {
                        "$group": {
                            "_id": "$competency_id",
                            "title": {"$first": "$competency_title"},
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"count": -1}},
                ],
            }
        },
    ]

    result = await mongo.entries().aggregate(pipeline).to_list(length=1)
    facets = result[0] if result else {}
    totals = (facets.get("totals") or [{}])[0]

    return {
        "total": totals.get("total", 0),
        "certified": totals.get("certified", 0),
        "answered": totals.get("answered", 0),
        "by_subject": [
            {"key": row["_id"], "label": row["_id"], "count": row["count"]}
            for row in facets.get("by_subject", [])
        ],
        "by_role": [
            {"key": row["_id"], "label": _ROLE_LABEL.get(row["_id"], row["_id"]), "count": row["count"]}
            for row in facets.get("by_role", [])
        ],
        "by_competency": [
            {"key": row["_id"], "label": row.get("title") or row["_id"], "count": row["count"]}
            for row in facets.get("by_competency", [])
        ],
    }
