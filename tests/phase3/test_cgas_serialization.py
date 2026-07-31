from __future__ import annotations

import math

import pytest

from scripts.phase3.cgas_serialization import CanonicalSerializationError, canonical_json_line, canonical_json_object


class UnsupportedJsonValue:
    pass


def test_canonical_json_object_and_line_bytes_are_stable() -> None:
    # Given: equivalent nested JSON objects with different insertion orders.
    first = {"zeta": 2, "alpha": {"flag": True, "label": "ok"}}
    second = {"alpha": {"label": "ok", "flag": True}, "zeta": 2}

    # When: each crosses the strict canonical-object boundary.
    first_bytes = canonical_json_object(first)
    second_bytes = canonical_json_object(second)

    # Then: object and JSONL line bytes are deterministic and compact.
    assert first_bytes == b'{"alpha":{"flag":true,"label":"ok"},"zeta":2}'
    assert first_bytes == second_bytes
    assert canonical_json_line(first) == first_bytes + b"\n"


@pytest.mark.parametrize(
    ("value", "reason"),
    (
        ({"score": 1.5}, "float_unsupported"),
        ({"score": math.nan}, "non_finite_float"),
        ({"score": math.inf}, "non_finite_float"),
        ({"items": ["not", "allowed"]}, "array_unsupported"),
        (["not", "an", "object"], "root_not_object"),
        ({"blob": b"not-json"}, "bytes_unsupported"),
        ({"nested": ("not", "allowed")}, "array_unsupported"),
        ({"nested": {"not", "allowed"}}, "unsupported_value"),
        ({"nested": {1: "not-json"}}, "object_key_not_string"),
        ({"nested": UnsupportedJsonValue()}, "unsupported_value"),
    ),
)
def test_canonical_boundary_rejects_unsupported_values(value: object, reason: str) -> None:
    # Given: untrusted content outside the strict canonical JSON object contract.

    # When: it crosses the canonical object boundary.
    with pytest.raises(CanonicalSerializationError) as raised:
        canonical_json_object(value)

    # Then: rejection names the stable machine-readable reason.
    assert raised.value.reason.value == reason
