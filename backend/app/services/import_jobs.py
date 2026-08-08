"""Progress of a running PDF import, held in the process.

A job is transient: one professor uploads one file, watches a progress line for a
few minutes, and takes the result into the editor. Nothing downstream reads it
afterwards, and the extracted competencies are not saved until the professor
presses Save. That makes it working state rather than a record, so it lives in
memory instead of a collection.

The trade-off, stated plainly: restarting the server loses any import in flight,
and this would need to move to the database before running more than one worker.
Both are visible to the professor as "that import is no longer available", which is
recoverable by uploading again.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

# Jobs are small (a few hundred strings at most) and short-lived, but a long
# session should not accumulate them without bound.
_TTL_SECONDS = 3600.0
_MAX_JOBS = 32

_jobs: dict[str, dict[str, Any]] = {}


def _sweep() -> None:
    now = time.monotonic()
    for job_id in [k for k, v in _jobs.items() if now - v["_at"] > _TTL_SECONDS]:
        _jobs.pop(job_id, None)
    while len(_jobs) > _MAX_JOBS:
        _jobs.pop(min(_jobs, key=lambda k: _jobs[k]["_at"]), None)


def create(professor_id: str, subject: str, filename: str | None, total: int,
           pages_read: int, pages_total: int) -> str:
    _sweep()
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {
        "_at": time.monotonic(),
        "_professor_id": professor_id,
        "id": job_id,
        "subject": subject,
        "status": "running",
        "filename": filename,
        "done": 0,
        "total": total,
        "pages_read": pages_read,
        "pages_total": pages_total,
        "truncated": False,
        "found": [],
        "error": None,
    }
    return job_id


def update(job_id: str, **fields: Any) -> None:
    job = _jobs.get(job_id)
    if job is not None:
        job.update(fields)
        job["_at"] = time.monotonic()


def get(job_id: str, professor_id: str) -> dict[str, Any] | None:
    """A job is only visible to the professor who started it."""
    job = _jobs.get(job_id)
    if job is None or job["_professor_id"] != professor_id:
        return None
    return {key: value for key, value in job.items() if not key.startswith("_")}
