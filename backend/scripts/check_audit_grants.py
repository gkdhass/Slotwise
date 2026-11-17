#!/usr/bin/env python
"""Check audit_logs grants and triggers."""

import asyncio

import asyncpg


async def check():
    """Check audit_logs grants and triggers."""
    conn = await asyncpg.connect('postgresql://slotwise_app:slotwise_app@127.0.0.1:5432/slotwise_test')

    # Show privileges
    print("Audit privileges for slotwise_app:")
    result = await conn.fetch("""
        SELECT privilege_type 
        FROM information_schema.role_table_grants 
        WHERE table_name = 'audit_logs' AND grantee = 'slotwise_app'
        ORDER BY privilege_type
    """)
    for row in result:
        print(f"  - {row[0]}")

    # Show triggers on audit_logs
    print("\nAudit triggers from pg_trigger:")
    result = await conn.fetch("""
        SELECT tgname, tgtype, tgenabled 
        FROM pg_trigger 
        WHERE tgrelid = 'audit_logs'::regclass
    """)
    if result:
        for row in result:
            print(f"  - {row[0]}: type={row[1]}, enabled={row[2]}")
    else:
        print("  (no triggers)")

    await conn.close()

asyncio.run(check())
