"""Modality phase settings and the mandatory pre-execution permission boundary.

This reads scientific settings and receipts, not artifact-integrity evidence.
Downstream entry points call ``permission`` before corpus/HTTP/model work and
must not proceed unless its returned receipt permits the requested start.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Mapping

from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    RunReceipt,
    StopOutcome,
    evaluate_execution_permission,
)

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = {"render", "corpus", "checkpoint", "budget", "matrix"}


@dataclass(frozen=True)
class ModalityPhase:
    freeze: Mapping[str, Any]
    components: Mapping[str, Any]
    authorization: Mapping[str, Any]

    @property
    def cells(self) -> tuple[tuple[str, str], ...]:
        matrix = self.components["matrix"]
        return tuple(product(matrix["algorithms"], matrix["modalities"]))

    def permission(
        self,
        *,
        stage: str,
        binding: ReceiptBinding,
        gate: GateReceipt,
        authorization: AuthorizationReceipt | None,
        predecessors: Mapping[str, Mapping[str, Any]],
        split: str,
    ) -> RunReceipt:
        """Require both the phase manifest and matching per-attempt receipts.

        Predecessor reports are complete stage-wide reports (all frozen cells),
        not a successful shard or a single checkpoint's training accuracy.
        No missing stage is inferred from a GitHub issue being closed.
        """
        phase_id = self.freeze["phase_id"]

        def stop(outcome: StopOutcome, reason: str, ancestor: str | None = None) -> RunReceipt:
            return RunReceipt(
                binding=binding,
                outcome=outcome,
                run_state="invalid-not-run" if outcome is StopOutcome.INVALID else "gated-not-run",
                start_permitted=False,
                scientific_completion=False,
                gate_receipt_id=gate.receipt_id,
                ancestor_receipt_id=ancestor,
                reason=reason,
            )

        if binding.contract_id != phase_id or split not in self.components["corpus"]["allowed_splits"]:
            return stop(StopOutcome.INVALID, "phase contract or development split mismatch")
        if stage not in self.components["matrix"]["stages"]:
            return stop(StopOutcome.INVALID, "stage outside the frozen modality phase")
        phase_outcome = StopOutcome(self.authorization["outcome"])
        if phase_outcome is not StopOutcome.PASS:
            outcome = StopOutcome.INVALID if phase_outcome is StopOutcome.INVALID else StopOutcome.ANCESTOR_STOP
            return stop(
                outcome,
                str(self.authorization["reason"]),
                str(self.authorization["receipt_id"]) if outcome is StopOutcome.ANCESTOR_STOP else None,
            )
        if stage not in self.authorization["authorized_stages"]:
            return stop(StopOutcome.INVALID, "stage missing from phase authorization")
        if "output_root" in self.freeze:
            expected_output = (ROOT / self.freeze["output_root"] / stage / binding.attempt_id).resolve()
            if Path(binding.output_root) != expected_output:
                return stop(StopOutcome.INVALID, "output does not bind the requested stage and attempt")
        permission = evaluate_execution_permission(
            binding=binding,
            gate_receipt=gate,
            authorization_receipt=authorization,
            ancestor_receipt_id=gate.ancestor_receipt_id,
        )
        if not permission.start_permitted:
            return permission
        for required in self.components["matrix"]["stages"][stage]["requires"]:
            report = predecessors.get(required)
            if report is None:
                return stop(StopOutcome.VALID_STOP, f"missing completed predecessor: {required}")
            if report.get("phase_id") != phase_id or report.get("stage") != required:
                return stop(StopOutcome.INVALID, f"predecessor scope mismatch: {required}")
            if report.get("outcome") == "INVALID":
                return stop(StopOutcome.INVALID, f"invalid predecessor: {required}")
            if report.get("outcome") not in {item.value for item in StopOutcome}:
                return stop(StopOutcome.INVALID, f"malformed predecessor outcome: {required}")
            if report.get("outcome") != "PASS":
                receipt_id = report.get("receipt_id")
                if not isinstance(receipt_id, str) or not receipt_id:
                    return stop(StopOutcome.INVALID, f"missing predecessor receipt identity: {required}")
                return stop(StopOutcome.ANCESTOR_STOP, f"predecessor stopped: {required}", receipt_id)
            if report.get("scientific_completion") is not True or report.get("complete_selected_coverage") is not True:
                return stop(StopOutcome.VALID_STOP, f"incomplete predecessor: {required}")
            checks = self.components["matrix"]["stages"][required].get("required_checks", [])
            if any(report.get("checks", {}).get(name) is not True for name in checks):
                return stop(StopOutcome.INVALID, f"predecessor PASS lacks required scientific checks: {required}")
            if "cells" in self.components["matrix"] and required != "render_preflight":
                if report.get("covered_cells") != self.components["matrix"]["cells"]:
                    return stop(StopOutcome.INVALID, f"predecessor cell coverage mismatch: {required}")
        return permission


def load_modality_phase(
    freeze_path: Path = ROOT / "configs/experiments/issue71/v2/freeze.json",
    *,
    repo_root: Path = ROOT,
) -> ModalityPhase:
    """Load the five recorded settings and their required authorization manifest."""
    freeze = json.loads(freeze_path.read_text())
    if freeze["schema_version"] != "modality_phase_freeze_v1" or freeze["source_issue"] != 71:
        raise ValueError("not an issue71 modality freeze")
    if set(freeze["components"]) != COMPONENTS:
        raise ValueError("all five modality component manifests are required")
    components = {name: json.loads((repo_root / path).read_text()) for name, path in freeze["components"].items()}
    for name, component in components.items():
        if component["component"] != name or component["phase_id"] != freeze["phase_id"]:
            raise ValueError(f"component phase mismatch: {name}")
    authorization = json.loads((repo_root / freeze["authorization_manifest"]).read_text())
    if (
        authorization["schema_version"] != "modality_phase_authorization_v1"
        or authorization["phase_id"] != freeze["phase_id"]
        or (repo_root / authorization["freeze_manifest"]).resolve() != freeze_path.resolve()
    ):
        raise ValueError("phase authorization does not bind this freeze")
    phase = ModalityPhase(freeze, components, authorization)
    checkpoint, budget, matrix = (components[key] for key in ("checkpoint", "budget", "matrix"))
    if (
        checkpoint["training_runs_per_cell"] != 1
        or checkpoint["training_seed"] != 17
        or checkpoint["rollout_checkpoint"] != "final"
        or checkpoint["training_seed_variance_claim"]
        or len(set(phase.cells)) != matrix["cell_count"]
        or matrix["training_run_count"] != len(phase.cells)
    ):
        raise ValueError("cell enumeration or single-training-seed policy is inconsistent")
    if (
        budget["max_input_tokens"] + budget["max_output_tokens"] > budget["context_tokens"]
        or budget["input_size_bins"][-1] != budget["max_input_tokens"]
        or budget["model_call_multiplier"] != 2
        or not 0 < budget["rollout_certification_seconds"] < budget["stop_new_calls_seconds"] < budget["gate_seconds"]
        or budget["hardware_qualification"]["inspect_model_success"]
    ):
        raise ValueError("token, call, clock or outcome-blind qualification settings are inconsistent")
    outcome = StopOutcome(authorization["outcome"])
    if outcome is StopOutcome.PASS:
        if (
            freeze["status"] != "authorized"
            or not components["render"].get("contract_frozen")
            or not components["render"]["domain_profiles"]
            or not components["corpus"].get("contract_frozen")
            or authorization["start_permitted"] is not True
        ):
            raise ValueError("PASS cannot authorize unresolved production settings")
        if matrix.get("cells") != [{"algorithm": a, "modality": m} for a, m in phase.cells]:
            raise ValueError("matrix must explicitly enumerate every matched cell")
        if set(authorization["authorized_stages"]) != set(matrix["stages"]):
            raise ValueError("authorization must bind the frozen stage graph")
    elif authorization["start_permitted"] or authorization["scientific_completion"]:
        raise ValueError("a stopped phase cannot authorize work or claim scientific completion")
    return phase


def inspect_modality_sources(phase: ModalityPhase, *, repo_root: Path = ROOT) -> dict[str, Any]:
    """Read source corpus coverage metadata only; never regenerate or compare files."""
    counts = {}
    for name, source in phase.components["corpus"]["sources"].items():
        manifest = json.loads((repo_root / source["manifest"]).read_text())
        actual = manifest["counts"]
        if actual["process_records"] != source["process_records"] or actual["split_assignments"] != source["tasks"]:
            raise ValueError(f"source corpus coverage differs from candidate settings: {name}")
        counts[name] = {"process_records": actual["process_records"], "tasks": actual["split_assignments"]}
    panel_path = phase.components["corpus"].get("panel_manifest")
    if panel_path:
        from .modality_panel import select_modality_panel

        panel = json.loads((repo_root / panel_path).read_text())
        if panel["phase_id"] != phase.freeze["phase_id"] or panel["selection_uses_model_outcomes"]:
            raise ValueError("panel phase or outcome-blind selection mismatch")
        selected = panel["selected"]
        if len({row["task_id"] for row in selected}) != len(selected):
            raise ValueError("duplicate selected task")
        summary = select_modality_panel(selected, phase.components["budget"]["max_reference_decisions"])
        if summary["excluded"]:
            raise ValueError("selected episode exceeds the frozen reference-decision ceiling")
        profiles = phase.components["render"]["domain_profiles"]
        for row in selected:
            if not (repo_root / profiles[row["domain"]]).is_file():
                raise ValueError(f"missing selected domain profile: {row['domain']}")
            if set(row["reference_costs"]) != set(row["trace_paths"]):
                raise ValueError("trace and reference cost algorithm mismatch")
            additive = {"best_first_add_w3", "best_first_add_greedy"}
            if additive.intersection(row["reference_costs"]) and not additive.issubset(row["reference_costs"]):
                raise ValueError("additive settings must remain paired")
            for path in row["trace_paths"].values():
                if not (repo_root / path).is_file():
                    raise ValueError(f"missing selected source trace: {path}")
        expected = dict(panel["counts"])
        expected["excluded_task_groups"] = 0
        if summary["counts"] != expected or panel["counts"] != phase.components["corpus"]["selected_counts"]:
            raise ValueError("selected task/cost coverage mismatch")
        counts["selected_panel"] = panel["counts"]
    return counts
