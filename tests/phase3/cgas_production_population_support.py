from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.phase3.cgas_candidate_characterization_contracts import selector_binding
from scripts.phase3.cgas_candidate_characterization_models import (
    AccountingBindingModel,
    AccountingCountsModel,
    ArtifactBindingModel,
    CheckpointModel,
    JsonObject,
    ReservoirBindingModel,
    StreamCursorModel,
)
from scripts.phase3.cgas_partition_selection import RoleRecord, Selection
from scripts.phase3.cgas_production_population import _accepted_manifest
from scripts.phase3.cgas_production_population_contracts import PopulationInput

ROOT = Path(__file__).resolve().parents[2]
CURRENT_CHECKPOINT = ROOT / "tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json"


def rows_fixture() -> tuple[JsonObject, ...]:
    rows: list[JsonObject] = []
    for index in range(53):
        structural = index < 20
        instance_id = f"row-{index:03}"
        planner: JsonObject = {
            "exact_search": {
                "expansion_count": 100 if structural else 1,
                "plan_length": 10 if structural else 1,
                "status": "exact_solution_replayed",
            },
            "replay": {"goal_satisfied": True, "replay_ok": True},
            "source_eligibility": "eligible_complete_trace",
        }
        rows.append(
            {
                "bfs": planner,
                "composition_signature": f"ood-{index // 2:02}" if structural else "remaining-33",
                "instance_id": instance_id,
                "iw_width_1": planner,
                "object_count": 12 if structural else 4,
                "source_identity": {"source_record_sha256": hashlib.sha256(instance_id.encode()).hexdigest()},
                "split": "candidate",
                "status": "characterized",
            }
        )
    return tuple(rows)


def population_fixture() -> PopulationInput:
    rows = rows_fixture()
    contents = _jsonl(rows)
    empty = ArtifactBindingModel(canonical_jsonl="", row_count=0, sha256=hashlib.sha256(b"").hexdigest())
    reservoir = ReservoirBindingModel(
        canonical_jsonl=contents,
        row_count=len(rows),
        sha256=hashlib.sha256(contents.encode()).hexdigest(),
        signature_count=11,
        signatures=[*(f"ood-{index:02}" for index in range(10)), "remaining-33"],
    )
    checkpoint = CheckpointModel(
        accounting=AccountingBindingModel(
            **empty.model_dump(), counts=AccountingCountsModel(duplicate=0, emitted=0, solved=0)
        ),
        approved_trace_contract_sha256="1" * 64,
        approved_trace_sha256="2" * 64,
        candidate_config_sha256="3" * 64,
        characterization=empty,
        feedback_sha256=None,
        predecessor_checkpoint_sha256=None,
        ranges=[],
        reservoir=reservoir,
        round=1,
        schema_version="cgas_candidate_characterization_checkpoint_v1",
        selector=selector_binding(),
        streams=[StreamCursorModel(object_count=count, next_raw_rank=0, exhausted=False) for count in (4, 8, 12)],
    )
    return PopulationInput(Path("synthetic/checkpoints/reservoir_checkpoint_000001.json"), checkpoint, "4" * 64, rows)


def feasible_manifest_fixture() -> tuple[tuple[JsonObject, ...], tuple[RoleRecord, ...]]:
    rows: list[JsonObject] = []
    records: list[RoleRecord] = []
    planner: JsonObject = {
        "exact_search": {"status": "exact_solution_replayed"},
        "replay": {"goal_satisfied": True, "replay_ok": True},
        "source_eligibility": "eligible_complete_trace",
    }
    groups = (
        ("train", 4, 190),
        ("train", 8, 198),
        ("train", 12, 14),
        ("calibration", 12, 39),
        ("structural_ood", 12, 40),
    )
    for selector_role, object_count, count in groups:
        split = {"calibration": "dev", "structural_ood": "test"}.get(selector_role, selector_role)
        for role_index in range(count):
            instance_id = f"{split}-{object_count:02}-{role_index:03}"
            source_digest = hashlib.sha256(instance_id.encode()).hexdigest()
            signature = f"{split}-signature-{role_index // 4:03}"
            rows.append(
                {
                    "bfs": planner,
                    "composition_signature": signature,
                    "instance_id": instance_id,
                    "iw_width_1": planner,
                    "object_count": object_count,
                    "source_identity": {"source_record_sha256": source_digest},
                    "split": "candidate",
                    "status": "characterized",
                }
            )
            records.append(RoleRecord(instance_id, source_digest, "candidate", signature, selector_role))
    return tuple(rows), tuple(records)


def feasible_population_fixture() -> tuple[PopulationInput, Selection, bytes]:
    rows, records = feasible_manifest_fixture()
    manifest = _accepted_manifest(rows, records)
    contents = _jsonl(rows)
    signatures = sorted({str(row["composition_signature"]) for row in rows})
    reservoir = ReservoirBindingModel(
        canonical_jsonl=contents,
        row_count=481,
        sha256=hashlib.sha256(contents.encode()).hexdigest(),
        signature_count=len(signatures),
        signatures=signatures,
    )
    checkpoint = population_fixture().checkpoint.model_copy(update={"reservoir": reservoir})
    population = PopulationInput(
        Path("synthetic/checkpoints/reservoir_checkpoint_000001.json"), checkpoint, "5" * 64, rows
    )
    return population, Selection(records, ()), manifest


def _jsonl(rows: tuple[JsonObject, ...]) -> str:
    return "".join(
        json.dumps(row, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        for row in rows
    )
