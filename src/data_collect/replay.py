"""Canonical byte bundles for focused generation replay checks."""

from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


ArtifactSource = bytes | bytearray | memoryview | str | os.PathLike[str]
ArtifactSet = Mapping[str, ArtifactSource]
_BUNDLE_MAGIC = b"canonical-generation-replay-v1\x00"
REPLAY_CONTRACT_SCHEMA_VERSION = "generation_replay_contract_v1"


class CanonicalReplayMismatch(AssertionError):
    """Raised when replayed canonical artifacts differ from the reference."""


def parse_canonical_bundle(bundle: bytes) -> dict[str, bytes]:
    """Strictly parse a canonical bundle without accepting alternate encodings."""

    if not isinstance(bundle, bytes):
        raise ValueError("Canonical bundle must be bytes")
    if not bundle.startswith(_BUNDLE_MAGIC):
        raise ValueError("Canonical bundle has invalid magic")
    cursor = len(_BUNDLE_MAGIC)

    def take_length(label: str) -> int:
        nonlocal cursor
        end = cursor + 8
        if end > len(bundle):
            raise ValueError(f"Canonical bundle is truncated before {label}")
        value = int.from_bytes(bundle[cursor:end], "big")
        cursor = end
        return value

    entry_count = take_length("entry count")
    entries: dict[str, bytes] = {}
    previous_path: str | None = None
    for index in range(entry_count):
        path_length = take_length(f"entry {index} path length")
        path_end = cursor + path_length
        if path_end > len(bundle):
            raise ValueError(f"Canonical bundle is truncated in entry {index} path")
        try:
            relative_path = bundle[cursor:path_end].decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"Canonical bundle entry {index} path is not UTF-8") from error
        cursor = path_end
        relative_path = _canonical_relative_path(relative_path)
        if previous_path is not None and relative_path <= previous_path:
            raise ValueError("Canonical bundle paths must be unique and strictly sorted")
        previous_path = relative_path

        content_length = take_length(f"entry {index} content length")
        content_end = cursor + content_length
        if content_end > len(bundle):
            raise ValueError(f"Canonical bundle is truncated in entry {index} content")
        entries[relative_path] = bundle[cursor:content_end]
        cursor = content_end

    if cursor != len(bundle):
        raise ValueError("Canonical bundle has trailing data")
    if build_canonical_bundle(entries) != bundle:
        raise ValueError("Canonical bundle is not canonical")
    return entries


def build_canonical_bundle(artifacts: ArtifactSet) -> bytes:
    """Serialize relative artifact names and exact contents deterministically.

    Mapping keys must already be canonical POSIX relative paths. Values may be
    bytes-like objects or filesystem paths. Source paths and all other runtime
    metadata are excluded from the serialized bundle by construction.
    """

    entries = [(_canonical_relative_path(name), _read_exact_bytes(source)) for name, source in artifacts.items()]
    entries.sort(key=lambda entry: entry[0])

    bundle = bytearray(_BUNDLE_MAGIC)
    bundle.extend(len(entries).to_bytes(8, "big"))
    for relative_path, content in entries:
        encoded_path = relative_path.encode("utf-8")
        bundle.extend(len(encoded_path).to_bytes(8, "big"))
        bundle.extend(encoded_path)
        bundle.extend(len(content).to_bytes(8, "big"))
        bundle.extend(content)
    return bytes(bundle)


def build_replay_contract(
    *,
    contract_id: str,
    seed: int,
    max_attempts_per_bucket: int,
    candidate_multiplier: int,
    require_rendering: bool,
    selected_domains: Sequence[str],
    selected_splits: Sequence[str],
    quotas_by_split: Mapping[str, Mapping[str, int]],
    source_artifacts: ArtifactSet,
) -> bytes:
    """Build the immutable, path-free contract required for generation replay."""

    source_digests = {
        _canonical_relative_path(name): hashlib.sha256(_read_exact_bytes(source)).hexdigest()
        for name, source in source_artifacts.items()
    }
    payload = {
        "candidate_multiplier": candidate_multiplier,
        "contract_id": contract_id,
        "max_attempts_per_bucket": max_attempts_per_bucket,
        "quotas_by_split": {
            split: {bucket: int(count) for bucket, count in sorted(quotas.items())}
            for split, quotas in sorted(quotas_by_split.items())
        },
        "require_rendering": require_rendering,
        "schema_version": REPLAY_CONTRACT_SCHEMA_VERSION,
        "seed": seed,
        "selected_domains": list(selected_domains),
        "selected_splits": list(selected_splits),
        "source_artifact_digests": dict(sorted(source_digests.items())),
    }
    return (
        json.dumps(payload, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def verify_canonical_replay(reference_artifacts: ArtifactSet, replayed_artifacts: ArtifactSet) -> bytes:
    """Build two fresh bundles and require byte-for-byte equality.

    The matching canonical bundle is returned for callers that want to persist
    or hash the verified result. A mismatch identifies missing, unexpected, and
    byte-changed relative artifact paths.
    """

    reference_bundle = build_canonical_bundle(reference_artifacts)
    replayed_bundle = build_canonical_bundle(replayed_artifacts)
    if reference_bundle == replayed_bundle:
        return reference_bundle

    reference = _materialize(reference_artifacts)
    replayed = _materialize(replayed_artifacts)
    missing = sorted(reference.keys() - replayed.keys())
    unexpected = sorted(replayed.keys() - reference.keys())
    changed = sorted(path for path in reference.keys() & replayed.keys() if reference[path] != replayed[path])
    details = []
    if missing:
        details.append(f"missing={missing!r}")
    if unexpected:
        details.append(f"unexpected={unexpected!r}")
    if changed:
        details.append(f"changed={changed!r}")
    raise CanonicalReplayMismatch("Canonical replay differs: " + ", ".join(details))


def _materialize(artifacts: ArtifactSet) -> dict[str, bytes]:
    return {_canonical_relative_path(name): _read_exact_bytes(source) for name, source in artifacts.items()}


def _read_exact_bytes(source: ArtifactSource) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, (bytearray, memoryview)):
        return bytes(source)
    return Path(source).read_bytes()


def _canonical_relative_path(relative_path: str) -> str:
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("Artifact path must be a non-empty relative POSIX path")
    if "\\" in relative_path:
        raise ValueError(f"Artifact path must be a canonical relative POSIX path: {relative_path!r}")
    raw_parts = relative_path.split("/")
    path = PurePosixPath(relative_path)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or path.as_posix() != relative_path
        or (raw_parts and raw_parts[0].endswith(":"))
    ):
        raise ValueError(f"Artifact path must be a canonical relative POSIX path: {relative_path!r}")
    return relative_path


__all__ = [
    "ArtifactSet",
    "ArtifactSource",
    "CanonicalReplayMismatch",
    "REPLAY_CONTRACT_SCHEMA_VERSION",
    "build_canonical_bundle",
    "build_replay_contract",
    "parse_canonical_bundle",
    "verify_canonical_replay",
]
