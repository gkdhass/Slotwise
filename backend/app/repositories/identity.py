"""Role, user and refresh-token repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.models.identity import RefreshToken, Role, User
from app.repositories.base import BaseRepository
from app.repositories.keyset import keyset_page
from app.repositories.pagination import Page


class RoleRepository(BaseRepository[Role]):
    model = Role

    async def get_by_name(self, name: str) -> Role | None:
        result = await self.session.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Role]:
        result = await self.session.execute(select(Role).order_by(Role.name))
        return list(result.scalars().all())


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        result = await self.session.execute(
            select(User).options(selectinload(User.role)).where(User.email == normalized)
        )
        return result.scalar_one_or_none()

    async def get_with_role(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User).options(selectinload(User.role)).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> Page[User]:
        statement = select(User).options(selectinload(User.role))
        if role is not None:
            statement = statement.join(Role, User.role_id == Role.id).where(Role.name == role)
        if is_active is not None:
            statement = statement.where(User.is_active.is_(is_active))
        return await keyset_page(
            self.session,
            statement,
            scope="users",
            sort_column=User.created_at,
            id_column=User.id,
            limit=limit,
            cursor=cursor,
        )


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke_family(self, family_id: uuid.UUID, *, now: datetime | None = None) -> int:
        moment = now or datetime.now(UTC)
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=moment)
        )
        return int(result.rowcount or 0)

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, now: datetime | None = None) -> int:
        moment = now or datetime.now(UTC)
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=moment)
        )
        return int(result.rowcount or 0)

    async def family_is_active(self, family_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(func.count())
            .select_from(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.used_at.is_(None),
            )
        )
        return int(result.scalar_one()) > 0
