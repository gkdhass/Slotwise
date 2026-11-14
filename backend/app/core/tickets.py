"""Single-use WebSocket authentication tickets.

Browsers cannot set an ``Authorization`` header on a WebSocket handshake, so a
REST call issues a random ticket that is stored hashed in Redis for 30 seconds.
Consumption uses ``GETDEL`` so exactly one handshake can win even under a race.
The ticket is bound to the user and the client IP that requested it.
"""

from __future__ import annotations

import json
import uuid

from app.core.redis import RedisClient
from app.core.security import hash_token, new_ws_ticket

_TICKET_PREFIX = "ws:ticket:"


def _key(raw: str, ip_address: str) -> str:
    # The issuing IP is part of the key, so a ticket presented from a different
    # address simply finds nothing. Using the raw ticket hash alone would mean a
    # GETDEL from the wrong IP burns the ticket and denies the legitimate client.
    return f"{_TICKET_PREFIX}{hash_token(f'{raw}|{ip_address}')}"


async def issue_ws_ticket(
    redis: RedisClient, *, user_id: uuid.UUID, ip_address: str, ttl_seconds: int
) -> str:
    raw, _digest = new_ws_ticket()
    payload = json.dumps({"sub": str(user_id), "ip": ip_address})
    await redis.set(_key(raw, ip_address), payload, ex=ttl_seconds)
    return raw


async def consume_ws_ticket(redis: RedisClient, raw: str, *, ip_address: str) -> uuid.UUID | None:
    stored = await redis.getdel(_key(raw, ip_address))
    if not stored:
        return None
    try:
        payload = json.loads(stored)
        subject = uuid.UUID(str(payload.get("sub")))
        bound_ip = str(payload.get("ip", ""))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if bound_ip != ip_address:
        return None
    return subject
