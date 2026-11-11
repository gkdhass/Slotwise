"""MLflow/registry client boundary.

Phase 2 will implement artifact and metric access. Keeping the protocol here
prevents the API layer from depending on MLflow types.
"""

from __future__ import annotations

from typing import Any, Protocol


class ModelRegistryClient(Protocol):
    async def list_versions(self, pipeline: str) -> list[dict[str, Any]]: ...

    async def get_metrics(self, model_version_id: str) -> dict[str, Any]: ...
