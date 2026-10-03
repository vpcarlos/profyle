import time
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field


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
    headline: str | None = Field(None, description="Main finding of the stored digest")


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
