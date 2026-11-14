"""Grant DML-only permissions to slotwise_app role for test database.

For tests to pass, slotwise_app needs:
- DML (SELECT/INSERT/UPDATE/DELETE) on operational tables
- INSERT-only on audit_logs (enforced by DB triggers for UPDATE/DELETE/TRUNCATE)
- NO DDL privileges
- NO ownership
"""

import asyncio
import logging
import os

import asyncpg

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


async def main():
    # Connect as postgres superuser
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password=os.environ.get("PGPASSWORD", "postgres"),
        database="slotwise_test",
    )

    try:
        # Grant USAGE on schema
        await conn.execute("GRANT USAGE ON SCHEMA public TO slotwise_app")

        # Grant DML on all tables (SELECT, INSERT, UPDATE, DELETE)
        await conn.execute("""
            GRANT SELECT, INSERT, UPDATE, DELETE
            ON ALL TABLES IN SCHEMA public
            TO slotwise_app
        """)

        # REVOKE UPDATE, DELETE, TRUNCATE on audit_logs specifically
        # (INSERT is allowed for audit writing, but mutations are blocked)
        await conn.execute("""
            REVOKE UPDATE, DELETE, TRUNCATE
            ON audit_logs
            FROM slotwise_app
        """)

        # Grant USAGE and SELECT on all sequences (needed for SERIAL/BIGSERIAL columns)
        await conn.execute("""
            GRANT USAGE, SELECT
            ON ALL SEQUENCES IN SCHEMA public
            TO slotwise_app
        """)

        # Set default privileges for future tables created by slotwise_migrator
        await conn.execute("""
            ALTER DEFAULT PRIVILEGES FOR ROLE slotwise_migrator IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO slotwise_app
        """)

        await conn.execute("""
            ALTER DEFAULT PRIVILEGES FOR ROLE slotwise_migrator IN SCHEMA public
            GRANT USAGE, SELECT ON SEQUENCES TO slotwise_app
        """)

        # Verify permissions on operational table
        result = await conn.fetch("""
            SELECT has_table_privilege('slotwise_app', 'roles', 'SELECT') as can_select,
                   has_table_privilege('slotwise_app', 'roles', 'INSERT') as can_insert,
                   has_table_privilege('slotwise_app', 'roles', 'UPDATE') as can_update,
                   has_table_privilege('slotwise_app', 'roles', 'DELETE') as can_delete,
                   has_table_privilege('slotwise_app', 'roles', 'TRUNCATE') as can_truncate,
                   has_table_privilege('slotwise_app', 'roles', 'REFERENCES') as can_references,
                   has_table_privilege('slotwise_app', 'roles', 'TRIGGER') as can_trigger
        """)
        perms = dict(result[0])
        logger.info("slotwise_app permissions on roles table:")
        logger.info(
            f"  DML: SELECT={perms['can_select']}, INSERT={perms['can_insert']}, "
            f"UPDATE={perms['can_update']}, DELETE={perms['can_delete']}"
        )
        logger.info(
            f"  DDL-like: TRUNCATE={perms['can_truncate']}, "
            f"REFERENCES={perms['can_references']}, TRIGGER={perms['can_trigger']}"
        )

        # Verify permissions on audit_logs
        audit_result = await conn.fetch("""
            SELECT has_table_privilege('slotwise_app', 'audit_logs', 'INSERT') as can_insert,
                   has_table_privilege('slotwise_app', 'audit_logs', 'UPDATE') as can_update,
                   has_table_privilege('slotwise_app', 'audit_logs', 'DELETE') as can_delete,
                   has_table_privilege('slotwise_app', 'audit_logs', 'TRUNCATE') as can_truncate
        """)
        audit_perms = dict(audit_result[0])
        logger.info("\nslotwise_app permissions on audit_logs table:")
        logger.info(
            f"  INSERT={audit_perms['can_insert']}, UPDATE={audit_perms['can_update']}, "
            f"DELETE={audit_perms['can_delete']}, TRUNCATE={audit_perms['can_truncate']}"
        )
        logger.info("  (DB triggers will block UPDATE/DELETE/TRUNCATE even if granted)")

        logger.info("\n✓ Successfully granted DML-only permissions to slotwise_app")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
