from abc import ABC, abstractmethod
from typing import Any

from profyle.domain.trace import RecordedRequest, Trace, TraceCreate


class TraceRepository(ABC):
    @abstractmethod
    def create_trace_selected_table(self) -> None: ...

    @abstractmethod
    def create_trace_table(self) -> None: ...

    @abstractmethod
    def delete_all_traces(self) -> int: ...

    @abstractmethod
    def deleted_all_selected_traces(self) -> int: ...

    @abstractmethod
    def vacuum(self) -> None: ...

    @abstractmethod
    def store_trace_selected(self, trace_id: int) -> None: ...

    @abstractmethod
    def store_trace(self, new_trace: TraceCreate) -> int | None:
        """Store a trace and return its id (None if it could not be stored)."""

    @abstractmethod
    def update_trace_request(self, trace_id: int, request: RecordedRequest) -> None: ...

    @abstractmethod
    def get_all_traces(self) -> list[Trace]: ...

    @abstractmethod
    def get_trace_by_id(self, id: int, include_data: bool = True) -> Trace | None: ...

    @abstractmethod
    def store_runtime(self, info: dict[str, Any]) -> None:
        """Record the app process currently writing traces (shown by `profyle doctor`)."""

    @abstractmethod
    def get_runtime(self) -> dict[str, Any] | None: ...

    @abstractmethod
    def get_digest(self, trace_id: int) -> dict[str, Any] | None: ...

    @abstractmethod
    def store_digest(self, trace_id: int, digest: dict[str, Any], headline: str) -> None: ...

    @abstractmethod
    def trace_ids_without_digest(self, limit: int) -> list[int]: ...

    @abstractmethod
    def get_trace_selected(self) -> int | None: ...

    @abstractmethod
    def delete_trace_by_id(self, trace_id: int): ...
