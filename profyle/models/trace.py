from typing import Dict, Any
from pydantic import BaseModel, Json


class Trace(BaseModel):
    data: Json[Dict[str, Any]]
    duration: float
    name: str
    timestamp: str = ''
    id: str = ''
