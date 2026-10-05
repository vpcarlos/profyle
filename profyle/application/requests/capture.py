"""Build the replayable description of an HTTP request (see `profyle replay`).

Credentials are redacted before a trace is stored (see `redact`) unless the
`capture_secrets` setting is on: traces live in a local SQLite file and their digests
are read by AI assistants.
"""

import base64
from collections.abc import Iterable

from profyle.domain.trace import RecordedRequest

MAX_BODY_BYTES = 64 * 1024
REDACTED = "[redacted]"

SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "x-api-key",
    "x-auth-token",
    "x-csrf-token",
    "x-csrftoken",
}
# Recomputed or meaningless when the request is sent again.
DROPPED_HEADERS = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "accept-encoding",
    "upgrade",
    "te",
}


def build_recorded_request(
    method: str,
    path: str,
    scheme: str,
    host: str,
    headers: Iterable[tuple[str, str]],
    body: bytes | None = None,
    body_truncated: bool = False,
    status_code: int | None = None,
) -> RecordedRequest:
    clean_headers = {
        name.lower(): value for name, value in headers if name.lower() not in DROPPED_HEADERS
    }

    body_text, encoding = None, None
    if body and not body_truncated:
        try:
            body_text, encoding = body.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            body_text, encoding = base64.b64encode(body).decode("ascii"), "base64"

    return RecordedRequest(
        method=method.upper(),
        path=path or "/",
        base_url=f"{scheme or 'http'}://{host or 'localhost'}",
        headers=clean_headers,
        body=body_text,
        body_encoding=encoding,
        body_truncated=body_truncated,
        status_code=status_code,
    )


def redact(request: RecordedRequest) -> RecordedRequest:
    """The request with its credentials (auth headers, cookies, API keys) hidden."""
    headers = {
        name: REDACTED if name in SENSITIVE_HEADERS else value
        for name, value in request.headers.items()
    }
    return request.model_copy(update={"headers": headers})


def decode_body(request: RecordedRequest) -> bytes | None:
    if request.body is None:
        return None
    if request.body_encoding == "base64":
        return base64.b64decode(request.body)
    return request.body.encode("utf-8")
