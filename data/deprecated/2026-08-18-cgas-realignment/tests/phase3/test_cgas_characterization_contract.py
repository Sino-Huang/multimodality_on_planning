from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.phase3.cgas_characterization_contract import (
    CharacterizationRunContractError,
    _module_roots,
    build_characterization_run_contract,
)


def test_run_contract_binds_exact_source_population_pddl_and_configuration(tmp_path: Path) -> None:
    # Given: a complete synthetic accepted population and a local implementation package.
    repository = _repository(tmp_path)
    manifest = _manifest(repository, duplicate=False)

    # When: the immutable contract is built from the raw source bytes.
    baseline = build_characterization_run_contract(manifest, repository, shard_count=3, module_roots=("fixture.runner",))
    changed_manifest = _manifest(repository, duplicate=False, suffix=" ")
    changed = build_characterization_run_contract(changed_manifest, repository, shard_count=3, module_roots=("fixture.runner",))

    # Then: raw bytes, selected identities, PDDL bytes, and run settings are fingerprinted.
    assert baseline.canonical_bytes == build_characterization_run_contract(
        manifest, repository, shard_count=3, module_roots=("fixture.runner",)
    ).canonical_bytes
    assert baseline.fingerprint != changed.fingerprint
    assert baseline.fingerprint != build_characterization_run_contract(
        manifest, repository, shard_count=4, module_roots=("fixture.runner",)
    ).fingerprint
    assert _mapping(baseline.payload["population"])["row_count"] == 481
    assert _mapping(baseline.payload["source"])["manifest_path"] == "accepted0.jsonl"
    assert baseline.payload["shard_count"] == 3


def test_run_contract_changes_for_pddl_and_implementation_bytes(tmp_path: Path) -> None:
    # Given: a valid source population and its static local implementation closure.
    repository = _repository(tmp_path)
    manifest = _manifest(repository, duplicate=False)
    baseline = build_characterization_run_contract(manifest, repository, shard_count=1, module_roots=("fixture.runner",))

    # When: one PDDL byte and then one imported implementation byte drift.
    problem = repository / "problem-4.pddl"
    problem.write_bytes(problem.read_bytes() + b"\n")
    pddl_changed = build_characterization_run_contract(manifest, repository, shard_count=1, module_roots=("fixture.runner",))
    helper = repository / "fixture/helper.py"
    helper.write_text("VALUE = 2\n", encoding="utf-8")
    implementation_changed = build_characterization_run_contract(manifest, repository, shard_count=1, module_roots=("fixture.runner",))

    # Then: scientific input and code changes cannot share a run fingerprint.
    assert baseline.fingerprint != pddl_changed.fingerprint
    assert pddl_changed.fingerprint != implementation_changed.fingerprint


@pytest.mark.parametrize("duplicate", (True,))
def test_run_contract_rejects_duplicate_selected_instance_identity(tmp_path: Path, duplicate: bool) -> None:
    # Given: a 481-row population containing a duplicated selected Blocksworld identity.
    repository = _repository(tmp_path)
    manifest = _manifest(repository, duplicate=duplicate)

    # When: the source boundary parses the accepted population.
    with pytest.raises(CharacterizationRunContractError, match="duplicate_instance_id"):
        build_characterization_run_contract(manifest, repository, shard_count=1, module_roots=("fixture.runner",))

    # Then: no contract can silently bind an ambiguous scientific population.


def test_run_contract_rejects_an_invalid_shard_count(tmp_path: Path) -> None:
    # Given: otherwise valid immutable source and implementation inputs.
    repository = _repository(tmp_path)
    manifest = _manifest(repository, duplicate=False)

    # When: the sharding boundary receives a nonpositive count.
    with pytest.raises(CharacterizationRunContractError, match="invalid_shard_count"):
        build_characterization_run_contract(manifest, repository, shard_count=0, module_roots=("fixture.runner",))

    # Then: the runtime cannot construct an undefined run partitioning contract.


@pytest.mark.parametrize(
    "source,reason",
    (
        ("from .missing import value\n", "unresolved_local_import"),
        ("import importlib\nvalue = importlib.import_module('fixture.helper')\n", "dynamic_import"),
        ("from importlib import import_module as load\nvalue = load('fixture.helper')\n", "dynamic_import"),
        ("from importlib import import_module\nload = import_module\nvalue = load('fixture.helper')\n", "dynamic_import"),
        ("import sys\nsys.path.append('elsewhere')\n", "sys_path_mutation"),
        ("from sys import path\npath.append('elsewhere')\n", "sys_path_mutation"),
        ("from sys import path\nalternate = path\nalternate.append('elsewhere')\n", "sys_path_mutation"),
        ("import os\nos.environ['PYTHONPATH'] = 'elsewhere'\n", "pythonpath_mutation"),
        ("from os import environ as environment\nenvironment['PYTHONPATH'] = 'elsewhere'\n", "pythonpath_mutation"),
        ("from os import environ\nenvironment = environ\nenvironment['PYTHONPATH'] = 'elsewhere'\n", "pythonpath_mutation"),
        ("import site as startup\nstartup.addsitedir('elsewhere')\n", "site_path_mutation"),
        ("import importlib\ngetattr(importlib, 'import_module')('fixture.helper')\n", "dynamic_import_reflection"),
        ("import importlib\nload = getattr(importlib, 'import_module')\nalias = load\nalias('fixture.helper')\n", "dynamic_import_reflection"),
        ("import builtins\ngetattr(builtins, '__import__')('fixture.helper')\n", "dynamic_import_reflection"),
        ("getattr(__builtins__, '__import__')('fixture.helper')\n", "dynamic_import_reflection"),
        ("vars(__builtins__)['__import__']('fixture.helper')\n", "dynamic_import_reflection"),
        ("getattr(__builtins__, 'eval')('1 + 1')\n", "dynamic_code_execution"),
        ("base = __builtins__\nload = getattr(base, '__import__')\nalias = load\nalias('fixture.helper')\n", "dynamic_import_reflection"),
        ("reflect = getattr\nbase = __builtins__\nrun = reflect(base, 'eval')\nrun('1 + 1')\n", "dynamic_code_execution"),
        ("import importlib\nvars(importlib)['import_module']('fixture.helper')\n", "dynamic_import_reflection"),
        ("import importlib\nattribute = getattr\nattribute(importlib, 'import_module')('fixture.helper')\n", "dynamic_import_reflection"),
        ("import importlib\nnamespace = vars\nnamespace(importlib)['import_module']('fixture.helper')\n", "dynamic_import_reflection"),
        ("import sys\np = getattr(sys, 'path')\np.append('elsewhere')\n", "sys_path_reflection"),
        ("import os\ne = getattr(os, 'environ')\ne['PYTHONPATH'] = 'elsewhere'\n", "pythonpath_reflection"),
        ("exec('import fixture.helper')\n", "dynamic_code_execution"),
        ("from builtins import exec as run\nrun('import fixture.helper')\n", "dynamic_code_execution"),
        ("eval('1 + 1')\n", "dynamic_code_execution"),
        ("compile('import fixture.helper', 'x', 'exec')\n", "dynamic_code_execution"),
        ("globals()['load']('fixture.helper')\n", "reflection_namespace_access"),
    ),
)
def test_run_contract_rejects_nonstatic_or_mutable_import_resolution(
    tmp_path: Path, source: str, reason: str
) -> None:
    # Given: a product root with an import-resolution escape hatch.
    repository = _repository(tmp_path, runner_source=source)
    manifest = _manifest(repository, duplicate=False)

    # When: the implementation closure is resolved from AST imports.
    with pytest.raises(CharacterizationRunContractError, match=reason):
        build_characterization_run_contract(manifest, repository, shard_count=1, module_roots=("fixture.runner",))

    # Then: machine-local import behavior cannot enter a reproducible fingerprint.


def test_run_contract_allows_benign_literal_reflection(tmp_path: Path) -> None:
    # Given: static reflection over an unrelated platform capability constant.
    repository = _repository(tmp_path, runner_source="import os\nFLAG = getattr(os, 'O_NOFOLLOW', 0)\n")
    manifest = _manifest(repository, duplicate=False)

    # When: the product module is included in the static implementation closure.
    contract = build_characterization_run_contract(manifest, repository, shard_count=1, module_roots=("fixture.runner",))

    # Then: only import-sensitive reflection is rejected.
    assert "fixture/runner.py" in _mapping(_mapping(contract.payload["implementation"])["files"])


@pytest.mark.parametrize("target", ("runner.py", "__init__.py"))
def test_run_contract_rejects_symlinked_closure_modules(tmp_path: Path, target: str) -> None:
    # Given: a product package whose module or initializer is a symbolic link.
    repository = _repository(tmp_path)
    package = repository / "fixture"
    external = repository / f"external-{target}"
    external.write_text("VALUE = 1\n", encoding="utf-8")
    linked = package / target
    linked.unlink()
    linked.symlink_to(external)
    manifest = _manifest(repository, duplicate=False)

    # When: static closure resolution reaches the linked source file.
    with pytest.raises(CharacterizationRunContractError, match="symlink_local_import"):
        build_characterization_run_contract(manifest, repository, shard_count=1, module_roots=("fixture.runner",))

    # Then: link indirection cannot alter the reviewed implementation inventory.


def test_run_contract_includes_function_conditional_type_and_package_imports(tmp_path: Path) -> None:
    # Given: imports in every syntactic scope plus a package initializer dependency.
    source = """from typing import TYPE_CHECKING\nfrom . import helper\nif TYPE_CHECKING:\n    from . import typing_only\ndef run():\n    from . import function_only\n    return helper.VALUE\nif True:\n    from . import conditional\n"""
    repository = _repository(tmp_path, runner_source=source)
    manifest = _manifest(repository, duplicate=False)

    # When: AST closure is materialized deterministically.
    contract = build_characterization_run_contract(manifest, repository, shard_count=1, module_roots=("fixture.runner",))

    # Then: every local imported module and package initializer is bound by POSIX path.
    paths = list(_mapping(_mapping(contract.payload["implementation"])["files"]))
    assert paths == sorted(paths)
    assert {"fixture/__init__.py", "fixture/conditional.py", "fixture/function_only.py", "fixture/helper.py", "fixture/runner.py", "fixture/typing_only.py"} <= set(paths)


def test_default_product_roots_include_contracts_and_a_verifier_package(tmp_path: Path) -> None:
    # Given: a future verifier represented by a Python package rather than a module file.
    verifier = tmp_path / "scripts/phase3/cgas_characterization_verifier"
    verifier.mkdir(parents=True)
    (verifier / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")

    # When: default product roots are derived for the repository.
    roots = _module_roots(tmp_path, None)

    # Then: contracts and the verifier package are mandatory fingerprint roots.
    assert {"scripts.phase3.cgas_characterization_contract", "scripts.phase3.cgas_characterization_imports", "scripts.phase3.cgas_characterization_verifier"} <= set(roots)


def test_mandatory_contract_root_drift_changes_the_fingerprint(tmp_path: Path) -> None:
    # Given: a source repository containing all default product roots.
    repository = _repository(tmp_path)
    _product_roots(repository)
    manifest = _manifest(repository, duplicate=False)
    baseline = build_characterization_run_contract(manifest, repository, shard_count=1)

    # When: either mandatory contract implementation module changes.
    contract_file = repository / "scripts/phase3/cgas_characterization_contract.py"
    contract_file.write_text("VALUE = 2\n", encoding="utf-8")
    contract_changed = build_characterization_run_contract(manifest, repository, shard_count=1)
    imports_file = repository / "scripts/phase3/cgas_characterization_imports.py"
    imports_file.write_text("VALUE = 2\n", encoding="utf-8")
    imports_changed = build_characterization_run_contract(manifest, repository, shard_count=1)

    # Then: both otherwise independent contract roots affect the run fingerprint.
    assert baseline.fingerprint != contract_changed.fingerprint
    assert contract_changed.fingerprint != imports_changed.fingerprint


def test_run_contract_binds_checkpoint_and_final_publication_profiles(tmp_path: Path) -> None:
    # Given: a current scientific source and implementation closure.
    repository = _repository(tmp_path)
    manifest = _manifest(repository, duplicate=False)

    # When: the immutable run contract is constructed.
    contract = build_characterization_run_contract(manifest, repository, shard_count=1, module_roots=("fixture.runner",))

    # Then: checkpoint and final publication profiles are immutable fingerprinted policy inputs.
    policies = _mapping(contract.payload["policies"])
    assert policies["checkpoint_publication"] == "otmpfile_procfd_linkat_v1"
    assert policies["final_publication_profile"] == "regular_bundle_linkat_trusted_state_v2"
    assert policies["state_directory"] == "repository_tmp_owner_safe_child0700_v1"


def _repository(root: Path, runner_source: str = "from . import helper\n") -> Path:
    package = root / "fixture"
    package.mkdir()
    (package / "__init__.py").write_text("from . import helper\n", encoding="utf-8")
    (package / "runner.py").write_text(runner_source, encoding="utf-8")
    for name in ("helper", "conditional", "function_only", "typing_only"):
        (package / f"{name}.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "domain.pddl").write_text(
        "(define (domain blocksworld) (:requirements :strips) (:predicates (clear ?x) (handempty)))\n",
        encoding="utf-8",
    )
    for count in (4, 8, 12):
        objects = " ".join(f"b{index}" for index in range(count))
        clear = " ".join(f"(clear b{index})" for index in range(count))
        (root / f"problem-{count}.pddl").write_text(
            f"(define (problem p{count}) (:domain blocksworld) (:objects {objects}) (:init (handempty) {clear}) (:goal (and (handempty))))\n",
            encoding="utf-8",
        )
    return root


def _product_roots(root: Path) -> None:
    phase = root / "scripts/phase3"
    phase.mkdir(parents=True)
    (root / "scripts/__init__.py").write_text("\n", encoding="utf-8")
    (phase / "__init__.py").write_text("\n", encoding="utf-8")
    for name in ("cgas_partition_characterization", "cgas_characterization_contract", "cgas_characterization_imports"):
        (phase / f"{name}.py").write_text("VALUE = 1\n", encoding="utf-8")


def _manifest(root: Path, duplicate: bool, suffix: str = "") -> Path:
    rows: list[dict[str, object]] = []
    for split, object_count, count in (("train", 4, 190), ("train", 8, 198), ("train", 12, 14), ("dev", 12, 39), ("test", 12, 40)):
        for _ in range(count):
            ordinal = len(rows)
            instance_id = f"blocksworld-{split}-bucket-{ordinal:04d}"
            rows.append(_row(instance_id, split, "bucket", ordinal, object_count, root))
    if duplicate:
        rows[1] = _row(str(rows[0]["instance_id"]), "train", "bucket", 0, 4, root)
    path = root / f"accepted{len(suffix)}.jsonl"
    path.write_text("".join(json.dumps(row, sort_keys=True) + suffix + "\n" for row in rows), encoding="utf-8")
    return path


def _row(instance_id: str, split: str, bucket: str, index: int, object_count: int, root: Path) -> dict[str, object]:
    return {
        "instance_id": instance_id,
        "candidate_id": f"blocksworld-{split}-{bucket}-attempt-{index:06d}",
        "domain_id": "blocksworld",
        "split": split,
        "bucket": bucket,
        "index": index,
        "attempt_index": index,
        "domain_path": str(root / "domain.pddl"),
        "problem_path": str(root / f"problem-{object_count}.pddl"),
    }


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value
