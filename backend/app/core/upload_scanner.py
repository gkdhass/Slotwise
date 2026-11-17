"""Upload scanning for event import files.

The :class:`UploadScanner` interface validates an uploaded file before it is
parsed. The default implementation checks:

* content type (from the ``Content-Type`` header)
* file extension (from the filename)
* magic bytes (the content signature must match the declared format)
* size (``import_max_file_bytes``)
* null bytes
* decompression-bomb heuristics (gzip/zlib content must not decompress beyond
  the size cap)
"""

from __future__ import annotations

import gzip
from typing import ClassVar

from app.core.config import Settings


class UploadRejectedError(Exception):
    """Raised by a scanner when an upload must be rejected.

    ``code`` is a stable machine-readable rejection reason surfaced in the
    import summary.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class UploadScanner:
    """Interface: validate an uploaded import file before parsing."""

    async def scan(
        self,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> None:
        """Raise :class:`UploadRejectedError` if the upload is unacceptable."""
        raise NotImplementedError


class DefaultUploadScanner(UploadScanner):
    """Default scanner: type, size, null-byte and decompression-bomb checks."""

    EXTENSION_CONTENT_TYPES: ClassVar[dict[str, frozenset[str]]] = {
        ".csv": frozenset({"text/csv", "application/csv"}),
        ".json": frozenset({"application/json"}),
        ".ndjson": frozenset({"application/x-ndjson", "application/ndjson", "application/json"}),
    }

    #: Decompressed content must not exceed the same cap as the upload itself.
    DECOMPRESSION_LIMIT_RATIO = 4

    _EXT_TO_FMT: ClassVar[dict[str, str]] = {".csv": "csv", ".json": "json", ".ndjson": "ndjson"}
    _FMT_TO_EXT: ClassVar[dict[str, str]] = {"csv": ".csv", "json": ".json", "ndjson": ".ndjson"}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.max_bytes = settings.security.import_max_file_bytes

    # ------------------------------------------------------------------ format

    def _format_from_extension(self, filename: str) -> str | None:
        name = filename.lower()
        for ext in (".ndjson", ".json", ".csv"):
            if name.endswith(ext):
                return self._EXT_TO_FMT[ext]
        return None

    def _content_type_allowed(self, fmt: str, content_type: str | None) -> bool:
        if not content_type:
            return False
        ct = content_type.split(";", 1)[0].strip().lower()
        return ct in self.EXTENSION_CONTENT_TYPES.get(self._FMT_TO_EXT[fmt], frozenset())

    # ------------------------------------------------------------------ magic bytes

    @staticmethod
    def _leading(data: bytes) -> bytes:
        return data.lstrip(b" \t\r\n")

    def _magic_matches(self, fmt: str, data: bytes) -> bool:
        stripped = self._leading(data)
        if not stripped:
            return False
        first = stripped[:1]
        if fmt in ("json", "ndjson"):
            return first in (b"{", b"[")
        if fmt == "csv":
            # CSV must not look like a JSON document.
            return first not in (b"{", b"[")
        return True

    # ------------------------------------------------------------------ entry point

    async def scan(
        self,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> None:
        if not filename:
            raise UploadRejectedError("NO_FILENAME", "A file is required.")

        # 1. Extension check.
        fmt = self._format_from_extension(filename)
        if fmt is None:
            raise UploadRejectedError(
                "UNSUPPORTED_EXTENSION",
                f"Unsupported file extension for {filename!r}.",
            )

        # 2. Content-type check.
        if not self._content_type_allowed(fmt, content_type):
            raise UploadRejectedError(
                "WRONG_CONTENT_TYPE",
                f"Content type {content_type!r} does not match extension {filename!r}.",
            )

        # 3. Raw size check.
        if len(data) > self.max_bytes:
            raise UploadRejectedError(
                "FILE_TOO_LARGE",
                f"Upload exceeds {self.max_bytes} bytes.",
            )

        # 4. Decompression-bomb heuristic: detect gzip, decompress, and reject
        #    content that inflates beyond the cap. Decompressed content replaces
        #    the raw bytes for the remaining checks so a gzip bomb cannot hide
        #    null bytes or a mismatched magic signature behind compression.
        data = self._maybe_decompress(data)

        # 5. Null-byte check on the (possibly decompressed) content.
        if b"\x00" in data:
            raise UploadRejectedError("NULL_BYTES_DETECTED", "Upload contains null bytes.")

        # 6. Magic-byte check on the (possibly decompressed) content.
        if not self._magic_matches(fmt, data):
            raise UploadRejectedError(
                "MAGIC_BYTE_MISMATCH",
                f"Content does not match the {fmt} format.",
            )

    def _maybe_decompress(self, data: bytes) -> bytes:
        """Decompress gzip uploads, enforcing the decompression-bomb cap.

        Returns the decompressed bytes for gzip input, otherwise the input
        unchanged.
        """
        stripped = self._leading(data)
        if stripped[:2] != b"\x1f\x8b":  # gzip magic
            return data
        try:
            decompressed = gzip.decompress(data)
        except (OSError, EOFError) as exc:
            raise UploadRejectedError("DECOMPRESSION_BOMB", "Gzip upload is corrupt.") from exc
        if len(decompressed) > self.max_bytes * self.DECOMPRESSION_LIMIT_RATIO:
            raise UploadRejectedError(
                "DECOMPRESSION_BOMB",
                "Decompressed content exceeds the size limit.",
            )
        return decompressed
