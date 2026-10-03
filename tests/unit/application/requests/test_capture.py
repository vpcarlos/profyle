from profyle.application.requests.capture import (
    REDACTED,
    build_recorded_request,
    decode_body,
    redact,
)


def build(headers, body=None, **kwargs):
    return build_recorded_request(
        method="post",
        path="/orders?x=1",
        scheme="http",
        host="localhost:8000",
        headers=headers,
        body=body,
        **kwargs,
    )


def test_redacts_credentials_and_drops_hop_by_hop_headers():
    request = redact(
        build(
            [
                ("Authorization", "Bearer secret"),
                ("Cookie", "session=abc"),
                ("Content-Type", "application/json"),
                ("Host", "localhost:8000"),
                ("Content-Length", "2"),
            ],
            body=b"{}",
            status_code=201,
        )
    )

    assert request.method == "POST"
    assert request.base_url == "http://localhost:8000"
    assert request.headers == {
        "authorization": REDACTED,
        "cookie": REDACTED,
        "content-type": "application/json",
    }
    assert request.body == "{}"
    assert request.status_code == 201


def test_credentials_are_kept_until_redacted():
    request = build([("Authorization", "Bearer secret")])

    assert request.headers["authorization"] == "Bearer secret"
    assert redact(request).headers["authorization"] == REDACTED


def test_binary_body_round_trips_as_base64():
    request = build([], body=b"\xff\x00binary")

    assert request.body_encoding == "base64"
    assert decode_body(request) == b"\xff\x00binary"


def test_truncated_body_is_not_stored():
    request = build([], body=b"partial", body_truncated=True)

    assert request.body is None
    assert request.body_truncated
