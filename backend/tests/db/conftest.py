"""Database test harness: real PostgreSQL only, never SQLite."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# The database CI job exports TEST_DATABASE_URL/TEST_MIGRATION_URL. Locally the
# caller can point these at any disposable PostgreSQL database.
APP_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://slotwise_app:slotwise_app@127.0.0.1:5432/slotwise_test",
)
MIGRATION_URL = (
    os.environ.get("TEST_MIGRATION_URL")
    or os.environ.get("DATABASE_MIGRATION_URL")
    or "postgresql+asyncpg://slotwise_migrator:slotwise_migrator@127.0.0.1:5432/slotwise_test"
)
os.environ["DATABASE_URL"] = APP_URL
os.environ["DATABASE_MIGRATION_URL"] = MIGRATION_URL
os.environ.setdefault("DATABASE_APP_ROLE", "slotwise_app")
os.environ.setdefault("APP_ENV", "test")


def alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[None]:
    from app.core.config import reset_settings_cache

    reset_settings_cache()
    command.upgrade(alembic_config(), "head")
    return


@pytest.fixture(scope="session")
def app_engine(migrated_database: None) -> Iterator[AsyncEngine]:
    engine = create_async_engine(
        APP_URL,
        poolclass=NullPool,
        connect_args={"server_settings": {"timezone": "UTC"}},
    )
    return engine


@pytest.fixture(scope="session")
def migration_engine(migrated_database: None) -> Iterator[AsyncEngine]:
    engine = create_async_engine(MIGRATION_URL, poolclass=NullPool)
    return engine


@pytest.fixture
async def db_connection(app_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Outer transaction rolled back after each test.

    Tests may commit freely; SQLAlchemy's ``create_savepoint`` join mode turns
    those commits into savepoint releases inside this outer transaction.
    """
    async with app_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = factory()
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture
def session_factory(db_connection: AsyncConnection) -> Any:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


# --------------------------------------------------------------------- API tests
#
# The API suites run the real FastAPI application against the same PostgreSQL
# transaction as the test body, with two substitutions:
#
# * ``get_db_session`` yields a session bound to that transaction, so a request
#   sees rows the test created and everything is rolled back afterwards.
# * ``get_redis_client`` returns the in-memory double, because no Redis server is
#   available on the developer workstation. The real-Redis contract (TTL, GETDEL
#   atomicity) is covered by ``tests/integration/test_redis_auth.py`` in CI.


@pytest.fixture
def fake_redis() -> Any:
    from tests.fake_redis import FakeRedis

    return FakeRedis()


@pytest.fixture
def api_session_factory(db_connection: AsyncConnection) -> Any:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
async def api_client(app: Any, settings: Any, api_session_factory: Any, fake_redis: Any) -> Any:
    import httpx
    from httpx import ASGITransport

    from app.core.config import get_settings
    from app.core.database import get_db_session
    from app.core.redis import get_redis_client

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with api_session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    app.dependency_overrides[get_settings] = lambda: settings

    # https so the Secure refresh cookie is stored and replayed by the client,
    # exactly as a browser would over TLS.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def make_user(api_session_factory: Any, settings: Any) -> Any:
    """Create a user with a real Argon2 hash inside the test transaction."""
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models.identity import Role, User

    async def _make(
        *,
        email: str,
        password: str,
        role: str = "ANALYST",
        is_active: bool = True,
        must_change_password: bool = False,
    ) -> Any:
        async with api_session_factory() as session:
            role_row = await session.scalar(select(Role).where(Role.name == role))
            if role_row is None:
                role_row = Role(name=role, description=f"{role} (test fixture)")
                session.add(role_row)
                await session.flush()
            user = User(
                email=email.strip().lower(),
                password_hash=hash_password(password, settings=settings),
                role_id=role_row.id,
                is_active=is_active,
                must_change_password=must_change_password,
            )
            session.add(user)
            await session.commit()
            return user.id

    return _make


CSRF_HEADERS = {"X-Requested-With": "slotwise-dashboard"}


@pytest.fixture
def login_headers() -> Any:
    async def _login(client: Any, email: str, password: str) -> dict[str, str]:
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


# ------------------------------------------------------------------ race tests
#
# The transactional harness above hands every request the *same* connection, so
# two requests can never run concurrently (asyncpg rejects overlapping work on
# one connection). The last-admin race tests need real concurrency, which means
# their rows must be committed and every request must check out its own
# connection. ``race_api_client`` uses the pool-backed engine directly;
# ``race_admins`` commits two administrators and removes every row it created.


class RaceAdmin:
    def __init__(self, user_id: Any, email: str, token: str) -> None:
        self.id = user_id
        self.email = email
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


class RaceAdmins:
    def __init__(self, factory: Any, role_ids: dict[str, Any], members: list[RaceAdmin]) -> None:
        self._factory = factory
        self._role_ids = role_ids
        self.members = members

    @property
    def first(self) -> RaceAdmin:
        return self.members[0]

    @property
    def second(self) -> RaceAdmin:
        return self.members[1]

    async def reset(self) -> None:
        """Restore both administrators to active ADMIN without going through auth."""
        from sqlalchemy import update

        from app.models.identity import User

        async with self._factory() as session:
            await session.execute(
                update(User)
                .where(User.id.in_([member.id for member in self.members]))
                .values(is_active=True, role_id=self._role_ids["ADMIN"])
            )
            await session.commit()

    async def set_active(self, member: RaceAdmin, active: bool) -> None:
        from sqlalchemy import update

        from app.models.identity import User

        async with self._factory() as session:
            await session.execute(update(User).where(User.id == member.id).values(is_active=active))
            await session.commit()

    async def active_admin_ids(self) -> list[Any]:
        from sqlalchemy import select

        from app.models.identity import Role, User

        async with self._factory() as session:
            result = await session.execute(
                select(User.id)
                .join(Role, User.role_id == Role.id)
                .where(Role.name == "ADMIN", User.is_active.is_(True))
            )
            return list(result.scalars().all())

    async def roles(self) -> dict[Any, str]:
        from sqlalchemy import select

        from app.models.identity import Role, User

        async with self._factory() as session:
            result = await session.execute(
                select(User.id, Role.name)
                .join(Role, User.role_id == Role.id)
                .where(User.id.in_([member.id for member in self.members]))
            )
            return {row[0]: row[1] for row in result.all()}

    async def active_states(self) -> dict[Any, bool]:
        from sqlalchemy import select

        from app.models.identity import User

        async with self._factory() as session:
            result = await session.execute(
                select(User.id, User.is_active).where(
                    User.id.in_([member.id for member in self.members])
                )
            )
            return {row[0]: row[1] for row in result.all()}


@pytest.fixture
def race_session_factory(app_engine: AsyncEngine) -> Any:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    # NullPool on the engine: every session checks out a distinct connection.
    return async_sessionmaker(bind=app_engine, expire_on_commit=False)


@pytest.fixture
async def race_api_client(
    app: Any, settings: Any, race_session_factory: Any, fake_redis: Any
) -> Any:
    import httpx
    from httpx import ASGITransport

    from app.core.config import get_settings
    from app.core.database import get_db_session
    from app.core.redis import get_redis_client

    async def _session_override() -> AsyncIterator[AsyncSession]:
        # A new session bound to the pool per request -> one connection each.
        async with race_session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    app.dependency_overrides[get_settings] = lambda: settings

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def race_admins(
    race_session_factory: Any, migration_engine: AsyncEngine, settings: Any
) -> AsyncIterator[RaceAdmins]:
    import uuid as uuid_module

    from sqlalchemy import bindparam, select, text

    from app.core.security import create_access_token, hash_password
    from app.models.identity import Role, User

    created_ids: list[Any] = []
    created_role_ids: list[Any] = []
    async with race_session_factory() as session:
        role_ids: dict[str, Any] = {}
        for name in ("ADMIN", "ANALYST", "VIEWER"):
            role = await session.scalar(select(Role).where(Role.name == name))
            if role is None:
                role = Role(name=name, description=f"{name} (race fixture)")
                session.add(role)
                await session.flush()
                created_role_ids.append(role.id)
            role_ids[name] = role.id

        members: list[RaceAdmin] = []
        for _ in range(2):
            email = f"race-admin-{uuid_module.uuid4().hex}@example.com"
            user = User(
                email=email,
                password_hash=hash_password("Race-Password-2026!", settings=settings),
                role_id=role_ids["ADMIN"],
                is_active=True,
                must_change_password=False,
            )
            session.add(user)
            await session.flush()
            created_ids.append(user.id)
            members.append(
                RaceAdmin(
                    user_id=user.id,
                    email=email,
                    token=create_access_token(user.id, "ADMIN", settings=settings),
                )
            )
        await session.commit()
        leftover = (
            (
                await session.execute(
                    select(User.id)
                    .join(Role, User.role_id == Role.id)
                    .where(
                        Role.name == "ADMIN",
                        User.is_active.is_(True),
                        User.id.notin_(created_ids),
                    )
                )
            )
            .scalars()
            .all()
        )

    # The invariant is global, so another committed active admin would silently
    # neuter the race: refuse to produce a false pass.
    assert not leftover, f"committed active admins from another test/run: {list(leftover)}"

    try:
        yield RaceAdmins(race_session_factory, role_ids, members)
    finally:
        if created_ids or created_role_ids:
            async with migration_engine.begin() as connection:
                await connection.execute(
                    text("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_no_delete")
                )
                try:
                    for statement in (
                        "DELETE FROM audit_logs WHERE actor_id IN :ids",
                        "DELETE FROM refresh_tokens WHERE user_id IN :ids",
                        "DELETE FROM users WHERE id IN :ids",
                    ):
                        await connection.execute(
                            text(statement).bindparams(bindparam("ids", expanding=True)),
                            {"ids": created_ids},
                        )
                    if created_role_ids:
                        await connection.execute(
                            text(
                                "DELETE FROM roles WHERE id IN :ids AND NOT EXISTS ("
                                "SELECT 1 FROM users WHERE users.role_id = roles.id)"
                            ).bindparams(bindparam("ids", expanding=True)),
                            {"ids": created_role_ids},
                        )
                finally:
                    await connection.execute(
                        text("ALTER TABLE audit_logs ENABLE TRIGGER audit_logs_no_delete")
                    )
