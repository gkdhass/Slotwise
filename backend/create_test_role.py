"""Create slotwise_test role."""
import asyncio
import asyncpg


async def create_role():
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/postgres")
    await conn.execute("CREATE ROLE slotwise_test WITH LOGIN PASSWORD 'slotwise_test'")
    await conn.close()
    print("Created slotwise_test role")


asyncio.run(create_role())
