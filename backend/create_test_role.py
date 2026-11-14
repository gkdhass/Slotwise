"""Create slotwise_test role."""

import asyncio
import logging

import asyncpg

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


async def create_role():
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/postgres")
    await conn.execute("CREATE ROLE slotwise_test WITH LOGIN PASSWORD 'slotwise_test'")
    await conn.close()
    logger.info("Created slotwise_test role")


asyncio.run(create_role())
