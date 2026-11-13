"""Check and create required PostgreSQL roles and databases."""
import asyncio
import asyncpg


async def check_setup():
    # Connect as postgres superuser
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/postgres")

    # Check/create roles
    roles = await conn.fetch(
        "SELECT rolname FROM pg_roles WHERE rolname IN ('slotwise_migrator', 'slotwise_app', 'slotwise_test')"
    )
    existing_roles = {r["rolname"] for r in roles}

    if "slotwise_migrator" not in existing_roles:
        await conn.execute("CREATE ROLE slotwise_migrator WITH LOGIN PASSWORD 'slotwise_migrator'")
        print("Created role: slotwise_migrator")
    else:
        print("Role exists: slotwise_migrator")

    if "slotwise_app" not in existing_roles:
        await conn.execute("CREATE ROLE slotwise_app WITH LOGIN PASSWORD 'slotwise_app'")
        print("Created role: slotwise_app")
    else:
        print("Role exists: slotwise_app")

    if "slotwise_test" not in existing_roles:
        await conn.execute("CREATE ROLE slotwise_test WITH LOGIN PASSWORD 'slotwise_test'")
        print("Created role: slotwise_test")
    else:
        print("Role exists: slotwise_test")

    # Check/create databases
    dbs = await conn.fetch(
        "SELECT datname FROM pg_database WHERE datname IN ('slotwise', 'slotwise_test')"
    )
    existing_dbs = {d["datname"] for d in dbs}

    if "slotwise" not in existing_dbs:
        await conn.execute("CREATE DATABASE slotwise OWNER slotwise_migrator")
        print("Created database: slotwise")
    else:
        print("Database exists: slotwise")

    if "slotwise_test" not in existing_dbs:
        await conn.execute("CREATE DATABASE slotwise_test OWNER slotwise_migrator")
        print("Created database: slotwise_test")
    else:
        print("Database exists: slotwise_test")

    await conn.close()
    
    # Grant permissions on slotwise_test
    test_conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/slotwise_test")
    await test_conn.execute("GRANT ALL PRIVILEGES ON DATABASE slotwise_test TO slotwise_test")
    await test_conn.execute("GRANT ALL PRIVILEGES ON SCHEMA public TO slotwise_test")
    await test_conn.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO slotwise_test")
    await test_conn.execute("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO slotwise_test")
    await test_conn.close()
    
    print("Granted permissions to slotwise_test role")
    print("Setup complete!")


asyncio.run(check_setup())
