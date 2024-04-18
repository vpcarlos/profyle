from typing import Any

from pydantic import BaseModel, Json, computed_field


class Trace(BaseModel):
    data: Json[Any] = {}
    name: str
    duration: float = 0
    timestamp: str = ""
    id: int


class TraceCreate(BaseModel):
    data: Json[Any] = {}
    name: str

    @computed_field
    @property
    def duration(self) -> float:
        any_trace_to_analize = any(
            True for trace in self.data.get("traceEvents", []) if trace.get("ts")
        )
        if not any_trace_to_analize:
            return 0

        start = min(
            trace.get("ts", 0) for trace in self.data.get("traceEvents", []) if trace.get("ts")
        )
        end = max(trace.get("ts", 0) for trace in self.data.get("traceEvents", []))
        return end - start
