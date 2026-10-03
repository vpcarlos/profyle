from profyle.application.requests.fingerprint import compare, fingerprint


def test_json_key_order_does_not_matter():
    a = fingerprint(b'{"a": 1, "b": [1, 2]}', "application/json")
    b = fingerprint(b'{"b":[1,2],"a":1}', "application/json")

    assert compare(a, b) == "identical"


def test_same_structure_with_different_values():
    a = fingerprint(b'{"id": 1, "at": "2026-01-01", "items": [{"x": 1}]}', "application/json")
    b = fingerprint(b'{"id": 2, "at": "2026-02-02", "items": [{"x": 9}]}', "application/json")

    assert compare(a, b) == "same_shape"


def test_missing_field_or_fewer_items_is_different():
    full = fingerprint(b'{"items": [{"x": 1}, {"x": 2}]}', "application/json")
    fewer = fingerprint(b'{"items": [{"x": 1}]}', "application/json")
    no_field = fingerprint(b'{"items": [{}, {}]}', "application/json")

    assert compare(full, fewer) == "different"
    assert compare(full, no_field) == "different"


def test_non_json_bodies_compare_bytes():
    a = fingerprint(b"<html>ok</html>", "text/html")
    b = fingerprint(b"<html>ok</html>", "text/html")
    c = fingerprint(b"<html>ko</html>", "text/html")

    assert a.shape is None
    assert compare(a, b) == "identical"
    assert compare(a, c) == "different"


def test_unknown_when_a_side_is_missing():
    assert compare(None, fingerprint(b"{}", "application/json")) == "unknown"


def test_invalid_json_is_compared_as_bytes():
    broken = fingerprint(b"{not json", "application/json")

    assert broken.shape is None


def test_null_values_are_part_of_the_structure():
    a = fingerprint(b'{"customer": null}', "application/json")
    b = fingerprint(b'{"customer": "c0"}', "application/json")

    assert compare(a, b) == "different"
