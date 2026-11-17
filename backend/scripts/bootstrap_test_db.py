#!/usr/bin/env python
"""Bootstrap test database and roles."""

import asyncio

import asyncpg


async def bootstrap():
    """Create roles and database for testing."""
    conn = await asyncpg.connect('postgresql://postgres:postgres@127.0.0.1:5432/postgres')

    # Roles (ignore "already exists")
    try:
        await conn.execute("CREATE ROLE slotwise_migrator LOGIN PASSWORD 'slotwise_migrator';")
        print("✓ Created role slotwise_migrator")
    except asyncpg.DuplicateObjectError:
        print("✓ Role slotwise_migrator already exists")

    try:
        await conn.execute("CREATE ROLE slotwise_app LOGIN PASSWORD 'slotwise_app';")
        print("✓ Created role slotwise_app")
    except asyncpg.DuplicateObjectError:
        print("✓ Role slotwise_app already exists")

    # Database
    try:
        await conn.execute("DROP DATABASE IF EXISTS slotwise_test WITH (FORCE);")
        print("✓ Dropped existing slotwise_test database")
    except Exception as e:
        print(f"! Drop database warning: {e}")

    await conn.execute("CREATE DATABASE slotwise_test OWNER slotwise_migrator;")
    print("✓ Created database slotwise_test")

    # Connect to new DB and grant
    await conn.close()
    conn = await asyncpg.connect('postgresql://postgres:postgres@127.0.0.1:5432/slotwise_test')
    await conn.execute("GRANT USAGE ON SCHEMA public TO slotwise_app;")
    print("✓ Granted USAGE on schema public to slotwise_app")
    await conn.execute("GRANT CREATE ON SCHEMA public TO slotwise_migrator;")
    print("✓ Granted CREATE on schema public to slotwise_migrator")
    await conn.close()

    print("\n✓ Bootstrap complete")


if __name__ == "__main__":
    asyncio.run(bootstrap())
