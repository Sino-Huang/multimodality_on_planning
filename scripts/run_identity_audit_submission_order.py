#!/usr/bin/env python
"""Issue #134 R1: submission-order-serial identity counterfactual (CPU-only).

Frozen protocol: docs/experiments/choice-frontier/issue-134-protocol.md.

Re-runs the 48 additive enumeration-contract pairs of
``outputs/native-arms/v1/identity-audit.json`` under the executed serial rule
(serials from the deterministic sorted candidate order at ``start_expansion``)
and under a ``BestFirstController`` variant that assigns heap serials in
submission order at ``apply_operation`` time. The executed-rule re-runs must
reproduce every stored baseline control episode exactly; any mismatch aborts
the run before the artifact is written.
"""

from __future__ import annotations

import gzip
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.best_first_controller import (  # noqa: E402
    BEST_FIRST_SETTINGS,
    BestFirstController,
    BestFirstOperation,
)
from examples.planning_benchmark_slice.best_first_development import (  # noqa: E402
    BestFirstDevelopmentTask,
    BestFirstModelSession,
    exact_best_first_output,
    random_valid_best_first_output,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority  # noqa: E402

BASELINE_STORE = Path("outputs/expanded-study/v1/baseline/episodes")
PANEL_PATH = Path("configs/experiments/expanded-study/final-panel.json")
BASELINE_PROTOCOL_PATH = Path("configs/experiments/expanded-study/baseline-protocol.json")
OUTPUT_PATH = ROOT / "outputs/native-arms/v1/identity-audit-submission-order.json"
MODALITIES = ("text-state", "visual-state", "multimodal-state")
CONDITIONS = ("random_valid", "exact_reference")
RULES = ("sorted_candidate_order", "submission_order")


class SubmissionOrderSerialController(BestFirstController):
    """BestFirstController variant: heap serials follow candidate submission order.

    Identical to the executed controller except that each target state's heap
    serial is assigned at ``apply_operation`` time — the first submission of a
    target within an expansion takes the next serial — instead of at
    ``start_expansion`` from the deterministic sorted candidate order. Candidate
    generation, priorities, duplicate/reopen handling, budgets and state-ref
    assignment are inherited unchanged.
    """

    def start_expansion(self):
        serial_start = self._next_serial
        state = super().start_expansion()
        self._serial_by_target = {}
        self._next_serial = serial_start
        return state

    def apply_operation(self, operation: BestFirstOperation, *, raw_output: str | None = None):
        candidate = next(
            (item for item in self._active_candidates if item.action == operation.action),
            None,
        )
        if candidate is not None and candidate.target_state.state_id not in self._serial_by_target:
            self._serial_by_target[candidate.target_state.state_id] = self._next_serial
            self._next_serial += 1
        return super().apply_operation(operation, raw_output=raw_output)


class SubmissionOrderSession(BestFirstModelSession):
    """BestFirstModelSession driving the submission-order serial variant."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.controller = SubmissionOrderSerialController(
            self.authority,
            BEST_FIRST_SETTINGS[self.task.algorithm],
            accepted_delta_limit=self.accepted_delta_limit,
            retain_decision_evidence=False,
        )


def read_json(path: Path):
    with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as stream:
        return json.load(stream)


def enumerate_pairs() -> dict[tuple[str, str], dict[str, dict[str, Path]]]:
    """The exact pair enumeration of scripts/run_expanded_native_arms.py identity_audit_stage."""

    pairs: dict[tuple[str, str], dict[str, dict[str, Path]]] = {}
    for modality in MODALITIES:
        for algdir in sorted(p for p in (ROOT / BASELINE_STORE).glob(f"{modality}/*") if p.is_dir()):
            for path in algdir.glob("*.json.gz"):
                algorithm, _, condition = path.name.removesuffix(".json.gz").rpartition("-")
                if not algorithm.startswith("best_first_add"):
                    continue
                entry = pairs.setdefault((algdir.name, algorithm), {})
                entry.setdefault(condition, {})[modality] = path
    return {
        key: entry
        for key, entry in sorted(pairs.items())
        if all(condition in entry for condition in CONDITIONS)
    }


def run_episode(authority, task, condition: str, rule: str, seed: int) -> dict:
    session_cls = BestFirstModelSession if rule == "sorted_candidate_order" else SubmissionOrderSession
    session = session_cls(authority=authority, task=task, arm=condition, seed=seed)
    generator = random.Random(seed)
    expansion_sources: list[str] = []
    while (request := session.next_request()) is not None:
        output = (
            exact_best_first_output(request.model_input)
            if condition == "exact_reference"
            else random_valid_best_first_output(request.model_input, generator)
        )
        source = session.controller.active_state_id
        if source is None:
            raise ValueError("audit session lost its active expansion source")
        expansion_sources.append(source)
        session.submit_output(output)
    return {
        "expansion_sources": expansion_sources,
        "raw_outputs": [event["raw_output"] for event in session.events],
        "result": session.result(),
    }


def first_divergence_index(random_run: dict, exact_run: dict) -> int | None:
    random_sources = random_run["expansion_sources"]
    exact_sources = exact_run["expansion_sources"]
    for index, (left, right) in enumerate(zip(random_sources, exact_sources, strict=False)):
        if left != right:
            return index
    if len(random_sources) != len(exact_sources):
        return min(len(random_sources), len(exact_sources))
    return None


def result_summary(run: dict) -> dict:
    result = run["result"]
    return {
        "decision_count": result["decision_count"],
        "expansion_count": result["expansion_count"],
        "goal_reached": result["goal_reached"],
        "invariant_valid_success": result["invariant_valid_success"],
        "termination_reason": result["termination_reason"],
    }


def main() -> None:
    baseline_protocol = read_json(ROOT / BASELINE_PROTOCOL_PATH)
    seed = int(baseline_protocol["evaluation_seed"])
    panel = read_json(ROOT / PANEL_PATH)
    rows_by_directory = {row["row"]["task_id"].replace("/", "__"): row["row"] for row in panel["tasks"]}

    pairs = enumerate_pairs()
    if len(pairs) != 48:
        raise ValueError(f"expected the 48 audited additive pairs, found {len(pairs)}")

    stored_counts_checked = 0
    stored_raw_checked = 0
    pair_reports = []
    rule_summaries = {rule: {"pairs_identical": 0, "pairs_divergent": 0} for rule in RULES}
    exact_invariance = {"pairs_checked": 0, "pairs_identical": 0}

    for (directory, algorithm), conditions in pairs.items():
        row = rows_by_directory.get(directory)
        if row is None:
            raise ValueError(f"baseline store directory missing from the frozen panel: {directory}")
        if row.get("semantic_object_order"):
            raise ValueError(f"semantic reordering is out of scope for this audit: {row['task_id']}")
        source = read_json(ROOT / row["task_path"])
        authority = PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"])
        cost = row["reference_costs"][algorithm]
        task = BestFirstDevelopmentTask(
            row["task_id"],
            row["task_id"],
            row["domain"],
            row["difficulty"],
            ROOT / row["task_path"],
            cost["decisions"],
            cost["expansions"],
            algorithm,
            75,
        )

        runs = {
            rule: {condition: run_episode(authority, task, condition, rule, seed) for condition in CONDITIONS}
            for rule in RULES
        }

        # Validation gate 1: executed-rule re-runs reproduce every stored episode.
        for condition in CONDITIONS:
            executed = runs["sorted_candidate_order"][condition]
            for modality, path in sorted(conditions[condition].items()):
                stored = read_json(path)
                stored_result = stored["result"]
                mismatches = {
                    key: (stored_result.get(key), executed["result"].get(key))
                    for key in (
                        "decision_count",
                        "expansion_count",
                        "goal_reached",
                        "termination_reason",
                        "invalid_operation_count",
                    )
                    if stored_result.get(key) != executed["result"].get(key)
                }
                if stored.get("seed") != seed or stored.get("algorithm") != algorithm:
                    raise ValueError(f"stored episode identity drifted: {path}")
                if mismatches:
                    raise ValueError(f"executed-rule reproduction failed for {path}: {mismatches}")
                stored_counts_checked += 1
                if modality == "text-state":
                    if [event["raw_output"] for event in stored["events"]] != executed["raw_outputs"]:
                        raise ValueError(f"executed-rule raw outputs differ from the stored episode: {path}")
                    stored_raw_checked += 1

        # Validation gate 2: exact_reference is provably rule-invariant (candidate-order
        # submission), so its trajectory must be identical under both serial rules.
        exact_invariance["pairs_checked"] += 1
        if (
            runs["sorted_candidate_order"]["exact_reference"]["expansion_sources"]
            == runs["submission_order"]["exact_reference"]["expansion_sources"]
            and result_summary(runs["sorted_candidate_order"]["exact_reference"])
            == result_summary(runs["submission_order"]["exact_reference"])
        ):
            exact_invariance["pairs_identical"] += 1
        else:
            raise ValueError(f"exact_reference trajectory differs across serial rules: {row['task_id']} {algorithm}")

        pair_report = {"task_id": row["task_id"], "algorithm": algorithm, "rules": {}}
        for rule in RULES:
            divergence = first_divergence_index(runs[rule]["random_valid"], runs[rule]["exact_reference"])
            identical = divergence is None
            rule_summaries[rule]["pairs_identical" if identical else "pairs_divergent"] += 1
            pair_report["rules"][rule] = {
                "verdict": "identical" if identical else "divergent",
                "first_divergence_decision_index": divergence,
                "conditions": {
                    condition: result_summary(runs[rule][condition]) for condition in CONDITIONS
                },
            }
        pair_reports.append(pair_report)
        print(
            f"[{len(pair_reports)}/{len(pairs)}] {row['task_id']} {algorithm} "
            + " ".join(
                f"{rule}={pair_report['rules'][rule]['verdict']}@{pair_report['rules'][rule]['first_divergence_decision_index']}"
                for rule in RULES
            ),
            flush=True,
        )

    if exact_invariance["pairs_identical"] != exact_invariance["pairs_checked"]:
        raise ValueError("exact_reference rule-invariance check failed")

    executed_summary = rule_summaries["sorted_candidate_order"]
    variant_summary = rule_summaries["submission_order"]
    prediction = {
        "source": "manuscript App B (review 18, finding 49)",
        "executed_rule_stays_identical": executed_summary["pairs_identical"] == len(pairs),
        "variant_diverges_in_most_pairs": variant_summary["pairs_divergent"] > len(pairs) // 2,
    }
    prediction["held"] = (
        prediction["executed_rule_stays_identical"] and prediction["variant_diverges_in_most_pairs"]
    )

    audit = {
        "schema_version": "native_arms_identity_audit_submission_order_v1",
        "issue": 134,
        "protocol": "docs/experiments/choice-frontier/issue-134-protocol.md",
        "generated_by": "scripts/run_identity_audit_submission_order.py",
        "base_audit": "outputs/native-arms/v1/identity-audit.json",
        "store": str(BASELINE_STORE),
        "panel": str(PANEL_PATH),
        "evaluation_seed": seed,
        "serial_rules": {
            "sorted_candidate_order": (
                "executed rule: heap serials assigned at start_expansion from the deterministic "
                "sorted candidate order (unmodified BestFirstController)"
            ),
            "submission_order": (
                "counterfactual variant: each target's heap serial assigned at apply_operation "
                "time, in candidate submission order; everything else unchanged"
            ),
        },
        "policies": {
            "exact_reference": "submit candidate row 0 (frozen control policy)",
            "random_valid": "uniform random candidate row, random.Random(17) per episode (frozen control policy)",
        },
        "validation": {
            "stored_episode_counts_checked": stored_counts_checked,
            "stored_raw_output_sequences_checked": stored_raw_checked,
            "mismatches": [],
            "exact_reference_rule_invariance": exact_invariance,
        },
        "pairs_checked": len(pairs),
        "rules": {
            rule: {"pairs_checked": len(pairs), **rule_summaries[rule]} for rule in RULES
        },
        "divergence_definition": (
            "a pair diverges at the first decision index whose active expansion source (canonical "
            "state id) differs between random_valid and exact_reference; an episode-length "
            "difference counts as divergence at the shorter length"
        ),
        "preregistered_prediction": prediction,
        "verdict": (
            "SERIAL_RULE_SENSITIVE: the 48/48 identity is a property of the executed serial rule; "
            "assigning heap serials in submission order breaks it in "
            f"{variant_summary['pairs_divergent']}/{len(pairs)} pairs"
            if prediction["held"]
            else "PREDICTION_FAILED: see preregistered_prediction"
        ),
        "pairs": pair_reports,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_name(OUTPUT_PATH.name + ".partial")
    temporary.write_text(json.dumps(audit, indent=1, sort_keys=False))
    temporary.replace(OUTPUT_PATH)
    print(json.dumps({k: audit[k] for k in ("pairs_checked", "rules", "preregistered_prediction", "verdict")}, indent=1))


if __name__ == "__main__":
    main()
