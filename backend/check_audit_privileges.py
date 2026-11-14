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
    result = await conn.fetchrow("""
        SELECT
            has_table_privilege('slotwise_app', 'audit_logs', 'INSERT') as can_insert,
            has_table_privilege('slotwise_app', 'audit_logs', 'UPDATE') as can_update,
            has_table_privilege('slotwise_app', 'audit_logs', 'DELETE') as can_delete,
            has_table_privilege('slotwise_app', 'audit_logs', 'TRUNCATE') as can_truncate
    """)
    logger.info("Privileges for slotwise_app on audit_logs:")
    logger.info(f"  INSERT:   {result['can_insert']}")
    logger.info(f"  UPDATE:   {result['can_update']}")
    logger.info(f"  DELETE:   {result['can_delete']}")
    logger.info(f"  TRUNCATE: {result['can_truncate']}")
    await conn.close()


asyncio.run(main())
