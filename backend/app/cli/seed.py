"""``python -m app.cli.seed`` entry point.

Examples:
    python -m app.cli.seed
    python -m app.cli.seed --demo

The command is safe to run repeatedly. It never prints secrets, and a weak or
placeholder admin password is refused outside dev/test.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.core.config import get_settings, reset_settings_cache
from app.core.database import dispose_engine, init_engine
from app.services.seed import SeedError, SeedService


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Slotwise bootstrap data.")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Also create clearly labelled synthetic demo alerts/incidents (dev/test only).",
    )
    return parser.parse_args(argv)


async def _run(demo: bool) -> int:
    settings = get_settings()
    init_engine(settings)
    try:
        service = SeedService(settings)
        result = await service.run(demo=demo)
    finally:
        await dispose_engine()
    print(json.dumps(result.as_dict(), sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    reset_settings_cache()
    try:
        return asyncio.run(_run(bool(args.demo)))
    except SeedError as exc:
        print(f"seed refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
