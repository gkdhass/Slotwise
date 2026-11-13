"""List all routes from the actual FastAPI app."""
from app.main import create_app
from app.api.deps import iter_api_routes

app = create_app()

print("=" * 80)
print("LIVE ROUTE TABLE FROM ACTUAL APP (via iter_api_routes)")
print("=" * 80)

routes = []
for route in iter_api_routes(app.routes):
    methods = sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"})
    path = getattr(route, "path", "N/A")
    
    # Get endpoint name if available
    endpoint_name = ""
    if hasattr(route, "endpoint") and hasattr(route.endpoint, "__name__"):
        endpoint_name = route.endpoint.__name__
    
    for method in methods:
        routes.append((method, path, endpoint_name))

# Sort by path then method  
routes.sort(key=lambda x: (x[1], x[0]))

print(f"\nTotal API routes: {len(routes)}\n")
print(f"{'Method':<8} {'Path':<60} {'Endpoint'}")
print("-" * 100)
for method, path, endpoint in routes:
    print(f"{method:<8} {path:<60} {endpoint}")

print("\n" + "=" * 80)
