"""Canonical byte bundles for focused generation replay checks."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Mapping


ArtifactSource = bytes | bytearray | memoryview | str | os.PathLike[str]
ArtifactSet = Mapping[str, ArtifactSource]
_BUNDLE_MAGIC = b"canonical-generation-replay-v1\x00"


class CanonicalReplayMismatch(AssertionError):
    """Raised when replayed canonical artifacts differ from the reference."""


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
    "build_canonical_bundle",
    "verify_canonical_replay",
]
