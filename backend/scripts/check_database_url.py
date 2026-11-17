#!/usr/bin/env python
"""Check which database URL is being used."""

import os
import sys

sys.path.insert(0, '.')

from app.core.config import get_settings

s = get_settings()

# Mask passwords for display
def mask_url(url):
    parts = url.split("@")
    return f"{parts[0].rsplit(':', 1)[0]}:***@{parts[1] if len(parts) > 1 else 'UNKNOWN'}"

print("Environment Variables:")
print(f"  DATABASE_URL={os.environ.get('DATABASE_URL', '(not set)')}")
print(f"  DATABASE_MIGRATION_URL={os.environ.get('DATABASE_MIGRATION_URL', '(not set)')}")
print(f"  TEST_DATABASE_URL={os.environ.get('TEST_DATABASE_URL', '(not set)')}")
print(f"  TEST_MIGRATION_URL={os.environ.get('TEST_MIGRATION_URL', '(not set)')}")

print("\nSettings resolved:")
print(f"  database.url: {mask_url(s.database.url)}")
print(f"  database.migration_url: {s.database.migration_url}")
print(f"  database.effective_migration_url: {mask_url(s.database.effective_migration_url)}")
print(f"  database.app_role: {s.database.app_role}")
print(f"  database.migration_role: {s.database.migration_role}")
