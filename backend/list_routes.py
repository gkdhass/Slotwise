"""List all routes from the actual FastAPI app."""

import logging

from app.api.deps import iter_api_routes
from app.main import create_app

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

app = create_app()

logger.info("=" * 80)
logger.info("LIVE ROUTE TABLE FROM ACTUAL APP (via iter_api_routes)")
logger.info("=" * 80)

routes = []
for route in iter_api_routes(app.routes):
    methods = sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"})
    path = getattr(route, "path", "N/A")

    # Get endpoint name if available
    endpoint_name = ""
    if hasattr(route, "endpoint") and hasattr(route.endpoint, "__name__"):
        endpoint_name = route.endpoint.__name__

    routes.extend((method, path, endpoint_name) for method in methods)

# Sort by path then method
routes.sort(key=lambda x: (x[1], x[0]))

logger.info(f"\nTotal API routes: {len(routes)}\n")
logger.info(f"{'Method':<8} {'Path':<60} {'Endpoint'}")
logger.info("-" * 100)
for method, path, endpoint in routes:
    logger.info(f"{method:<8} {path:<60} {endpoint}")

logger.info("\n" + "=" * 80)
