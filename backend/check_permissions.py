"""Check current permissions for slotwise_app role."""

import asyncio
import asyncpg


async def main():
    # Connect as slotwise_app
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="slotwise_app",
            password="slotwise_app",
            database="slotwise_test",
        )

        # Try to select from roles
        try:
            roles = await conn.fetch("SELECT * FROM roles")
            print(f"✓ Can SELECT from roles: {len(roles)} rows")
        except Exception as e:
            print(f"✗ Cannot SELECT from roles: {e}")

        # Try to insert into roles
        try:
            await conn.execute(
                "INSERT INTO roles (name, description, id) VALUES ($1, $2, gen_random_uuid())",
                "TEST", "Test role"
            )
            print("✓ Can INSERT into roles")
            await conn.execute("DELETE FROM roles WHERE name = 'TEST'")
        except Exception as e:
            print(f"✗ Cannot INSERT into roles: {e}")

        await conn.close()

    except Exception as e:
        print(f"✗ Cannot connect as slotwise_app: {e}")

    # Now check with postgres
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="postgres",
        database="slotwise_test",
    )

    result = await conn.fetch("""
        SELECT grantee, privilege_type
        FROM information_schema.role_table_grants
        WHERE table_name='roles' AND grantee='slotwise_app'
    """)
    print(f"\nGrants on roles table for slotwise_app:")
    for row in result:
        print(f"  {row['privilege_type']}")

    # Check table owner
    owner = await conn.fetchval("""
        SELECT tableowner FROM pg_tables
        WHERE tablename='roles' AND schemaname='public'
    """)
    print(f"\nTable owner: {owner}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
