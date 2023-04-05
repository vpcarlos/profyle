import tempfile
from types import TracebackType
from typing import Optional, Type


from viztracer import VizTracer


class Profyle:

    def __init__(self) -> None:
        self.tracer = VizTracer()
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.json')

    def __enter__(self):
        self.tracer.start()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ):
        self.tracer.stop()
        self.tracer.save(self.temp_file.name)
        self.temp_file.close()
        self.data = self.tracer.data
