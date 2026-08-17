from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

from .cgas_serialization import CanonicalSerializationError, canonical_json_object

_MAGIC: Final = b"cgas-final-bundle-v1\n"
_LENGTH_BYTES: Final = 4
_MAX_HEADER_BYTES: Final = 16 * 1024
_MAX_MEMBER_BYTES: Final = 128 * 1024 * 1024
_PROFILE: Final = "regular_bundle_linkat_v1"
_VERSION: Final = "cgas-final-bundle-v1"
_NAMES: Final = ("run-contract.json", "characterization.jsonl", "characterization_manifest.json")


@dataclass(frozen=True, slots=True)
class BundleError(ValueError):
    rule: str

    def __str__(self) -> str:
        return f"characterization bundle {self.rule}"


@dataclass(frozen=True, slots=True)
class BundleMember:
    name: str
    contents: bytes


@dataclass(frozen=True, slots=True)
class ParsedBundle:
    run_fingerprint: str
    members: tuple[BundleMember, ...]


def build_bundle(members: tuple[BundleMember, ...], run_fingerprint: str) -> bytes:
    """Encode the exact logical final members into canonical bundle bytes."""
    ordered = _ordered_members(members)
    fingerprint = _fingerprint(run_fingerprint)
    header = canonical_json_object(
        {
            "profile": _PROFILE,
            "run_fingerprint": fingerprint,
            "version": _VERSION,
            **{
                member.name: {"mode": 0o600, "sha256": hashlib.sha256(member.contents).hexdigest(), "size": len(member.contents)}
                for member in ordered
            },
        }
    )
    if len(header) > _MAX_HEADER_BYTES:
        raise BundleError("header_too_large")
    return _MAGIC + len(header).to_bytes(_LENGTH_BYTES, "big") + header + b"".join(member.contents for member in ordered)


def parse_bundle(contents: bytes) -> ParsedBundle:
    """Parse one exact bundle without extracting or writing logical members."""
    prefix = len(_MAGIC) + _LENGTH_BYTES
    if len(contents) < prefix or contents[: len(_MAGIC)] != _MAGIC:
        raise BundleError("bad_magic")
    header_size = int.from_bytes(contents[len(_MAGIC) : prefix], "big")
    if header_size < 2 or header_size > _MAX_HEADER_BYTES or len(contents) < prefix + header_size:
        raise BundleError("bad_header_length")
    header = contents[prefix : prefix + header_size]
    raw = _header(header)
    offset = prefix + header_size
    parsed: list[BundleMember] = []
    for name in _NAMES:
        size, digest = _descriptor(raw[name])
        end = offset + size
        if end > len(contents):
            raise BundleError("truncated_member")
        member = contents[offset:end]
        if hashlib.sha256(member).hexdigest() != digest:
            raise BundleError("member_digest_mismatch")
        parsed.append(BundleMember(name, member))
        offset = end
    if offset != len(contents):
        raise BundleError("trailing_bytes")
    return ParsedBundle(_fingerprint(raw["run_fingerprint"]), tuple(parsed))


def _ordered_members(members: tuple[BundleMember, ...]) -> tuple[BundleMember, ...]:
    by_name = {member.name: member for member in members}
    if len(by_name) != len(members) or set(by_name) != set(_NAMES):
        raise BundleError("logical_member_profile")
    for member in by_name.values():
        if len(member.contents) > _MAX_MEMBER_BYTES:
            raise BundleError("member_too_large")
    return tuple(by_name[name] for name in _NAMES)


def _header(contents: bytes) -> dict[str, object]:
    try:
        raw = json.loads(contents)
        canonical = canonical_json_object(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, CanonicalSerializationError) as error:
        raise BundleError("noncanonical_header") from error
    if not isinstance(raw, dict) or canonical != contents or set(raw) != {"profile", "run_fingerprint", "version", *_NAMES}:
        raise BundleError("header_fields")
    if raw["profile"] != _PROFILE or raw["version"] != _VERSION:
        raise BundleError("header_profile")
    return raw


def _descriptor(raw: object) -> tuple[int, str]:
    if not isinstance(raw, dict) or set(raw) != {"mode", "sha256", "size"}:
        raise BundleError("member_fields")
    size, digest, mode = raw["size"], raw["sha256"], raw["mode"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0 or size > _MAX_MEMBER_BYTES:
        raise BundleError("member_size")
    if mode != 0o600 or not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise BundleError("member_metadata")
    return size, digest


def _fingerprint(raw: object) -> str:
    if not isinstance(raw, str) or len(raw) != 64 or any(character not in "0123456789abcdef" for character in raw):
        raise BundleError("run_fingerprint")
    return raw
