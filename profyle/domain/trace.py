import time
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field, model_serializer


class TraceFile(BaseModel):
    path: str
    source_code: str
    line_count: int

    @model_serializer
    def serialize(self) -> dict[str, Any]:
        return {self.path: [self.source_code, self.line_count]}


class TraceFunction(BaseModel):
    name: str
    file_path: str
    line_number: int

    @model_serializer
    def serialize(self) -> dict[str, Any]:
        return {self.name: [self.file_path, self.line_number]}


class TraceFileInfo(BaseModel):
    trace_id: str = Field(..., description="The trace id of the file info", exclude=True)
    files: dict[str, TraceFile]
    functions: dict[str, TraceFunction]


class TraceEvent(BaseModel):
    trace_id: str = Field(..., description="The trace id of the event", exclude=True)
    phase_type: str = Field(
        ..., description="The phase type of the event", serialization_alias="ph"
    )
    process_id: int = Field(
        ..., description="The process id of the event", serialization_alias="pid"
    )
    thread_id: int = Field(..., description="The thread id of the event", serialization_alias="tid")
    timestamp: float | None = Field(
        ..., description="The timestamp of the event", serialization_alias="ts"
    )
    duration: float | None = Field(
        ..., description="The duration of the event", serialization_alias="dur"
    )
    name: str | None = Field(..., description="The name of the event", serialization_alias="name")
    args: dict[str, Any] | None = Field(
        ..., description="The args of the event", serialization_alias="args"
    )
    category: str | None = Field(
        ..., description="The category of the event", serialization_alias="cat"
    )


class TraceData(BaseModel):
    trace_id: str = Field(
        ...,
        description="The trace id of the data",
        exclude=True,
    )
    events: list[TraceEvent] = Field(
        ...,
        description="The events of the trace",
        serialization_alias="traceEvents",
    )
    file_info: TraceFileInfo
    metadata: dict[Any, Any] = Field(
        ...,
        description="The metadata of the trace",
        serialization_alias="viztracer_metadata",
    )


class ResponseFingerprint(BaseModel):
    """Enough about a response body to tell whether a change altered what it returns,
    without storing the body itself."""

    size: int
    content_type: str | None = None
    sha256: str = Field(..., description="Hash of the body (canonical form for JSON)")
    shape: str | None = Field(
        None, description="JSON only: hash of keys, types and list lengths, ignoring values"
    )


class RecordedRequest(BaseModel):
    """The HTTP request that produced a trace, kept so it can be replayed."""

    method: str
    path: str = Field(..., description="Path including the query string")
    base_url: str = Field(..., description="scheme://host[:port] the app was reached at")
    headers: dict[str, str] = {}
    body: str | None = None
    body_encoding: Literal["utf-8", "base64"] | None = None
    body_truncated: bool = False
    status_code: int | None = None
    response: ResponseFingerprint | None = None


class Trace(BaseModel):
    name: str
    id: int | str = Field(description="The id of the trace")
    timestamp: str = ""
    duration: float = 0
    data: dict[Any, Any] | None = None
    request: RecordedRequest | None = None


class TraceCreate(BaseModel):
    id: str = Field(
        description="The id of the trace",
        exclude=True,
        default_factory=lambda: uuid4().hex,
    )
    raw_trace: dict[Any, Any]
    name: str
    request: RecordedRequest | None = None
    timestamp: str = Field(
        description="The timestamp of the trace",
        default_factory=lambda: str(time.time()),
    )

    @computed_field
    @property
    def duration(self) -> float:
        any_trace_to_analize = any(
            True for trace in self.raw_trace.get("traceEvents", []) if trace.get("ts")
        )
        if not any_trace_to_analize:
            return 0

        start = min(
            trace.get("ts", 0) for trace in self.raw_trace.get("traceEvents", []) if trace.get("ts")
        )
        end = max(trace.get("ts", 0) for trace in self.raw_trace.get("traceEvents", []))
        return end - start
