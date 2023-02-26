from pydantic import BaseModel


class Trace(BaseModel):
    file: str
    duration: float
    name: str
    label: str
    time: str = ''
    id: str = ''
