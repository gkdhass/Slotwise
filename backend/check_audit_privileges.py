import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect(
        host='localhost', port=5432, 
        user='postgres', password='postgres', 
        database='slotwise_test'
    )
    result = await conn.fetchrow("""
        SELECT 
            has_table_privilege('slotwise_app', 'audit_logs', 'INSERT') as can_insert,
            has_table_privilege('slotwise_app', 'audit_logs', 'UPDATE') as can_update,
            has_table_privilege('slotwise_app', 'audit_logs', 'DELETE') as can_delete,
            has_table_privilege('slotwise_app', 'audit_logs', 'TRUNCATE') as can_truncate
    """)
    print(f"Privileges for slotwise_app on audit_logs:")
    print(f"  INSERT:   {result['can_insert']}")
    print(f"  UPDATE:   {result['can_update']}")
    print(f"  DELETE:   {result['can_delete']}")
    print(f"  TRUNCATE: {result['can_truncate']}")
    await conn.close()

asyncio.run(main())
