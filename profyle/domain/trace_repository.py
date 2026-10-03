from abc import ABC, abstractmethod
from typing import Any

from profyle.domain.trace import NewTrace, RecordedRequest, Trace


class TraceRepository(ABC):
    """Where traces are kept, together with what is derived from them."""

    # --- Traces ---------------------------------------------------------------------

    @abstractmethod
    def add_trace(self, trace: NewTrace) -> int | None:
        """Store a trace and return its id (None if it could not be stored)."""

    @abstractmethod
    def get_trace(self, trace_id: int, include_data: bool = True) -> Trace | None: ...

    @abstractmethod
    def list_traces(
        self,
        limit: int | None = None,
        name_contains: str | None = None,
        min_duration_ms: float = 0,
    ) -> list[Trace]:
        """Newest first, without their data. `name_contains` ignores case."""

    @abstractmethod
    def latest_trace_id(self) -> int:
        """0 when there are no traces."""

    @abstractmethod
    def update_request(self, trace_id: int, request: RecordedRequest) -> None: ...

    @abstractmethod
    def delete_trace(self, trace_id: int) -> None: ...

    @abstractmethod
    def delete_all_traces(self) -> int:
        """Delete every trace and free the space; returns how many were deleted."""

    # --- Digests: the analysis of a trace, computed once on the reading side --------

    @abstractmethod
    def get_digest(self, trace_id: int) -> dict[str, Any] | None: ...

    @abstractmethod
    def store_digest(self, trace_id: int, digest: dict[str, Any], headline: str) -> None: ...

    @abstractmethod
    def trace_ids_without_digest(self, limit: int) -> list[int]: ...

    # --- Runtime: the app currently writing traces (shown by `profyle doctor`) ------

    @abstractmethod
    def store_runtime(self, info: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_runtime(self) -> dict[str, Any] | None: ...
