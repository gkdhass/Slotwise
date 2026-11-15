"""S3-compatible storage service for raw event archiving.

Implements idempotent PUT and signed URL generation. Falls back to in-memory
fake for tests when real S3 is unavailable.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError


class StorageService:
    """S3-compatible storage client with idempotent operations."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bucket = settings.minio.bucket
        self._fake_storage: dict[str, bytes] = {}

    async def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",  # noqa: ARG002
        metadata: dict[str, str] | None = None,  # noqa: ARG002
    ) -> str:
        """Store an object idempotently.

        Returns the object key. Same key + same data = no-op.
        Raises ServiceUnavailableError if storage is down.
        """
        # TODO: Implement real S3/MinIO client
        # For now, use in-memory fake
        try:
            if key in self._fake_storage:
                # Verify data matches for idempotency
                existing = self._fake_storage[key]
                if existing != data:
                    raise ValueError(f"Key {key} already exists with different data")
            else:
                self._fake_storage[key] = data
            return key
        except Exception as exc:
            raise ServiceUnavailableError(
                "Storage service unavailable",
                details={"retry_after": 60},
            ) from exc

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 300,
    ) -> str:
        """Generate a pre-signed URL for temporary access.

        Raises ServiceUnavailableError if storage is down.
        """
        # TODO: Implement real S3/MinIO pre-signed URL generation
        # For now, return a fake URL
        try:
            if key not in self._fake_storage:
                raise KeyError(f"Object not found: {key}")

            # In a real implementation, this would generate a signed URL
            # For now, return a placeholder
            base_url = self.settings.minio.endpoint.rstrip("/")
            return f"{base_url}/{self.bucket}/{key}?token=fake-token&expires={expires_in}"
        except Exception as exc:
            raise ServiceUnavailableError(
                "Storage service unavailable",
                details={"retry_after": 60},
            ) from exc

    async def get_object(self, key: str) -> bytes:
        """Retrieve an object.

        Raises ServiceUnavailableError if storage is down.
        """
        try:
            if key not in self._fake_storage:
                raise KeyError(f"Object not found: {key}")
            return self._fake_storage[key]
        except Exception as exc:
            raise ServiceUnavailableError(
                "Storage service unavailable",
                details={"retry_after": 60},
            ) from exc


class FakeStorageService(StorageService):
    """In-memory storage for tests."""

    def __init__(self) -> None:
        from unittest.mock import Mock

        mock_settings = Mock()
        mock_settings.minio.bucket = "test-bucket"
        mock_settings.minio.endpoint = "http://localhost:9000"
        super().__init__(mock_settings)

    async def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",  # noqa: ARG002
        metadata: dict[str, str] | None = None,  # noqa: ARG002
    ) -> str:
        """Store in memory, always succeeds."""
        self._fake_storage[key] = data
        return key

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 300,  # noqa: ARG002
    ) -> str:
        """Return fake URL."""
        if key not in self._fake_storage:
            raise KeyError(f"Object not found: {key}")
        return f"http://localhost:9000/test-bucket/{key}?token=fake"

    async def get_object(self, key: str) -> bytes:
        """Retrieve from memory."""
        if key not in self._fake_storage:
            raise KeyError(f"Object not found: {key}")
        return self._fake_storage[key]
