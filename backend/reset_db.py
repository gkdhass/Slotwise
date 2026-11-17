#!/usr/bin/env python
"""Reset test DB and migrate fresh."""
import asyncio
import asyncpg
from app.core.config import settings

async def main():
    conn = await asyncpg.connect(str(settings.database.migration_url))
    try:
        # Drop and recreate
        await conn.execute("DROP DATABASE IF EXISTS slotwise_test WITH (FORCE);")
        print("✓ Dropped existing database")
        
        await conn.execute("CREATE DATABASE slotwise_test;")
        print("✓ Created database slotwise_test")
        
        # Grant usage/create  
        await conn.execute("GRANT USAGE ON SCHEMA public TO slotwise_app;")
        await conn.execute("GRANT CREATE ON SCHEMA public TO slotwise_migrator;")
        print("✓ Granted schema privileges")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
