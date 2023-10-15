from typing import Any
from pydantic import BaseModel, Json, computed_field


class Trace(BaseModel):
    data: Json[Any] = {}
    name: str
    duration: float = 0
    timestamp: str = ''
    id: int


class TraceCreate(BaseModel):
    data: Json[Any] = {}
    name: str

    @computed_field
    @property
    def duration(self) -> float:
        start = min(
            trace.get('ts')
            for trace in self.data.get('traceEvents', [])
            if trace.get('ts')
        )
        end = max(
            trace.get('ts', 0)
            for trace in self.data.get('traceEvents', [])
        )
        return end-start
