"""Choice-frontier teacher corpus and frozen membership (#132).

Replays the frozen paired-phase v3 exact traces through the choice-sensitive
contract (``choice_frontier.py``) on CPU, verifies every expansion against the
stored trace, and materializes one SFT record per (task, algorithm, expansion)
membership triple.

Membership freeze rule (pre-registered): the frozen matched-modalities
membership (512 training + 27 diagnostic record ids per additive algorithm)
indexes old-contract decisions; each old decision maps to the expansion whose
candidate set it submitted into (per-event decision cumsum of the stored exact
trace). Unique (task, expansion) pairs in first-occurrence order form the base
set; because several old decisions can share one expansion, the base set is
topped up to 512 by round-robin over the frozen task order (first occurrence in
the frozen training ids), each pass taking the task's next uncovered expansion.
Diagnostic records are the unique-expansion set of the frozen diagnostic ids
with no top-up. Record ids keep the frozen shape ``{task}:{algorithm}:{index}``
with ``index`` the expansion index.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .choice_frontier import (
    CHOICE_ARM,
    CHOICE_RECIPE_ID,
    ChoiceFrontierModelSession,
    ChoiceFrontierTask,
    canonical_choice,
)
from .choice_frontier_views import assert_no_text_leak, build_choice_observation, choice_payload
from .modality_view_preparation import write_json
from .native_arm_corpus import _render_states
from .pddl_state import PDDLStateAuthority
from .scene_assets import read_json
from .visual_episode import VisualTaskViews

ADDITIVE_ALGORITHMS = ("best_first_add_greedy", "best_first_add_w3")
CORPUS_SCHEMA = "choice_frontier_corpus_v1"
STORE_SCHEMA = "choice_frontier_scene_store_v1"
MEMBERSHIP_SCHEMA = "choice_frontier_membership_v1"
REPORT_SCHEMA = "choice_frontier_preparation_v1"
TRAIN_RECORDS = 512
PAIR_TRACES = "data/best_first_paired_phase_v3/exact-traces/pairs"
CORPUS_REPORT = "outputs/modality_corpus/issue74-matched-32k-v1/release-001/report.json"
V5_SCENE_VIEWS = "outputs/matched_modalities/v5/preparation/scene-views.json"
SOURCE_MEMBERSHIP = "configs/experiments/matched-modalities/membership.json"


def _load_trace(pair_dir: Path, algorithm: str) -> dict[str, Any]:
    return read_json(pair_dir / f"{algorithm}.json.gz")


def expansion_starts(trace: dict[str, Any]) -> tuple[list[int], int]:
    """Old-contract decision index at which each expansion starts, plus the total."""


    starts, cursor = [], 0
    for event in trace["events"]:
        starts.append(cursor)
        cursor += len(event["decisions"])
    return starts, cursor


def expansion_of_decision(starts: list[int], total: int, decision_index: int) -> int:
    if decision_index < 0 or decision_index >= total:
        raise ValueError("old-contract decision index is outside the trace")
    expansion = 0
    for index, start in enumerate(starts):
        if start > decision_index:
            break
        expansion = index
    return expansion

def derive_membership(root: Path, source_membership_path: str = SOURCE_MEMBERSHIP) -> dict[str, Any]:
    """Freeze the choice-contract membership from the frozen source membership."""

    source = read_json(root / source_membership_path)
    source_sha = hashlib.sha256((root / source_membership_path).read_bytes()).hexdigest()
    membership: dict[str, Any] = {
        "schema_version": MEMBERSHIP_SCHEMA,
        "contract": "choice-frontier",
        "source_membership": source_membership_path,
        "source_membership_sha256": source_sha,
        "selection_rule": (
            "map each frozen old-contract record to its expansion via the stored trace's "
            "per-event decision cumsum; unique (task, expansion) pairs in first-occurrence "
            "order form the base set; top up to 512 by round-robin over the frozen task "
            "order (first occurrence in the frozen training ids), each pass taking the "
            "task's next uncovered expansion index; diagnostics are the unique-expansion "
            "set of the frozen diagnostic ids without top-up"
        ),
        "training_record_ids": {},
        "diagnostic_record_ids": {},
        "task_order": {},
    }
    for algorithm in ADDITIVE_ALGORITHMS:
        training = list(source["training_record_ids"][algorithm])
        diagnostic = list(source["diagnostic_record_ids"][algorithm])
        traces: dict[str, tuple[list[int], int]] = {}
        task_order: list[str] = []
        for rid in training:
            task_id = rid.split(":")[0]
            if task_id not in task_order:
                task_order.append(task_id)

        def trace_of(task_id: str, _traces: dict = traces, _algorithm: str = algorithm) -> tuple[list[int], int]:
            if task_id not in _traces:
                _traces[task_id] = expansion_starts(_load_trace(root / PAIR_TRACES / task_id, _algorithm))
            return _traces[task_id]

        def expansion_of(rid: str) -> tuple[str, int]:
            task_id, _algorithm, index = rid.split(":")
            starts, total = trace_of(task_id)
            return task_id, expansion_of_decision(starts, total, int(index))

        selected: list[tuple[str, int]] = []
        seen: set[tuple[str, int]] = set()
        for rid in training:
            pair = expansion_of(rid)
            if pair not in seen:
                seen.add(pair)
                selected.append(pair)
        if len(selected) < TRAIN_RECORDS:
            uncovered = {
                task_id: [e for e in range(len(traces[task_id][0])) if (task_id, e) not in seen]
                for task_id in task_order
            }
            while len(selected) < TRAIN_RECORDS:
                progressed = False
                for task_id in task_order:
                    if len(selected) >= TRAIN_RECORDS:
                        break
                    if uncovered[task_id]:
                        pair = (task_id, uncovered[task_id].pop(0))
                        seen.add(pair)
                        selected.append(pair)
                        progressed = True
                if not progressed:
                    raise ValueError(f"choice-frontier membership cannot reach {TRAIN_RECORDS} records")
        elif len(selected) > TRAIN_RECORDS:
            selected = selected[:TRAIN_RECORDS]
        diagnostic_selected: list[tuple[str, int]] = []
        diagnostic_seen: set[tuple[str, int]] = set()
        for rid in diagnostic:
            pair = expansion_of(rid)
            if pair not in diagnostic_seen:
                diagnostic_seen.add(pair)
                diagnostic_selected.append(pair)
        membership["training_record_ids"][algorithm] = [
            f"{task_id}:{algorithm}:{expansion}" for task_id, expansion in selected
        ]
        membership["diagnostic_record_ids"][algorithm] = [
            f"{task_id}:{algorithm}:{expansion}" for task_id, expansion in diagnostic_selected
        ]
        membership["task_order"][algorithm] = task_order
    return membership


def _catalog_key_map(catalog: dict[str, Any]) -> dict[str, int]:
    key = VisualTaskViews.key
    mapping: dict[str, int] = {}
    for entry in catalog["states"]:
        mapping.setdefault(key(entry["atoms"], entry["fluents"]), int(entry["index"]))
    return mapping


def derive_task_episode(
    root: Path,
    task_id: str,
    algorithm: str,
    *,
    page_counts: tuple[int, int],
    corpus_row: dict[str, Any],
) -> dict[str, Any]:
    """Replay the exact reference under the choice contract; gate against the trace.

    Returns per-decision menu bindings (refs + catalog indices), the teacher
    choice per decision and token counts, plus the verification summary.
    """

    pair_dir = root / PAIR_TRACES / task_id
    source = read_json(pair_dir / "task.json")
    trace = _load_trace(pair_dir, algorithm)
    if trace["algorithm"] != algorithm:
        raise ValueError("choice-frontier trace algorithm differs")
    result = trace["result"]
    manifest = read_json(root / corpus_row["view_manifest"])
    catalog = read_json(root / manifest["scene_catalog"])
    indices = _catalog_key_map(catalog)
    key = VisualTaskViews.key


    authority = PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"])
    task = ChoiceFrontierTask(
        instance_id=source["instance_id"],
        pair_id=task_id,
        domain=source["domain"],
        algorithm=algorithm,
        exact_expansions=int(result["expansion_count"]),
    )
    session = ChoiceFrontierModelSession(authority=authority, task=task, arm="exact_reference", seed=17)
    static_count, goal_count = page_counts
    decisions: list[dict[str, Any]] = []
    while (request := session.next_request()) is not None:
        menu_states = session.menu_states(request)
        menu_indices = []
        for state in menu_states:
            state_key = key(state.atoms, state.fluents)
            if state_key not in indices:
                raise ValueError("choice-frontier menu state is outside the scene catalog")
            menu_indices.append(indices[state_key])
        payload = choice_payload(dict(request.model_input))
        placeholder = build_choice_observation(
            payload,
            ["static"] * static_count,
            ["goal"] * goal_count,
            list(request.model_input["frontier_menu"]["choices"]),
            lambda state_index: f"scenes/state-{state_index:06d}.png",
            menu_indices,
        )
        assert_no_text_leak(placeholder)
        teacher = session.reference_output()
        teacher_label = json.loads(teacher)["expand_choice"]
        session.submit_output(teacher)
        event = session.events[-1]
        decisions.append(
            {
                "decision_index": request.decision_index,
                "menu": [dict(entry) for entry in request.menu_binding],
                "menu_indices": menu_indices,
                "teacher_choice": teacher_label,
                "input_tokens": placeholder["binding"]["input_tokens"],
                "input_pages": placeholder["binding"]["input_pages"],
                "menu_size": len(menu_indices),
                "expanded_state_id": event["trusted_runtime_result"].get("expanded_state_id"),
                "status": event["trusted_runtime_result"]["status"],
            }
        )

    # Gate: expansion-for-expansion equality against the stored exact trace.
    expansion_events = [d for d in decisions if d["status"] == "expanded"]
    goal_selections = [d for d in decisions if d["status"] == "goal_reached"]
    if len(expansion_events) != len(trace["events"]):
        raise ValueError("choice-frontier exact episode expansion count differs from the trace")
    admissions_by_decision = {
        event["decision_index"]: event["trusted_runtime_result"]["admissions"]
        for event in session.events
        if event["trusted_runtime_result"]["status"] == "expanded"
    }
    for decision, trace_event in zip(expansion_events, trace["events"], strict=True):
        targets = [json.loads(entry["target"]) for entry in trace_event["decisions"]]
        sources = {entry["source_state_id"] for entry in targets}
        if len(sources) != 1:
            raise ValueError("stored trace expansion mixes source states")
        if decision["expanded_state_id"] != sources.pop():
            raise ValueError("choice-frontier exact expansion order differs from the trace")
        admissions = admissions_by_decision[decision["decision_index"]]
        if len(admissions) != len(trace_event["decisions"]):
            raise ValueError("choice-frontier expansion candidate count differs from the trace")
        for admission, trace_decision, target in zip(admissions, trace_event["decisions"], targets, strict=True):
            if admission["action"] != target["action"]:
                raise ValueError("choice-frontier candidate order differs from the trace")
            for field, value in trace_decision["runtime"].items():
                if admission["trusted_runtime_result"].get(field) != value:
                    raise ValueError("choice-frontier trusted runtime result differs from the trace")
    summary = session.result()
    if summary["expansion_count"] != int(result["expansion_count"]):
        raise ValueError("choice-frontier exact expansion total differs from the trace")
    if session.controller.reopen_count != int(result["reopen_count"]):
        raise ValueError("choice-frontier exact reopen count differs from the trace")
    if len(goal_selections) != (0 if summary["goal_reached"] is False else 1):
        raise ValueError("choice-frontier exact goal selection bookkeeping differs")
    return {
        "task_id": task_id,
        "algorithm": algorithm,
        "domain": source["domain"],
        "instance_id": source["instance_id"],
        "decisions": decisions,
        "result": summary,
        "trace": {
            "decision_count": int(result["decision_count"]),
            "expansion_count": int(result["expansion_count"]),
            "reopen_count": int(result["reopen_count"]),
            "solution_cost": int(result["solution_cost"]),
        },
    }


def _page_counts(root: Path, v5: dict[str, Any], task_id: str, manifest: dict[str, Any]) -> tuple[int, int]:
    if task_id in v5["tasks"]:
        task = v5["tasks"][task_id]
        return len(task["static_pages"]), len(task["goal_pages"])
    reusable = manifest["reusable_pages"]
    return len(reusable["task-context"]), len(reusable["goal"])


def prepare_store(
    root: Path,
    membership: dict[str, Any],
    output_dir: Path,
    progress=lambda *args, **kwargs: None,
) -> dict[str, Any]:
    """Materialize the frozen choice-frontier membership under the choice contract."""

    if membership.get("schema_version") != MEMBERSHIP_SCHEMA:
        raise ValueError("choice-frontier membership schema differs")
    v5 = read_json(root / V5_SCENE_VIEWS)
    representation = v5.get("study", {}).get("state_representation")
    recipe_id = representation.get("id") if isinstance(representation, dict) else representation
    if v5.get("outcome") != "PASS" or recipe_id != "scene-only-128-unlabelled-v1":
        raise ValueError("choice-frontier corpus builds on the verified v5 scene-only preparation")
    corpus_rows = {row["task_id"]: row for row in read_json(root / CORPUS_REPORT)["results"]}
    algorithms = list(ADDITIVE_ALGORITHMS)
    task_order: list[str] = []
    for algorithm in algorithms:
        for task_id in membership["task_order"][algorithm]:
            if task_id not in task_order:
                task_order.append(task_id)
        for record_id in membership["diagnostic_record_ids"][algorithm]:
            task_id = record_id.split(":")[0]
            if task_id not in task_order:
                task_order.append(task_id)
    store: dict[str, Any] = {
        "schema_version": STORE_SCHEMA,
        "arm": CHOICE_ARM,
        "recipe_id": CHOICE_RECIPE_ID,
        "study": {
            "corpus_report": CORPUS_REPORT,
            "v5_scene_views": V5_SCENE_VIEWS,
            "source_membership": membership["source_membership"],
            "state_representation": CHOICE_RECIPE_ID,
        },
        "tasks": {},
        "records": {},
        "counts": {},
    }
    needed_scenes: dict[str, set[int]] = {task_id: {0} for task_id in task_order}
    derived: dict[tuple[str, str], dict[str, Any]] = {}
    for position, task_id in enumerate(task_order):
        manifest = read_json(root / corpus_rows[task_id]["view_manifest"])
        counts = _page_counts(root, v5, task_id, manifest)
        for algorithm in algorithms:
            episode = derive_task_episode(
                root, task_id, algorithm, page_counts=counts, corpus_row=corpus_rows[task_id]
            )
            derived[(task_id, algorithm)] = episode
            for decision in episode["decisions"]:
                needed_scenes[task_id].update(decision["menu_indices"])
        progress("choice_prep:episode", completed=position + 1, total=len(task_order), task=task_id)

    for task_id in task_order:
        manifest = read_json(root / corpus_rows[task_id]["view_manifest"])
        catalog = read_json(root / manifest["scene_catalog"])
        if task_id in v5["tasks"]:
            v5_task = v5["tasks"][task_id]
            scenes = dict(v5_task["scenes"])
            static_pages = list(v5_task["static_pages"])
            goal_pages = list(v5_task["goal_pages"])
            scene_bindings = dict(v5_task["scene_bindings"])
        else:
            scenes, static_pages, goal_pages, scene_bindings = {}, [], [], {}
            reusable = manifest["reusable_pages"]
            static_pages = list(reusable["task-context"])
            goal_pages = list(reusable["goal"])
        wanted = needed_scenes[task_id]
        missing = wanted - {int(index) for index in scenes}
        if missing:
            rendered = _render_states(root, catalog, manifest, missing, output_dir / "scenes" / task_id)
            scenes.update(rendered)
        unresolved = [index for index in wanted if not (root / scenes[str(index)]).is_file()]
        if unresolved:
            raise ValueError(f"choice-frontier scene references do not resolve: {unresolved[:3]}")
        store["tasks"][task_id] = {
            "source_manifest": corpus_rows[task_id]["view_manifest"],
            "static_pages": static_pages,
            "goal_pages": goal_pages,
            "scenes": scenes,
            "scene_bindings": scene_bindings,
            "view_id": f"choice-frontier/{task_id}",
        }

    for algorithm in algorithms:
        ids = list(membership["training_record_ids"][algorithm]) + list(
            membership["diagnostic_record_ids"][algorithm]
        )
        for record_id in ids:
            task_id, _algorithm, expansion = record_id.split(":")
            episode = derived[(task_id, algorithm)]
            decision = episode["decisions"][int(expansion)]
            if decision["status"] != "expanded":
                raise ValueError("choice-frontier membership selects a non-expansion decision")
            task = store["tasks"][task_id]
            payload = choice_payload(
                {
                    "algorithm": algorithm,
                    "frontier_menu": {"choices": [entry["choice"] for entry in decision["menu"]]},
                    "representation": "visual-choice-frontier",
                    "schema_version": "choice_frontier_model_input_v1",
                }
            )
            example = build_choice_observation(
                payload,
                task["static_pages"],
                task["goal_pages"],
                [entry["choice"] for entry in decision["menu"]],
                lambda state_index, task=task: task["scenes"][str(state_index)],
                decision["menu_indices"],
            )
            assert_no_text_leak(example)
            if example["binding"]["input_tokens"] != decision["input_tokens"]:
                raise ValueError("choice-frontier store token count differs from derivation")
            store["records"][record_id] = {
                "record_id": record_id,
                "task_id": task_id,
                "domain": episode["domain"],
                "algorithm": algorithm,
                "split": "train" if record_id in set(membership["training_record_ids"][algorithm]) else "diagnostic",
                "expansion_index": int(expansion),
                "menu": decision["menu"],
                "menu_indices": decision["menu_indices"],
                "teacher_choice": decision["teacher_choice"],
                "expanded_state_id": decision["expanded_state_id"],
                "input_tokens": decision["input_tokens"],
                "input_pages": example["binding"]["input_pages"],
                "menu_size": decision["menu_size"],
                "reference_expansions": episode["trace"]["expansion_count"],
            }
    store["counts"] = {
        "records": len(store["records"]),
        "tasks": len(store["tasks"]),
        "scenes": sum(len(task["scenes"]) for task in store["tasks"].values()),
        "episodes_verified": len(derived),
    }
    write_json(output_dir / "store.json", store)
    report = {
        "schema_version": REPORT_SCHEMA,
        "arm": CHOICE_ARM,
        "membership_counts": {
            algorithm: {
                "training": len(membership["training_record_ids"][algorithm]),
                "diagnostic": len(membership["diagnostic_record_ids"][algorithm]),
            }
            for algorithm in algorithms
        },
        "counts": store["counts"],
        "token_range": {
            "min": min(record["input_tokens"] for record in store["records"].values()),
            "max": max(record["input_tokens"] for record in store["records"].values()),
        },
        "menu_size_range": {
            "min": min(record["menu_size"] for record in store["records"].values()),
            "max": max(record["menu_size"] for record in store["records"].values()),
        },
        "expansion_gate": "every derived episode matched its stored exact trace expansion for expansion",
    }
    write_json(output_dir / "report.json", report)
    return store


class ChoiceFrontierStore:
    """Load a materialized choice-frontier store and build training examples."""

    def __init__(self, root: Path, store_path: Path):
        self.root = root
        report = read_json(store_path)
        if report.get("schema_version") != STORE_SCHEMA or report.get("arm") != CHOICE_ARM:
            raise ValueError("choice-frontier store schema/arm differs")
        self.recipe_id = report["recipe_id"]
        self.tasks = report["tasks"]
        self.records = report["records"]
        self.study = report["study"]
        self.counts = report["counts"]

    def training_example(self, record_id: str) -> dict[str, Any]:
        record = self.records[record_id]
        task = self.tasks[record["task_id"]]
        choices = [entry["choice"] for entry in record["menu"]]
        payload = choice_payload(
            {
                "algorithm": record["algorithm"],
                "frontier_menu": {"choices": choices},
                "representation": "visual-choice-frontier",
                "schema_version": "choice_frontier_model_input_v1",
            }
        )

        def loader(label: str, path: str):
            from PIL import Image

            with Image.open(self.root / path) as stored:
                return stored.convert("RGB")

        example = build_choice_observation(
            payload,
            task["static_pages"],
            task["goal_pages"],
            choices,
            lambda state_index: task["scenes"][str(state_index)],
            record["menu_indices"],
            loader,
        )
        assert_no_text_leak(example)
        if example["binding"]["input_pages"] != record["input_pages"]:
            raise ValueError("choice-frontier page roles differ from the frozen preparation")
        if example["binding"]["input_tokens"] != record["input_tokens"]:
            raise ValueError("choice-frontier input tokens differ from the frozen preparation")
        teacher = next(
            entry["choice"]
            for entry in record["menu"]
            if entry["state_ref"] == record["expanded_state_id"]
        )
        if teacher != record["teacher_choice"]:
            raise ValueError("choice-frontier teacher label differs from the frozen preparation")
        example["messages"].append({"role": "assistant", "content": canonical_choice(teacher)})
        return example


class ChoiceFrontierTrainingDataset:
    """Membership-ordered torch dataset over the choice-frontier store."""

    def __init__(self, root: Path, store: ChoiceFrontierStore, membership: dict[str, Any], algorithm: str, split: str):
        key = "training_record_ids" if split == "train" else "diagnostic_record_ids"
        self.record_ids = list(membership[key][algorithm])
        self.store = store
        # Interface parity with NativeArmTrainingDataset: train_visual reads
        # ``dataset.records`` for the membership-ordered training record ids.
        self.records = [store.records[record_id] for record_id in self.record_ids]
        for record_id in self.record_ids:
            if record_id not in store.records:
                raise ValueError("choice-frontier dataset record lacks a frozen binding")

    def __len__(self):
        return len(self.record_ids)

    def __getitem__(self, index):
        return self.store.training_example(self.record_ids[index])


__all__ = [
    "ADDITIVE_ALGORITHMS",
    "CORPUS_REPORT",
    "CORPUS_SCHEMA",
    "MEMBERSHIP_SCHEMA",
    "PAIR_TRACES",
    "REPORT_SCHEMA",
    "SOURCE_MEMBERSHIP",
    "STORE_SCHEMA",
    "TRAIN_RECORDS",
    "V5_SCENE_VIEWS",
    "ChoiceFrontierStore",
    "ChoiceFrontierTrainingDataset",
    "derive_membership",
    "derive_task_episode",
    "expansion_of_decision",
    "expansion_starts",
    "prepare_store",
]
