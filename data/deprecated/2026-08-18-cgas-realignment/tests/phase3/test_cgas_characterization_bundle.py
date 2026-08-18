from __future__ import annotations

import hashlib

import pytest

from scripts.phase3.cgas_characterization_bundle import (
    BundleError,
    BundleMember,
    build_bundle,
    parse_bundle,
)


def test_bundle_is_deterministic_and_round_trips_exact_logical_members() -> None:
    # Given: the only three logical final members in a noncanonical input order.
    members = (
        BundleMember("characterization_manifest.json", b'{"owner_approved":false}\n'),
        BundleMember("run-contract.json", b'{"contract_version":"v1"}'),
        BundleMember("characterization.jsonl", b'{"instance_id":"a"}\n'),
    )

    # When: independent calls serialize the logical artifact.
    first = build_bundle(members, "f" * 64)
    second = build_bundle(tuple(reversed(members)), "f" * 64)

    # Then: bytes are canonical and parsing restores the exact canonical member order.
    assert first == second
    parsed = parse_bundle(first)
    assert parsed.run_fingerprint == "f" * 64
    assert tuple(member.name for member in parsed.members) == (
        "run-contract.json",
        "characterization.jsonl",
        "characterization_manifest.json",
    )
    assert tuple(hashlib.sha256(member.contents).hexdigest() for member in parsed.members) == (
        hashlib.sha256(b'{"contract_version":"v1"}').hexdigest(),
        hashlib.sha256(b'{"instance_id":"a"}\n').hexdigest(),
        hashlib.sha256(b'{"owner_approved":false}\n').hexdigest(),
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: b"wrong-magic" + payload[11:],
        lambda payload: payload[:11] + (1).to_bytes(4, "big") + payload[15:],
        lambda payload: payload[:-1],
        lambda payload: payload + b"trailing",
    ),
)
def test_bundle_rejects_malformed_or_nonexact_bytes(mutate) -> None:
    # Given: a valid deterministic bundle and one independent wire corruption.
    payload = build_bundle(
        (
            BundleMember("run-contract.json", b"{}"),
            BundleMember("characterization.jsonl", b"{}\n"),
            BundleMember("characterization_manifest.json", b"{}\n"),
        ),
        "a" * 64,
    )

    # When: the streaming parser receives malformed input.
    with pytest.raises(BundleError):
        parse_bundle(mutate(payload))

    # Then: no malformed byte sequence is accepted.


def test_bundle_converts_invalid_utf8_header_to_typed_error() -> None:
    # Given: a framed header whose first byte is not valid UTF-8.
    payload = b"cgas-final-bundle-v1\n" + (2).to_bytes(4, "big") + b"\xff{"

    # When: the bundle boundary parses the malformed frame.
    with pytest.raises(BundleError, match="noncanonical_header"):
        parse_bundle(payload)

    # Then: callers receive the stable typed error rather than a decoder exception.
