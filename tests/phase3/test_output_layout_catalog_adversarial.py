from __future__ import annotations

from dataclasses import replace
import json

import pytest

from scripts.phase3.output_layout_contracts import (
    DEFAULT_OUTPUT_LAYOUT,
    OutputLayoutContractError,
    serialize_catalog,
    validate_output_layout,
)


EXPECTED_VIEW_TARGET_KINDS = (
    "file",
    "file",
    "file",
    "file",
    "file",
    "file",
    "file",
    "file",
    "file",
    "directory",
    "directory",
    "directory",
    "directory",
    "directory",
    "file",
)


def test_catalog_declares_exact_view_target_kinds() -> None:
    # Given: the approved immutable output-layout catalog.
    contract = DEFAULT_OUTPUT_LAYOUT

    # When: the view-link target kinds are inspected.
    target_kinds = tuple(link.target_kind for link in contract.view_links)

    # Then: every approved view target declares its file or directory kind.
    assert target_kinds == EXPECTED_VIEW_TARGET_KINDS


def test_catalog_serialization_includes_view_target_kinds() -> None:
    # Given: the approved immutable output-layout catalog.
    contract = DEFAULT_OUTPUT_LAYOUT

    # When: the catalog is serialized.
    catalog = json.loads(serialize_catalog(contract))

    # Then: the stable view-link payload preserves each target kind in order.
    assert tuple(link["target_kind"] for link in catalog["view_links"]) == EXPECTED_VIEW_TARGET_KINDS


@pytest.mark.parametrize("root_index", range(3))
def test_catalog_rejects_each_same_shape_protected_root_alteration(root_index: int) -> None:
    # Given: a protected-root rationale changed without affecting structure or paths.
    contract = DEFAULT_OUTPUT_LAYOUT
    altered_roots = tuple(
        replace(root, rationale=f"synthetic altered root {root_index}") if index == root_index else root
        for index, root in enumerate(contract.protected_roots)
    )
    altered_contract = replace(contract, protected_roots=altered_roots)

    # When: the altered catalog is validated.
    with pytest.raises(OutputLayoutContractError, match="approved immutable default"):
        validate_output_layout(altered_contract)

    # Then: structural validity cannot authorize a different protected-root catalog.


@pytest.mark.parametrize("relocation_index", range(12))
def test_catalog_rejects_each_same_shape_relocation_alteration(relocation_index: int) -> None:
    # Given: a relocation classification changed without affecting topology or categories.
    contract = DEFAULT_OUTPUT_LAYOUT
    altered_relocations = tuple(
        replace(relocation, classification=f"synthetic altered relocation {relocation_index}")
        if index == relocation_index
        else relocation
        for index, relocation in enumerate(contract.relocations)
    )
    altered_contract = replace(contract, relocations=altered_relocations)

    # When: the altered catalog is validated.
    with pytest.raises(OutputLayoutContractError, match="approved immutable default"):
        validate_output_layout(altered_contract)

    # Then: structural validity cannot authorize a different relocation catalog.


@pytest.mark.parametrize("link_index", range(15))
def test_catalog_rejects_each_same_shape_view_link_alteration(link_index: int) -> None:
    # Given: one view-link target kind changed without affecting link topology.
    contract = DEFAULT_OUTPUT_LAYOUT
    altered_links = tuple(
        replace(
            link,
            target_kind="directory" if link.target_kind == "file" else "file",
        )
        if index == link_index
        else link
        for index, link in enumerate(contract.view_links)
    )
    altered_contract = replace(contract, view_links=altered_links)

    # When: the altered catalog is validated.
    with pytest.raises(OutputLayoutContractError, match="approved immutable default"):
        validate_output_layout(altered_contract)

    # Then: structural validity cannot authorize a different view-link catalog.
