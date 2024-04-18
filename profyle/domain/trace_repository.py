from abc import ABC, abstractmethod
from typing import Optional

from profyle.domain.trace import Trace, TraceCreate


class TraceRepository(ABC):
    @abstractmethod
    def create_trace_selected_table(self) -> None:
        ...

    @abstractmethod
    def create_trace_table(self) -> None:
        ...

    @abstractmethod
    def delete_all_traces(self) -> int:
        ...

    @abstractmethod
    def deleted_all_selected_traces(self) -> int:
        ...

    @abstractmethod
    def vacuum(self) -> None:
        ...

    @abstractmethod
    def store_trace_selected(self, trace_id: int) -> None:
        ...

    @abstractmethod
    def store_trace(self, new_trace: TraceCreate) -> None:
        ...

    @abstractmethod
    def get_all_traces(self) -> list[Trace]:
        ...

    @abstractmethod
    def get_trace_by_id(self, id: int) -> Optional[Trace]:
        ...

    @abstractmethod
    def get_trace_selected(self) -> Optional[int]:
        ...

    @abstractmethod
    def delete_trace_by_id(self, trace_id: int):
        ...
