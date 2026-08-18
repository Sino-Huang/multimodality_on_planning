from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.phase3.output_layout_contracts import (
    DEFAULT_OUTPUT_LAYOUT,
    OutputLayoutContractError,
    validate_output_layout,
)


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


@pytest.mark.parametrize("relocation_index", range(len(DEFAULT_OUTPUT_LAYOUT.relocations)))
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
