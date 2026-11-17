#!/usr/bin/env python
"""Verify TEST_* vars are ignored in production."""

import os
import sys

os.environ['APP_ENV'] = 'prod'
os.environ['SECURITY_SECRET_KEY'] = 'a' * 64
os.environ['MINIO_SECRET_KEY'] = 'b' * 40
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://user:pass@prod.example.com:5432/slotwise'
os.environ['SEED_ADMIN_PASSWORD'] = 'Strong-Prod-Password-2026!'
os.environ['APP_CORS_ORIGINS'] = 'https://prod.example.com'
os.environ['TEST_DATABASE_URL'] = 'postgresql+asyncpg://slotwise_app:slotwise_app@127.0.0.1:5432/slotwise_test'

sys.path.insert(0, '.')
from app.core.config import Settings, reset_settings_cache

reset_settings_cache()
s = Settings()
print(f"Env: {s.app.env}")
print(f"DB URL (masked): postgresql+asyncpg://***@{s.database.url.split('@')[1]}")
print("✓ TEST_DATABASE_URL was ignored in production" if "prod.example.com" in s.database.url else "✗ TEST_DATABASE_URL was used (WRONG)")
