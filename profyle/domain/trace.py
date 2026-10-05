from typing import Any, Literal

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
    """A stored trace. `data` (the raw VizTracer trace, often megabytes) is only loaded
    when asked for."""

    id: int
    name: str = Field(description='What was traced, e.g. "GET /users?page=2"')
    timestamp: str = ""
    duration: float = Field(0, description="Microseconds, VizTracer's unit")
    data: dict[str, Any] | None = None
    request: RecordedRequest | None = None
    headline: str | None = Field(None, description="Main finding of the stored digest")

    @property
    def duration_ms(self) -> float:
        return self.duration / 1000


class NewTrace(BaseModel):
    """A trace about to be stored; the repository assigns its id and timestamp."""

    name: str
    raw_trace: dict[str, Any]
    request: RecordedRequest | None = None

    @computed_field
    @property
    def duration(self) -> float:
        """From the first to the last event, in microseconds."""
        starts, ends = [], []
        for event in self.raw_trace.get("traceEvents", []):
            if event.get("ts"):
                starts.append(event["ts"])
                ends.append(event["ts"] + (event.get("dur") or 0))
        return max(ends) - min(starts) if starts else 0
