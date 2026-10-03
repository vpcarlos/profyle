"""Fingerprint response bodies so a performance fix can be checked for behavior changes.

Two levels: `sha256` says the body is byte-for-byte the same (JSON is canonicalised
first, so key order does not matter); `shape` says a JSON body has the same structure
(keys, value types, list lengths) even when values such as timestamps or ids differ.
"""

import hashlib
import json
from typing import Any, Literal

from profyle.domain.trace import ResponseFingerprint

MAX_FINGERPRINT_BYTES = 2 * 1024 * 1024

Verdict = Literal["identical", "same_shape", "different", "unknown"]


def fingerprint(body: bytes, content_type: str | None = None) -> ResponseFingerprint:
    data = _as_json(body, content_type)
    if data is _NOT_JSON:
        return ResponseFingerprint(
            size=len(body), content_type=content_type, sha256=_sha256(body)
        )
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    shape = json.dumps(_skeleton(data), sort_keys=True, separators=(",", ":"))
    return ResponseFingerprint(
        size=len(body),
        content_type=content_type,
        sha256=_sha256(canonical.encode()),
        shape=_sha256(shape.encode()),
    )


def compare(
    before: ResponseFingerprint | None, after: ResponseFingerprint | None
) -> Verdict:
    if before is None or after is None:
        return "unknown"
    if before.sha256 == after.sha256:
        return "identical"
    if before.shape and before.shape == after.shape:
        return "same_shape"
    return "different"


VERDICT_TEXT = {
    "identical": "identical",
    "same_shape": "same structure, values differ",
    "different": "DIFFERENT",
    "unknown": "not recorded",
}


_NOT_JSON = object()


def _as_json(body: bytes, content_type: str | None) -> Any:
    if not body or (content_type and "json" not in content_type.lower()):
        return _NOT_JSON
    try:
        return json.loads(body)
    except ValueError:
        return _NOT_JSON


def _skeleton(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _skeleton(item) for key, item in value.items()}
    if isinstance(value, list):
        # Length plus the distinct element structures (order-insensitive).
        shapes = {json.dumps(_skeleton(item), sort_keys=True) for item in value}
        return ["list", len(value), sorted(shapes)]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if value is None:
        return "null"
    return "string"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
