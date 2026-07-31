from __future__ import annotations

from dataclasses import FrozenInstanceError
from collections.abc import Callable

import pytest

from scripts.phase3.cgas_characterization_types import (
    CanonicalRowIndex,
    CharacterizationArtifactDigest,
    CharacterizationReport,
    CharacterizationRun,
    SourceManifestDigest,
    CharacterizationTypeError,
    parse_canonical_row_index,
    parse_characterization_artifact_digest,
    parse_source_manifest_digest,
)
from scripts.phase3.cgas_partition_contracts import assert_expected_population
from cgas_characterization_support import synthetic_characterization_population


def test_characterization_values_preserve_branded_identity_and_are_frozen() -> None:
    # Given: identifiers parsed into their distinct characterization contracts.
    row_index = CanonicalRowIndex(7)
    source_digest = SourceManifestDigest("a" * 64)
    run = CharacterizationRun(row_index=row_index, source_digest=source_digest)

    # When: a typed report binds the run to its artifact digest.
    report = CharacterizationReport(
        run=run,
        artifact_digest=CharacterizationArtifactDigest("b" * 64),
        row_count=481,
    )

    # Then: static brands survive construction and values cannot be mutated.
    annotated_index: CanonicalRowIndex = row_index
    annotated_digest: SourceManifestDigest = source_digest
    assert int(annotated_index) == 7
    assert str(annotated_digest) == "a" * 64
    assert report.run is run
    with pytest.raises(FrozenInstanceError):
        setattr(run, "row_index", CanonicalRowIndex(8))


def test_explicitly_synthetic_population_has_the_complete_contract_shape() -> None:
    # Given: the test-only, explicitly synthetic characterization population.
    rows = synthetic_characterization_population()

    # When: its split and object dimensions are counted independently.
    split_counts = {split: sum(row.split == split for row in rows) for split in ("train", "dev", "test")}
    object_counts = {count: sum(row.object_count == count for row in rows) for count in (4, 8, 12)}

    # Then: it models the exact 481-row contract without reading a production corpus.
    assert len(rows) == 481
    assert split_counts == {"train": 402, "dev": 39, "test": 40}
    assert object_counts == {4: 190, 8: 198, 12: 93}
    assert all(row.instance_id.startswith("synthetic-characterization-") for row in rows)
    assert_expected_population(
        {"instance_id": row.instance_id, "split": row.split, "object_count": row.object_count}
        for row in rows
    )


@pytest.mark.parametrize("raw", (1.5, -1, None))
def test_parse_canonical_row_index_rejects_noncanonical_inputs(raw: object) -> None:
    # Given: a value that is not a nonnegative integer index.

    # When: it crosses the typed row-index parser boundary.
    with pytest.raises(CharacterizationTypeError) as raised:
        parse_canonical_row_index(raw)

    # Then: the boundary never leaks a raw type error or implicit None.
    assert raised.value.reason.value == "invalid_row_index"


@pytest.mark.parametrize("parser", (parse_source_manifest_digest, parse_characterization_artifact_digest))
@pytest.mark.parametrize("raw", (None, 42, "a" * 63))
def test_digest_parsers_reject_none_wrong_type_and_malformed_strings(
    parser: Callable[[object], SourceManifestDigest | CharacterizationArtifactDigest], raw: object
) -> None:
    # Given: a digest input that is absent, not text, or malformed text.

    # When: it crosses either typed digest parser boundary.
    with pytest.raises(CharacterizationTypeError) as raised:
        parser(raw)

    # Then: both digest brands fail with the shared typed reason.
    assert raised.value.reason.value == "invalid_digest"
