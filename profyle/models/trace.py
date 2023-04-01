from typing import Any
from pydantic import BaseModel, Json


class Trace(BaseModel):
    data: Json[Any] = {}
    duration: float
    name: str
    timestamp: str = ''
    id: str = ''
