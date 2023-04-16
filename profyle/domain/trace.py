from typing import Any
from pydantic import BaseModel, Json


class Trace(BaseModel):
    data: Json[Any] = {}
    name: str
    duration: float = 0
    timestamp: str = ''
    id: str = ''

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if self.data and not self.duration:
            start = min(
                trace.get('ts')
                for trace in self.data.get('traceEvents', [])
                if trace.get('ts')
            )
            end = max(
                trace.get('ts', 0)
                for trace in self.data.get('traceEvents', [])
            )
            self.duration = end-start
