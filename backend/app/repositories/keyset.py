"""Reusable keyset pagination for admin collections.

Every admin list endpoint orders by ``(created_at DESC, id DESC)`` and returns an
opaque cursor bound to the collection it was issued for. The cursor is not
signed because it carries no authority: values are bound parameters and the
scope marker prevents replaying a cursor against a different collection.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import Select, and_, literal, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError
from app.repositories.pagination import Page, decode_cursor, encode_cursor, validate_limit

T = TypeVar("T")


async def keyset_page(
    session: AsyncSession,
    statement: Select[Any],
    *,
    scope: str,
    sort_column: Any,
    id_column: Any,
    limit: int,
    cursor: str | None,
) -> Page[Any]:
    size = validate_limit(limit)
    decoded = decode_cursor(cursor)
    if decoded is not None:
        if decoded.get("scope") != scope:
            raise BadRequestError("The pagination cursor does not belong to this collection.")
        try:
            moment = datetime.fromisoformat(str(decoded["created_at"]))
            last_id = uuid.UUID(str(decoded["id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise BadRequestError("The pagination cursor is invalid.") from exc
        # (created_at, id) < (moment, last_id), written explicitly so the bound
        # datetime/UUID types are unambiguous to the driver and the type checker.
        statement = statement.where(
            or_(
                sort_column < literal(moment),
                and_(sort_column == literal(moment), id_column < literal(last_id)),
            )
        )

    page_statement = statement.order_by(sort_column.desc(), id_column.desc()).limit(size + 1)
    result = await session.execute(page_statement)
    items = list(result.scalars().all())
    has_more = len(items) > size
    visible = items[:size]
    next_cursor = None
    if has_more and visible:
        last = visible[-1]
        next_cursor = encode_cursor(
            {
                "scope": scope,
                "created_at": last.created_at.isoformat(),
                "id": str(last.id),
            }
        )
    return Page(items=visible, next_cursor=next_cursor)
