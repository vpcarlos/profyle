from abc import ABC, abstractmethod
from typing import List, Optional

from profyle.domain.trace import Trace


class TraceRepository(ABC):

    @abstractmethod
    def create_trace_selected_table(self) -> None:
        ...

    @abstractmethod
    def create_trace_table(self) -> None:
        ...

    @abstractmethod
    def remove_all_traces(self) -> int:
        ...

    @abstractmethod
    def vacuum(self) -> None:
        ...

    @abstractmethod
    def store_trace_selected(self, trace_id: int) -> None:
        ...

    @abstractmethod
    def store_trace(self, trace: Trace) -> None:
        ...

    @abstractmethod
    def get_all_traces(self) -> List[Trace]:
        ...

    @abstractmethod
    def get_trace_by_id(self, id: int) -> Optional[Trace]:
        ...

    def get_trace_selected(self) -> Optional[int]:
        ...
