"""Check if policy immutability trigger exists."""
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect(
        host='localhost', port=5432,
        user='postgres', password='postgres',
        database='slotwise_test'
    )
    
    # Check for function
    func_result = await conn.fetch("""
        SELECT proname, prosrc
        FROM pg_proc
        WHERE proname = 'response_policies_immutable'
    """)
    
    print("=== Function in pg_proc ===")
    if func_result:
        print(f"Function exists: {func_result[0]['proname']}")
        print(f"Source (first 200 chars): {func_result[0]['prosrc'][:200]}...")
    else:
        print("Function NOT FOUND")
    
    # Check for trigger
    trigger_result = await conn.fetch("""
        SELECT tgname, tgenabled, 
               pg_get_triggerdef(oid) as definition
        FROM pg_trigger
        WHERE tgname LIKE '%immutable%' OR tgrelid = 'response_policies'::regclass
    """)
    
    print("\n=== Triggers on response_policies ===")
    if trigger_result:
        for row in trigger_result:
            print(f"Trigger: {row['tgname']}, Enabled: {row['tgenabled']}")
            print(f"Definition: {row['definition'][:150]}...")
    else:
        print("No triggers found")
    
    await conn.close()

asyncio.run(main())
