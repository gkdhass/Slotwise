"""Check if policy immutability trigger exists."""

import asyncio
import logging
import os

import asyncpg

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


async def main():
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password=os.environ.get("PGPASSWORD", "postgres"),
        database="slotwise_test",
    )

    # Check for function
    func_result = await conn.fetch("""
        SELECT proname, prosrc
        FROM pg_proc
        WHERE proname = 'response_policies_immutable'
    """)

    logger.info("=== Function in pg_proc ===")
    if func_result:
        logger.info(f"Function exists: {func_result[0]['proname']}")
        logger.info(f"Source (first 200 chars): {func_result[0]['prosrc'][:200]}...")
    else:
        logger.info("Function NOT FOUND")

    # Check for trigger
    trigger_result = await conn.fetch("""
        SELECT tgname, tgenabled,
               pg_get_triggerdef(oid) as definition
        FROM pg_trigger
        WHERE tgname LIKE '%immutable%' OR tgrelid = 'response_policies'::regclass
    """)

    logger.info("\n=== Triggers on response_policies ===")
    if trigger_result:
        for row in trigger_result:
            logger.info(f"Trigger: {row['tgname']}, Enabled: {row['tgenabled']}")
            logger.info(f"Definition: {row['definition'][:150]}...")
    else:
        logger.info("No triggers found")

    await conn.close()


asyncio.run(main())
