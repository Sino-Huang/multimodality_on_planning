"""Materialize the authorized, semantically audited best-first text corpus."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from examples.planning_benchmark_slice.best_first_corpus import (  # noqa: E402
    BestFirstCorpusContract,
    BestFirstCorpusLimitError,
    load_best_first_corpus_contract,
    load_best_first_corpus_token_counter,
    run_best_first_corpus_release,
)

_DESIGN = _REPO_ROOT / "configs/experiments/best-first-paired-corpus-design-v3.json"
_AUTHORIZATION = _REPO_ROOT / "configs/experiments/best-first-paired-corpus-authorization-v3.json"
_RECEIPT = (
    _REPO_ROOT
    / "data/best_first_paired_phase_v3/corpus-receipts"
    / "corpus-issue-64-best-first-paired-corpus-v3-attempt-001.json"
)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture-dry-run", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--materialize", action="store_true")
    args = parser.parse_args(arguments)

    contract = load_best_first_corpus_contract(
        _DESIGN,
        _AUTHORIZATION,
        repo_root=_REPO_ROOT,
    )
    counts = contract.design["expected_counts"]
    output_root = (_REPO_ROOT / str(contract.authorization["output_root"])).resolve()
    if args.fixture_dry_run:
        return _fixture_dry_run(contract)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "authorized_stage": "corpus_release",
                    "contract_id": contract.phase_id,
                    "curriculum_controls": contract.design["curriculum_controls"],
                    "excluded_pair_count": counts["excluded_pairs"],
                    "fresh_test_access_authorized": False,
                    "max_reference_decisions_per_trace": contract.design["feasibility"][
                        "max_reference_decisions_per_trace"
                    ],
                    "operational_records": counts["operational_records"],
                    "output_root": str(output_root),
                    "pair_count": counts["pairs"],
                    "process_records": counts["process_records"],
                    "source_generation_receipt": contract.source_phase.authorization["generation_receipt_id"],
                    "trace_count": counts["traces"],
                    "views": contract.design["views"],
                    "writes": 0,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 0
    tokenizer = contract.design["tokenizer"]
    token_counter = load_best_first_corpus_token_counter(
        model_id=str(tokenizer["model_id"]),
        revision=str(tokenizer["revision"]),
    )
    try:
        manifest = run_best_first_corpus_release(
            contract=contract,
            output_root=output_root,
            token_counter=token_counter,
            progress=_progress,
        )
    except (BestFirstCorpusLimitError, MemoryError) as error:
        receipt = _receipt(
            contract,
            "VALID_STOP",
            str(error) or type(error).__name__,
            None,
        )
        _write_new(_RECEIPT, _canonical_bytes(receipt))
        print(json.dumps(receipt, sort_keys=True), flush=True)
        return 0
    except ValueError as error:
        receipt = _receipt(contract, "INVALID", str(error), None)
        _write_new(_RECEIPT, _canonical_bytes(receipt))
        print(json.dumps(receipt, sort_keys=True), flush=True)
        return 1
    receipt = _receipt(contract, "PASS", None, manifest)
    _write_new(_RECEIPT, _canonical_bytes(receipt))
    print(json.dumps(receipt, sort_keys=True), flush=True)
    return 0


class _FixtureTokenCounter:
    def input_tokens(self, model_input) -> int:
        return len(json.dumps(model_input, sort_keys=True)) // 4

    def target_tokens(self, target_text: str) -> int:
        return len(target_text) // 4


def _fixture_dry_run(contract: BestFirstCorpusContract) -> int:
    pair_id = "astar-pair-15205002a905be45f6de13ba"
    item = next(pair for pair in contract.source_manifest["pairs"] if pair["pair_id"] == pair_id)
    record_count = sum(trace["decision_count"] for trace in item["traces"].values())
    fixture = BestFirstCorpusContract(
        design={
            **contract.design,
            "expected_counts": {
                "dev_records": record_count,
                "domains": 1,
                "excluded_pairs": 0,
                "excluded_records": 0,
                "excluded_traces": 0,
                "operational_records": record_count,
                "pairs": 1,
                "process_records": record_count,
                "strata": 1,
                "traces": 2,
                "train_records": 0,
            },
        },
        authorization=contract.authorization,
        source_phase=contract.source_phase,
        source_manifest={
            **contract.source_manifest,
            "pair_count": 1,
            "trace_count": 2,
            "pairs": [item],
        },
        repo_root=contract.repo_root,
    )
    with tempfile.TemporaryDirectory(prefix="best-first-corpus-fixture-") as temporary:
        root = Path(temporary) / "release"
        manifest = run_best_first_corpus_release(
            contract=fixture,
            output_root=root,
            token_counter=_FixtureTokenCounter(),
        )
    print(
        json.dumps(
            {
                "operational_records": manifest["counts"]["operational_records"],
                "pair_count": 1,
                "process_records": manifest["counts"]["process_records"],
                "status": "fixture_contract_validated",
                "trace_count": 2,
                "writes": 0,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def _receipt(
    contract: BestFirstCorpusContract,
    outcome: str,
    reason: str | None,
    manifest: dict | None,
) -> dict:
    counts = None if manifest is None else manifest["counts"]
    return {
        "authorization_id": contract.authorization["authorization_id"],
        "contract_id": contract.phase_id,
        "counts": counts,
        "gate_receipt_id": contract.authorization["gate_receipt"]["receipt_id"],
        "outcome": outcome,
        "reason": reason,
        "receipt_id": contract.authorization["receipt_id"],
        "schema_version": "best_first_corpus_receipt_v2",
        "scientific_completion": outcome == "PASS",
        "source_generation_receipt_id": contract.source_phase.authorization["generation_receipt_id"],
        "source_issue": 64,
    }


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _write_new(path: Path, payload: bytes) -> None:
    if path.is_file():
        raise FileExistsError(f"best-first corpus receipt exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _progress(message: str) -> None:
    print(message, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
