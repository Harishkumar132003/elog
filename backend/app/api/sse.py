"""Server-sent events.

Two endpoints stream now — entry parsing and dictation — and both rely on the
same property: an intermediary cannot time out a connection that never falls
silent. Cloudflare's 100s limit and nginx's `proxy_read_timeout` both measure the
gap between bytes, not the total duration, so a heartbeat is what makes a
two-minute response safe.
"""

import json
from typing import Any

# Short enough that no proxy sees an idle connection, long enough not to chatter.
HEARTBEAT_SECONDS = 5.0

# nginx buffers proxied responses by default, which would hold every event until
# the stream closed — defeating the point and putting the silence back. This
# disables it per response, so no nginx config change is needed.
STREAM_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def sse(event: str, data: dict[str, Any]) -> bytes:
    """One server-sent event. The blank line terminates the frame."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()
