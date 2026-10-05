"""Send a recorded request again so a fix can be measured on a fresh trace."""

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from profyle.application.requests.capture import REDACTED, decode_body
from profyle.application.requests.fingerprint import fingerprint
from profyle.domain.trace import RecordedRequest, ResponseFingerprint

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "testserver"}


class ReplayRefused(ValueError):
    pass


@dataclass
class ReplayResponse:
    status_code: int | None
    elapsed_ms: float
    error: str | None = None
    fingerprint: ResponseFingerprint | None = None


def is_local(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host in LOCAL_HOSTS or host.endswith(".localhost")


def check_replayable(
    request: RecordedRequest,
    base_url: str,
    allow_unsafe_method: bool,
    allow_remote: bool = False,
) -> None:
    if not is_local(base_url) and not allow_remote:
        raise ReplayRefused(
            f"Refusing to replay against {base_url}: only local hosts are allowed (set "
            "PROFYLE_REPLAY_ALLOW_REMOTE=true, or replay_allow_remote = true in "
            "[tool.profyle], to override)."
        )
    if request.method not in SAFE_METHODS and not allow_unsafe_method:
        raise ReplayRefused(
            f"{request.method} {request.path} may have side effects (create, update or "
            "delete data). Confirm with the user before replaying it with "
            "allow_unsafe_method=true."
        )
    if request.body_truncated:
        raise ReplayRefused(
            "The request body was larger than 64 KB and was not recorded, so the request "
            "cannot be replayed faithfully."
        )


def send(
    request: RecordedRequest,
    base_url: str | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: float = 120,
) -> ReplayResponse:
    headers = {k: v for k, v in request.headers.items() if v != REDACTED}
    headers.update({k.lower(): v for k, v in (extra_headers or {}).items()})
    url = (base_url or request.base_url).rstrip("/") + request.path
    http_request = urllib.request.Request(
        url, data=decode_body(request), headers=headers, method=request.method
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            body = response.read()
            status, content_type = response.status, response.headers.get("Content-Type")
    except urllib.error.HTTPError as error:
        body = error.read()
        status, content_type = error.code, error.headers.get("Content-Type")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        reason = getattr(error, "reason", error)
        return ReplayResponse(None, _elapsed(start), f"{url}: {reason}")
    return ReplayResponse(status, _elapsed(start), fingerprint=fingerprint(body, content_type))


def redacted_headers(request: RecordedRequest) -> list[str]:
    return sorted(k for k, v in request.headers.items() if v == REDACTED)


def _elapsed(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
