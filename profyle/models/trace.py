from typing import Dict, Any
from pydantic import BaseModel


class Trace(BaseModel):
    data: Dict[str, Any]
    duration: float
    name: str
    timestamp: str = ''
    id: str = ''
