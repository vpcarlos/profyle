from pydantic import BaseModel


class Trace(BaseModel):
    file: str
    duration: float
    url: str
    method: str
    label: str
    time: str = ''
    id: str = ''
