"""Matched modality releases bound to the approved readable-page successor.

Rows retain one authoritative family input, a teacher target, and page bindings.
The model-facing projection is built by the same adapter used for live views.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
import tempfile
from collections import Counter
from dataclasses import replace
from pathlib import Path

from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    RunReceipt,
    StopOutcome,
    evaluate_execution_permission,
)

from .modality_corpus_replay import canonical, replay_inputs
from .modality_pages import ModalityViewStore, fact_blocks, project_messages
from .modality_phase import load_modality_phase
from .modality_view_panel import load_view_panel
from .modality_view_preparation import check_task, frozen_processor, process_rows, validate_process_state, write_json
from .pddl_state import PDDLStateAuthority
from .scene_assets import build_scene_catalog, load_scene_task, read_json

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = "configs/experiments/issue73/contract.json"
SCHEMA = "visual_state_corpus_record_v1"
MODALITIES = ("text-state", "visual-state", "multimodal-state")


class CorpusStop(ValueError):
    def __init__(self, outcome: StopOutcome, reason: str, ancestor: str | None = None):
        super().__init__(reason)
        self.outcome, self.ancestor = outcome, ancestor

    def __reduce__(self):
        return type(self), (self.outcome, str(self), self.ancestor)


def release_permission(root: Path, contract: dict, authorization: dict, gate_payload: dict, output: Path) -> RunReceipt:
    """Check exact successor settings and attempt receipts before processing data."""
    binding = ReceiptBinding(contract["contract_id"], output.name, output.resolve())
    gate = GateReceipt(
        ReceiptBinding(**gate_payload["binding"]),
        StopOutcome(gate_payload["outcome"]),
        gate_payload.get("ancestor_receipt_id"),
    )
    auth = AuthorizationReceipt(ReceiptBinding(**authorization["binding"]), authorization["gate_receipt_id"])
    receipt = evaluate_execution_permission(
        binding=binding, gate_receipt=gate, authorization_receipt=auth, ancestor_receipt_id=gate.ancestor_receipt_id
    )
    if not receipt.start_permitted:
        return receipt

    def stop(outcome, reason, ancestor=None):
        return replace(
            receipt,
            outcome=outcome,
            start_permitted=False,
            scientific_completion=False,
            run_state="invalid-not-run" if outcome is StopOutcome.INVALID else "gated-not-run",
            reason=reason,
            ancestor_receipt_id=ancestor,
        )

    if authorization.get("contract") != contract or (root / contract["output_root"]).resolve() != output.resolve():
        return stop(StopOutcome.INVALID, "authorization does not bind the exact successor settings/output")
    phase = load_modality_phase(root / contract["parent_freeze"], repo_root=root)
    if authorization.get("parent_gate_receipt_id") != phase.authorization["receipt_id"]:
        return stop(StopOutcome.INVALID, "parent phase gate binding differs")
    if phase.authorization["outcome"] != "PASS":
        outcome = StopOutcome.INVALID if phase.authorization["outcome"] == "INVALID" else StopOutcome.ANCESTOR_STOP
        return stop(
            outcome,
            "parent modality phase stopped",
            phase.authorization["receipt_id"] if outcome is StopOutcome.ANCESTOR_STOP else None,
        )
    view_path = root / contract["views_report"]
    if not view_path.is_file():
        return stop(StopOutcome.VALID_STOP, "missing readable-view predecessor")
    view = read_json(view_path)
    outcome = view.get("outcome")
    if outcome in ("VALID_STOP", "ANCESTOR_STOP"):
        return stop(
            StopOutcome.ANCESTOR_STOP, "readable-view predecessor stopped", f"views:{view['attempt_id']}:{outcome}"
        )
    if outcome != "PASS":
        return stop(StopOutcome.INVALID, "invalid readable-view predecessor")
    if not view.get("complete_selected_coverage") or not view.get("model_input_ready"):
        return stop(StopOutcome.VALID_STOP, "incomplete readable-view predecessor")
    try:
        panel, view_contract = load_view_panel(root, root / contract["panel_manifest"])
        ModalityViewStore(root, view_path)
        if (
            view["contract"] != view_contract
            or contract["expected"] != view_contract["expected"]
            or contract["context_tokens"] != view["approved_context"]
            or contract["output_tokens"] != view_contract["output_tokens"]
            or contract["search_memory"] != phase.components["corpus"]["search_memory"]
            or contract["source_corpora"] != phase.components["corpus"]["sources"]
            or contract["model_id"] != view_contract["model_id"]
            or contract["model_revision"] != view_contract["model_revision"]
            or contract["released_modalities"]
            != {73: ["text-state", "visual-state"], 74: list(MODALITIES)}.get(contract["source_issue"])
            or contract["qualified_modalities"] != list(MODALITIES)
            or len(panel) != contract["expected"]["tasks"]
        ):
            raise ValueError("corpus successor differs from approved views/memory/model/scope")
        if contract["source_issue"] == 74:
            source_release(root, contract)
    except CorpusStop as error:
        return stop(error.outcome, str(error), error.ancestor)
    except (ValueError, KeyError, OSError) as error:
        return stop(StopOutcome.INVALID, str(error))
    return receipt


def source_release(root: Path, contract: dict) -> dict:
    """Require the complete matching #73 predecessor before reusing its records."""
    path = root / contract["source_release"]
    if not path.is_file():
        raise CorpusStop(StopOutcome.VALID_STOP, "missing matched text/visual corpus predecessor")
    source = read_json(path)
    if source["contract"]["source_issue"] != 73 or source["contract"]["contract_id"] != contract["source_contract_id"]:
        raise ValueError("source release must be the bound #73 corpus")
    outcome = source.get("outcome")
    if outcome in ("VALID_STOP", "ANCESTOR_STOP"):
        raise CorpusStop(
            StopOutcome.ANCESTOR_STOP,
            "text/visual corpus predecessor stopped",
            f"corpus:{contract['source_contract_id']}:{path.parent.name}:{outcome}",
        )
    if outcome != "PASS":
        raise ValueError("invalid text/visual corpus predecessor")
    if not source.get("complete_selected_coverage") or not source.get("scientific_completion"):
        raise CorpusStop(StopOutcome.VALID_STOP, "incomplete text/visual corpus predecessor")
    for field in (
        "parent_freeze",
        "panel_manifest",
        "views_report",
        "expected",
        "context_tokens",
        "output_tokens",
        "model_id",
        "model_revision",
        "search_memory",
        "source_corpora",
        "qualified_modalities",
        "required_checks",
    ):
        if source["contract"][field] != contract[field]:
            raise ValueError(f"matched corpus setting differs: {field}")
    ModalityCorpus(root, path)
    return source


def iter_shard(path: Path):
    with gzip.open(path, "rt") as stream:
        for line in stream:
            yield json.loads(line)


def project_record(record: dict, manifest: dict, catalog: dict, modality: str) -> list[dict]:
    """Projection with page references; resolving them never changes text semantics."""
    decision = next(
        d
        for d in manifest["decisions"]
        if (d["algorithm"], d["index"]) == (record["algorithm"], record["decision_index"])
    )
    if record["input_pages"] != decision["input_pages"] or record["state"] != decision["state"]:
        raise ValueError("corpus input page/state binding differs")
    validate_process_state(record["authoritative_input"], record["algorithm"], catalog["states"][decision["state"]])
    blocks = fact_blocks(catalog["task_context"], catalog["states"][decision["state"]], manifest["source"])
    images = [(role, f"{role}/{state}/{index}") for role, state, index in record["input_pages"]]
    return project_messages(record["authoritative_input"], record["algorithm"], modality, blocks, images)


def build_task(root: Path, row: dict, view_result: dict, contract: dict, output: Path, check: bool = False) -> dict:
    """Replay one complete task group, then write or semantically check its shard."""
    _, view_contract = load_view_panel(root, root / contract["panel_manifest"])
    check_task(root, view_result, row, view_contract)
    manifest = read_json(root / view_result["manifest"])
    catalog = read_json(root / manifest["scene_catalog"])
    domain, problem, traces = load_scene_task(root, row)
    replayed_catalog = build_scene_catalog(domain, problem, traces)
    if (
        replayed_catalog["task_context"] != catalog["task_context"]
        or replayed_catalog["decisions"] != catalog["decisions"]
    ):
        raise ValueError("scene task/decision bindings differ from PDDL replay")
    for actual, stored in zip(replayed_catalog["states"], catalog["states"], strict=True):
        if any(stored.get(key) != value for key, value in actual.items()) or not (root / stored["scene_path"]).is_file():
            raise ValueError("scene state/path binding differs from PDDL replay")
    processor = frozen_processor()
    live = {}
    for algorithm, trace in traces.items():
        replayed = replay_inputs(PDDLStateAuthority.from_pddl(domain, problem), algorithm, trace, processor)
        if len(replayed) != row["reference_costs"][algorithm]["decisions"]:
            raise ValueError("replayed decision count differs from selected reference")
        live.update({(algorithm, i): record for i, record in enumerate(replayed)})
    decisions = {(d["algorithm"], d["index"]): d for d in manifest["decisions"]}
    records = []
    token_maxima = Counter()
    for source, source_path in process_rows(root, row):
        algorithm = source["algorithm"]
        index = source.get("record_index", source.get("trace_record_index"))
        key = (algorithm, index)
        replayed = live.pop(key)
        if source["input"] != replayed["input"] or source["target"] != replayed["target"]:
            raise ValueError(f"source corpus differs from live replay: {row['task_id']}:{algorithm}:{index}")
        decision = decisions[key]
        record = {
            "schema_version": SCHEMA,
            "task_id": row["task_id"],
            "algorithm": algorithm,
            "decision_index": index,
            "split": row["split"],
            "domain": row["domain"],
            "difficulty": row["difficulty"],
            "record_id": f"{row['task_id']}:{algorithm}:{index}",
            "source_process_path": source_path,
            "source_record_id": source["record_id"],
            "source_trace_path": row["trace_paths"][algorithm],
            "view_manifest": view_result["manifest"],
            "state": decision["state"],
            "input_pages": decision["input_pages"],
            "authoritative_input": replayed["input"],
            "target": replayed["target"],
            "after_operation": {"runtime_result": replayed["result"], "successor_state": decision["successor"]},
        }
        counts = {}
        for modality in MODALITIES:
            messages = project_record(record, manifest, catalog, modality)
            count = processor.count(messages)
            if count + contract["output_tokens"] > contract["context_tokens"]:
                raise CorpusStop(StopOutcome.VALID_STOP, "complete model input exceeds approved context")
            counts[modality] = count
            token_maxima[modality] = max(token_maxima[modality], count)
        target_tokens = len(processor.processor.tokenizer.encode(canonical(record["target"]), add_special_tokens=False))
        if target_tokens > contract["output_tokens"]:
            raise CorpusStop(StopOutcome.VALID_STOP, "teacher target exceeds frozen output allowance")
        record["tokens"] = {"input": counts, "target": target_tokens}
        token_maxima["target"] = max(token_maxima["target"], target_tokens)
        records.append(record)
    if live or len(records) != len(decisions):
        raise ValueError("partial task decision coverage")
    records.sort(key=lambda r: (r["algorithm"], r["decision_index"]))
    path = output / "tasks" / row["task_id"].replace("/", "__") / "records.jsonl.gz"
    if check:
        stored = list(iter_shard(path))
        if stored != records:
            raise ValueError("released rows differ from replayed semantics/bindings/splits")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with temporary.open("wb") as stream, gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as zipped:
            for record in records:
                zipped.write((canonical(record) + "\n").encode())
        temporary.replace(path)
    result = {
        "task_id": row["task_id"],
        "split": row["split"],
        "domain": row["domain"],
        "difficulty": row["difficulty"],
        "path": str(path.relative_to(root)),
        "view_manifest": view_result["manifest"],
        "source_trace_paths": row["trace_paths"],
        "reference_costs": row["reference_costs"],
        "records": len(records),
        "states": view_result["states"],
        "maximum_tokens": dict(token_maxima),
        "stored_bytes": path.stat().st_size,
    }
    if not check:
        write_json(path.parent / "task.json", result)
    return result


def audit_release(root: Path, results: list[dict], progress=None) -> dict:
    """Exact split/input-label isolation using semantic text keys, without digests.

    Full context/goal content is part of every model input. Partitioning the
    input index by that content keeps the audit small without weakening it.
    SQLite bounds memory when several tasks have the same displayed context.
    """
    contexts: dict[str, tuple[str, int]] = {}
    tasks: dict[str, str] = {}
    counts = Counter()
    with tempfile.TemporaryDirectory(prefix="visual-corpus-audit-") as temporary:
        with sqlite3.connect(str(Path(temporary) / "inputs.sqlite")) as db:
            db.execute(
                "CREATE TABLE inputs (context INTEGER, input TEXT, split TEXT, target TEXT, PRIMARY KEY(context,input))"
            )
            for completed, result in enumerate(results, 1):
                manifest = read_json(root / result["view_manifest"])
                catalog = read_json(root / manifest["scene_catalog"])
                task_identity = canonical(catalog["task_context"])
                if task_identity in tasks and tasks[task_identity] != result["split"]:
                    raise ValueError("cross-split normalized task overlap")
                tasks[task_identity] = result["split"]
                blocks = fact_blocks(catalog["task_context"], catalog["states"][0], manifest["source"])
                context = canonical([blocks["task-context"], blocks["goal"]])
                if context in contexts and contexts[context][0] != result["split"]:
                    raise ValueError("cross-split semantic task overlap")
                contexts.setdefault(context, (result["split"], len(contexts)))
                context_id = contexts[context][1]
                for record in iter_shard(root / result["path"]):
                    if record["split"] != result["split"] or record["task_id"] != result["task_id"]:
                        raise ValueError("row/task split binding differs")
                    state = catalog["states"][record["state"]]
                    # IDs refer to assets, not model-visible semantics. Use full
                    # state semantics instead so duplicate imagery cannot hide conflicts.
                    common = project_record(record, manifest, catalog, "visual-state")[1]["content"][0]["text"]
                    key = canonical([record["algorithm"], common, state["atoms"], state["fluents"]])
                    target = canonical(record["target"])
                    prior = db.execute(
                        "SELECT split,target FROM inputs WHERE context=? AND input=?", (context_id, key)
                    ).fetchone()
                    if prior is not None:
                        if prior[0] != record["split"]:
                            raise ValueError("cross-split model input overlap")
                        if prior[1] != target:
                            raise ValueError("identical model inputs have conflicting teacher targets")
                    else:
                        db.execute("INSERT INTO inputs VALUES (?,?,?,?)", (context_id, key, record["split"], target))
                    counts[f"{record['algorithm']}/{record['split']}"] += 1
                db.commit()
                if progress:
                    progress(completed)
    return {
        "decisions_by_algorithm_split": dict(sorted(counts.items())),
        "semantic_task_overlap_count": 0,
        "model_input_overlap_count": 0,
        "identical_input_conflicting_target_count": 0,
    }


class ModalityCorpus:
    """Load authorized matched training examples with on-demand page composition."""

    def __init__(self, root: Path, report_path: Path):
        self.root = root
        report = read_json(report_path)
        self.contract = report["contract"]
        permission = release_permission(root, self.contract, report["authorization"], report["gate"], report_path.parent)
        if not permission.start_permitted or report.get("outcome") != "PASS" or not report.get("scientific_completion"):
            raise ValueError("corpus loader requires a complete authorized PASS release")
        completed = replace(permission, run_state="completed", scientific_completion=True, start_permitted=False)
        if (
            report.get("receipt") != completed.to_dict()
            or report.get("released_modalities") != self.contract["released_modalities"]
            or any(report.get("checks", {}).get(name) is not True for name in self.contract["required_checks"])
        ):
            raise ValueError("corpus completion receipt/modality/check binding differs")
        panel, _ = load_view_panel(root, root / self.contract["panel_manifest"])
        self.results = {r["task_id"]: r for r in report["results"]}
        if (
            report.get("counts") != self.contract["expected"]
            or not report.get("complete_selected_coverage")
            or len(self.results) != len(report["results"])
            or set(self.results) != {r["task_id"] for r in panel}
        ):
            raise ValueError("corpus release coverage is incomplete")
        self.views = ModalityViewStore(root, root / self.contract["views_report"])
        if self.contract["source_issue"] == 74:
            source = read_json(root / self.contract["source_release"])
            if report["results"] != source["results"]:
                raise ValueError("matched release must reference the exact source task shards")

    def records(self, *, algorithm: str, split: str):
        if split not in ("train", "dev"):
            raise ValueError("held-out access is not authorized")
        # Stable staged curriculum: difficulty, domain, whole task, decision order.
        ordered = sorted(
            self.results.values(),
            key=lambda r: ({"easy": 0, "medium": 1, "hard": 2}[r["difficulty"]], r["domain"], r["task_id"]),
        )
        for result in ordered:
            if result["split"] == split:
                for record in iter_shard(self.root / result["path"]):
                    if record["algorithm"] == algorithm:
                        yield record

    def training_example(self, record: dict, modality: str = "visual-state") -> dict:
        if modality not in self.contract["released_modalities"]:
            raise ValueError("modality is not part of this release")
        result = self.results[record["task_id"]]
        if record["view_manifest"] != result["view_manifest"] or record["split"] != result["split"]:
            raise ValueError("record provenance differs from released task")
        manifest = read_json(self.root / result["view_manifest"])
        catalog = read_json(self.root / manifest["scene_catalog"])
        project_record(record, manifest, catalog, modality)
        observations = self.views.observations(
            record["task_id"], record["algorithm"], record["decision_index"], record["authoritative_input"]
        )
        observation = observations[MODALITIES.index(modality)]
        return {
            "messages": [*observation.messages, {"role": "assistant", "content": canonical(record["target"])}],
            "images": [page.image for page in observation.pages],
            "page_roles": [page.role for page in observation.pages],
        }


# Preserve the released #73 import while exposing the shared three-modality name.
VisualCorpus = ModalityCorpus
