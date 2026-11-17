#!/usr/bin/env python
"""Grant application role DML permissions after schema migration.

Runs after alembic upgrade head. Applies least-privilege grants:
- DML on all operational tables (including event_outbox)
- SELECT, INSERT only on audit_logs (append-only, no UPDATE/DELETE/TRUNCATE)
- No ALTER DEFAULT PRIVILEGES

Usage:
    python grant_app_permissions.py
"""

import asyncio
import os
import re

import asyncpg


async def grant_permissions():
    """Grant minimal DML privileges to slotwise_app role."""
    # Read database URL from environment
    db_url = os.environ.get(
        "TEST_MIGRATION_URL",
        "postgresql+asyncpg://slotwise_migrator:slotwise_migrator@127.0.0.1:5432/slotwise_test",
    )
    # Parse connection string
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        conn = await asyncpg.connect(db_url)

        # Validate role name
        app_role = "slotwise_app"
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", app_role):
            raise ValueError(f"Invalid role name: {app_role}")

        # Execute grants
        # Role name validated above via regex, SQL injection risk mitigated
        sql_template = (
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{app_role}') THEN
                    -- REVOKE all first to clear any accumulated privileges
                    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {app_role};
                    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {app_role};

                    -- Schema usage
                    GRANT USAGE ON SCHEMA public TO {app_role};

                    -- DML on operational tables: SELECT, INSERT, UPDATE, DELETE
                    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
                      TO {app_role};

                    -- Sequences for ID generation
                    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {app_role};

                    -- audit_logs: override to INSERT, SELECT ONLY
                    REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM {app_role};

                    -- alembic_version: read-only
                    GRANT SELECT ON alembic_version TO {app_role};

                    -- Revoke TRUNCATE from all tables
                    REVOKE TRUNCATE ON ALL TABLES IN SCHEMA public FROM {app_role};
                END IF;
            END
            $$;
            """
        )
        await conn.execute(sql_template)

        print(f"✓ Privileges granted to {app_role}")

        # Verify audit_logs privileges
        result = await conn.fetch(
            """
            SELECT privilege_type
            FROM information_schema.role_table_grants
            WHERE table_name = 'audit_logs'
            AND grantee = $1
            ORDER BY privilege_type
            """,
            app_role,
        )
        privs = [row[0] for row in result]
        print(f"  audit_logs privileges for {app_role}: {privs}")
        if set(privs) == {"INSERT", "SELECT"}:
            print("  ✓ audit_logs correctly restricted to INSERT, SELECT only")
        else:
            print(f"  ✗ ERROR: Expected only INSERT, SELECT; got {privs}")
            return False

        await conn.close()
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(grant_permissions())
    exit(0 if success else 1)
