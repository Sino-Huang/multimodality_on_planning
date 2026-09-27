"""#147 data-cost runner: frozen unit order, file-locked resumable queue, train / evaluate / controls / finalize.

Every stage resumes from durable state: the queue claim of a dead worker is stale and re-claimable; training resumes
from the latest HF checkpoint (every 16 updates, only the latest kept); evaluation resumes from partial episode
journals that persist every generated output before submission (``expanded_baseline.run_binding``).
"""

from __future__ import annotations

import contextlib
import fcntl
import gc
import hashlib
import json
import os
import random
import shutil
import socket
import struct
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
STUDY_ID = "data-cost-v1"
ALGORITHMS = ("bfs", "best_first_width")
MODALITIES = ("text-state", "visual-state", "multimodal-state")
SIZES = (512, 1024, 2048, 4096, 8192, 16384)
SEEDS = (17, 29, 71)
EVALUATION_SEED = 17
RANDOM_VALID_SEEDS = (17, 5077, 6131, 7409, 8527)
CONTROL_CELL = {"kind": "control", "algorithm": "bfs", "modality": "text-state", "size": 2048, "epochs": 8, "seed": 17}
GLOBAL_BATCH = 32
CHECKPOINT_EVERY = 16
LORA_RANK, LORA_ALPHA = 64, 128

OUTPUT = Path("outputs/data-cost/v1")
PANEL = Path("configs/experiments/data-cost/panel.json")
MEMBERSHIP = Path("configs/experiments/data-cost/membership.json")
STUDY_V5 = Path("configs/experiments/matched-modalities/study-v5.json")
SCENE_VIEWS = OUTPUT / "preparation/scene-views.json"
SUFFICIENCY = OUTPUT / "preparation/sufficiency.json"
CORPUS_REPORT = Path("outputs/modality_corpus/issue74-matched-32k-v1/release-001/report.json")
SCHEDULE = Path("docs/experiments/data-cost/schedule.json")
LEDGER = OUTPUT / "budget.json"
QUEUE = OUTPUT / "queue"
JOBS = Path("configs/experiments/data-cost")
METRICS = OUTPUT / "metrics"

GPU_HOURS_CAP = 800.0
BUDGET_STOP_GPU_HOURS = 760.0
WORKER_MAX_SECONDS = 7 * 24 * 3600
MIN_CLAIM_SECONDS = 1800
DEADLINE_MARGIN_SECONDS = 900
MAX_SLOT_FAILURES = 2
MAX_CONSECUTIVE_FAILURES = 3
BACKEND_PORT, BACKEND_WORKERS = 18092, 4
GPU_ENDPOINT_PORTS = {0: 18092, 1: 18093}
CONTROL_ENDPOINT_PORTS = (18094, 18095)
ENV_SCRIPT = "~/cd_vlaplan"
BACKEND_PYTHON = Path(".cache/issue70-backend-venv/bin/python")


# --------------------------------------------------------------------------------------------- json helpers


def read(path: Path) -> Any:
    from .scene_assets import read_json

    return read_json(Path(path))


def write(path: Path, value: Any) -> None:
    from .modality_view_preparation import write_json

    write_json(Path(path), value)


def sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


# --------------------------------------------------------------------------------------------- cells and units


def cell_key(cell: dict[str, Any]) -> str:
    if cell["kind"] == "base":
        return f"base:{cell['algorithm']}:{cell['modality']}"
    if cell["kind"] == "control":
        return f"control:{cell['algorithm']}:{cell['modality']}:{cell['size']}x{cell['epochs']}:{cell['seed']}"
    return f"{cell['algorithm']}:{cell['modality']}:{cell['size']}:{cell['seed']}"


def parse_cell(key: str) -> dict[str, Any]:
    parts = key.split(":")
    if parts[0] == "base":
        return {"kind": "base", "algorithm": parts[1], "modality": parts[2]}
    if parts[0] == "control":
        size, epochs = parts[3].split("x")
        return {
            "kind": "control",
            "algorithm": parts[1],
            "modality": parts[2],
            "size": int(size),
            "epochs": int(epochs),
            "seed": int(parts[4]),
        }
    return {
        "kind": "learned",
        "algorithm": parts[0],
        "modality": parts[1],
        "size": int(parts[2]),
        "epochs": 1,
        "seed": int(parts[3]),
    }


def parse_unit(unit: str) -> tuple[str, dict[str, Any]]:
    stage, key = unit.split(":", 1)
    if stage not in ("train", "eval"):
        raise ValueError(f"unknown unit stage: {unit}")
    return stage, parse_cell(key)


def slots() -> list[dict[str, Any]]:
    """The frozen priority order: 6 base evaluations, then seed 17 (ascending size; bfs/bfws x text/visual/
    multimodal), the compute-matched control, seed 29, seed 71. A train unit is always followed by its eval unit
    inside the same claim (same worker)."""

    result = []
    for algorithm in ALGORITHMS:
        for modality in MODALITIES:
            cell = {"kind": "base", "algorithm": algorithm, "modality": modality}
            result.append({"key": cell_key(cell), "cell": cell, "stages": [f"eval:{cell_key(cell)}"]})
    for seed in SEEDS:
        for size in SIZES:
            for algorithm in ALGORITHMS:
                for modality in MODALITIES:
                    cell = {
                        "kind": "learned",
                        "algorithm": algorithm,
                        "modality": modality,
                        "size": size,
                        "epochs": 1,
                        "seed": seed,
                    }
                    key = cell_key(cell)
                    result.append({"key": key, "cell": cell, "stages": [f"train:{key}", f"eval:{key}"]})
        if seed == 17:
            key = cell_key(CONTROL_CELL)
            result.append({"key": key, "cell": dict(CONTROL_CELL), "stages": [f"train:{key}", f"eval:{key}"]})
    return result


def units() -> list[str]:
    return [unit for slot in slots() for unit in slot["stages"]]


def training_dir(cell: dict[str, Any]) -> Path:
    base = OUTPUT / "training"
    if cell["kind"] == "control":
        base = base / "control"
    size = f"{cell['size']}x{cell['epochs']}" if cell["kind"] == "control" else str(cell["size"])
    return base / cell["algorithm"] / cell["modality"] / size / f"seed-{cell['seed']}"


def evaluation_root(cell: dict[str, Any]) -> Path:
    base = OUTPUT / "evaluation"
    if cell["kind"] == "base":
        return base / "base" / cell["algorithm"] / cell["modality"]
    if cell["kind"] == "control":
        base = base / "control"
    size = f"{cell['size']}x{cell['epochs']}" if cell["kind"] == "control" else str(cell["size"])
    return base / cell["algorithm"] / cell["modality"] / size / f"seed-{cell['seed']}"


def controls_root(condition: str, seed: int) -> Path:
    return OUTPUT / "controls" / condition / f"seed-{seed}"


def receipt_path(root: Path, unit: str) -> Path:
    return root / QUEUE / "receipts" / (unit.replace(":", "__") + ".json")


def unit_done(root: Path, unit: str) -> bool:
    path = receipt_path(root, unit)
    return path.is_file() and read(path).get("outcome") == "PASS"


def expected_steps(cell: dict[str, Any]) -> int:
    return cell["size"] * cell["epochs"] // GLOBAL_BATCH


# --------------------------------------------------------------------------------------------- training order


def cell_order(membership: dict[str, Any], cell: dict[str, Any]) -> list[str]:
    """Set = first N retained records; order shuffled per cell (per epoch for the compute-matched control)."""

    algorithm, size, seed = cell["algorithm"], cell["size"], cell["seed"]
    ids = membership["training_record_ids"][algorithm]
    if len(ids) < size or len(set(ids)) != len(ids):
        raise ValueError(f"{algorithm} membership has fewer than {size} distinct records")
    prefix = list(ids[:size])
    if cell["epochs"] == 1:
        random.Random(f"{STUDY_ID}:order:{algorithm}:{size}:{seed}").shuffle(prefix)
        return prefix
    order = []
    for epoch in range(cell["epochs"]):
        part = list(prefix)
        random.Random(f"{STUDY_ID}:order:{algorithm}:{size}:{seed}:epoch{epoch}").shuffle(part)
        order.extend(part)
    return order


class CellDataset:
    """Sequentially sampled supervised examples in the frozen per-cell order (duplicates across epochs)."""

    def __init__(self, corpus, records, modality):
        self.corpus, self.records, self.modality = corpus, records, modality

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        return self.corpus.training_example(self.records[index], self.modality)


def cell_dataset_factory(root: Path, cell: dict[str, Any]) -> Callable:
    from .modality_corpus import ModalityCorpus

    membership = read(root / MEMBERSHIP)
    order = cell_order(membership, cell)
    corpus = ModalityCorpus(root, root / membership.get("corpus_report", str(CORPUS_REPORT)), scene_views=SCENE_VIEWS)
    wanted = set(order)
    indexed = {}
    for split in ("train", "dev"):
        for record in corpus.records(algorithm=cell["algorithm"], split=split):
            if record["record_id"] in wanted:
                indexed[record["record_id"]] = record
    missing = wanted - set(indexed)
    if missing:
        raise ValueError(
            f"{len(missing)} cell records are absent from the corpus/scene views, e.g. {sorted(missing)[:3]}"
        )
    records = [indexed[record_id] for record_id in order]

    def factory(root_, config, algorithm, split):
        if algorithm != cell["algorithm"] or config["modality"] != cell["modality"]:
            raise ValueError("dataset factory called for a different cell")
        return CellDataset(corpus, records if split == "train" else [], cell["modality"])

    return factory


def training_config(root: Path, cell: dict[str, Any]) -> dict[str, Any]:
    study = read(root / STUDY_V5)
    membership = read(root / MEMBERSHIP)
    training = dict(study["training"])
    # Epochs are materialised in the dataset order (per-epoch shuffles); the Trainer sees one pass.
    training["epochs"] = 1
    return {
        "study_id": STUDY_ID,
        "model_id": study["model_id"],
        "model_revision": study["model_revision"],
        "training": training,
        "training_seed": cell["seed"],
        "modality": cell["modality"],
        "corpus_report": membership.get("corpus_report", str(CORPUS_REPORT)),
        "scene_views": str(SCENE_VIEWS),
    }


# --------------------------------------------------------------------------------------------- adapter checks


def safetensors_dtypes(path: Path) -> set[str]:
    with Path(path).open("rb") as stream:
        (length,) = struct.unpack("<Q", stream.read(8))
        header = json.loads(stream.read(length))
    return {entry["dtype"] for name, entry in header.items() if name != "__metadata__"}


def checkpoint_complete(path: Path) -> bool:
    try:
        state = json.loads((path / "trainer_state.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return (
        state.get("global_step") == int(path.name.split("-")[-1])
        and (path / "adapter_model.safetensors").is_file()
        and (path / "optimizer.pt").is_file()
        and (path / "scheduler.pt").is_file()
    )


def sanitize_checkpoints(output: Path) -> list[str]:
    """Remove checkpoints torn by a crash mid-save so HF resumes from the latest complete one."""

    removed = []
    for path in output.glob("checkpoint-*"):
        if not checkpoint_complete(path):
            shutil.rmtree(path)
            removed.append(path.name)
    return removed


def verify_final(root: Path, cell: dict[str, Any], *, check_seed: bool = True) -> dict[str, Any]:
    output = root / training_dir(cell)
    final = output / "final"
    weights = final / "adapter_model.safetensors"
    config_path = final / "adapter_config.json"
    state_path = output / "training_state.json"
    if not (weights.is_file() and config_path.is_file() and state_path.is_file()):
        raise ValueError(f"final adapter incomplete: {final}")
    dtypes = safetensors_dtypes(weights)
    adapter = json.loads(config_path.read_text())
    state = json.loads(state_path.read_text())
    steps = expected_steps(cell)
    problems = []
    if dtypes != {"BF16"}:
        problems.append(f"adapter dtypes {sorted(dtypes)} != BF16")
    if adapter.get("r") != LORA_RANK or adapter.get("lora_alpha") != LORA_ALPHA:
        problems.append("adapter r/alpha differ from 64/128")
    if state.get("global_step") != steps or state.get("max_steps") != steps:
        problems.append(f"steps {state.get('global_step')}/{state.get('max_steps')} != {steps}")
    seed = None
    if check_seed:
        import torch

        args = torch.load(final / "training_args.bin", weights_only=False)
        seed = args.seed
        if args.seed != cell["seed"] or args.data_seed != cell["seed"]:
            problems.append(f"training seed {args.seed} != {cell['seed']}")
    if problems:
        raise ValueError("final adapter verification failed: " + "; ".join(problems))
    return {
        "adapter": str(final),
        "dtype": "BF16",
        "r": adapter["r"],
        "lora_alpha": adapter["lora_alpha"],
        "steps": steps,
        "seed": seed,
        "bytes": weights.stat().st_size,
    }


# --------------------------------------------------------------------------------------------- queue


def this_boot() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except FileNotFoundError:
        return "unknown"


def worker_handle(gpu: int | None) -> dict[str, Any]:
    from .expanded_scheduler import handle

    return {
        **handle(os.getpid()),
        "host": socket.gethostname(),
        "boot_id": this_boot(),
        "gpu": gpu,
        "claimed": time.time(),
    }


def claim_live(claim: dict[str, Any] | None) -> bool:
    from .expanded_scheduler import alive

    return bool(
        claim and claim.get("host") == socket.gethostname() and claim.get("boot_id") == this_boot() and alive(claim)
    )


@contextlib.contextmanager
def queue_state(root: Path):
    directory = root / QUEUE
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "queue.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / "claims.json"
        state = json.loads(path.read_text()) if path.exists() else {"claims": {}, "failures": {}, "history": []}
        yield state
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(path)


def slot_done(root: Path, slot: dict[str, Any]) -> bool:
    return all(unit_done(root, unit) for unit in slot["stages"])


def claim_next(root: Path, gpu: int | None, *, handle: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Claim the first pending slot in priority order that is neither live-claimed, done, nor blocked."""

    handle = handle or worker_handle(gpu)
    with queue_state(root) as state:
        for slot in slots():
            key = slot["key"]
            if slot_done(root, slot):
                continue
            claim = state["claims"].get(key)
            if claim is not None and claim_live(claim):
                continue
            if len(state["failures"].get(key, [])) >= MAX_SLOT_FAILURES:
                continue
            if claim is not None:
                state["history"].append({"event": "stale_reclaimed", "slot": key, "stale": claim, "time": time.time()})
            state["claims"][key] = handle
            state["history"].append({"event": "claimed", "slot": key, "gpu": gpu, "time": time.time()})
            return slot
    return None


def release(root: Path, key: str, *, failure: str | None = None, handle: dict[str, Any] | None = None) -> None:
    with queue_state(root) as state:
        claim = state["claims"].get(key)
        if (
            handle is not None
            and claim is not None
            and (claim["pid"], claim["start_ticks"])
            != (
                handle["pid"],
                handle["start_ticks"],
            )
        ):
            raise ValueError("release by a worker that does not own the claim")
        state["claims"].pop(key, None)
        if failure is not None:
            state["failures"].setdefault(key, []).append({"time": time.time(), "error": failure[-4000:]})
        state["history"].append({"event": "failed" if failure else "released", "slot": key, "time": time.time()})


def queue_summary(root: Path) -> dict[str, Any]:
    path = root / QUEUE / "claims.json"
    state = json.loads(path.read_text()) if path.exists() else {"claims": {}, "failures": {}}
    counts = {"done": 0, "running": 0, "stale": 0, "blocked": 0, "pending": 0}
    running, stale, blocked = [], [], []
    for slot in slots():
        key = slot["key"]
        claim = state["claims"].get(key)
        if slot_done(root, slot):
            counts["done"] += 1
        elif claim is not None and claim_live(claim):
            counts["running"] += 1
            running.append(
                {"slot": key, "gpu": claim.get("gpu"), "stages_done": [u for u in slot["stages"] if unit_done(root, u)]}
            )
        elif len(state["failures"].get(key, [])) >= MAX_SLOT_FAILURES:
            counts["blocked"] += 1
            blocked.append({"slot": key, "last_error": state["failures"][key][-1]["error"][-400:]})
        elif claim is not None:
            counts["stale"] += 1
            stale.append(key)
        else:
            counts["pending"] += 1
    return {
        "slots": len(slots()),
        "units": len(units()),
        "units_done": sum(unit_done(root, unit) for unit in units()),
        **counts,
        "running_slots": running,
        "stale_claims": stale,
        "blocked_slots": blocked,
        "failures": {k: len(v) for k, v in state["failures"].items()},
        "next_pending": next(
            (s["key"] for s in slots() if not slot_done(root, s) and s["key"] not in state["claims"]), None
        ),
    }


# --------------------------------------------------------------------------------------------- budget


def charged_gpu_hours(ledger: dict[str, Any], now: float | None = None) -> float:
    """Charged so far: completed attempts' recorded GPU-h + elapsed GPU-h of running attempts."""

    now = time.time() if now is None else now
    total = 0.0
    for attempt in ledger.get("attempts", []):
        if attempt["status"] == "running":
            total += max(0.0, now - attempt.get("started", now)) * len(attempt["gpus"]) / 3600
        elif attempt["status"] != "reserved":
            total += attempt.get("gpu_hours") or 0.0
    return total


def budget_exhausted(root: Path) -> tuple[bool, float]:
    path = root / LEDGER
    if not path.exists():
        return False, 0.0
    charged = charged_gpu_hours(json.loads(path.read_text()))
    return charged > BUDGET_STOP_GPU_HOURS, charged


# --------------------------------------------------------------------------------------------- panel / protocol


_PANEL_CACHE: dict[str, Any] = {}


def load_panel(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Frozen panel + its reference-view tasks (cached per process; both files are immutable once frozen)."""

    key = str(root)
    if key not in _PANEL_CACHE:
        _PANEL_CACHE[key] = _load_panel(root)
    return _PANEL_CACHE[key]


def _load_panel(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    panel = read(root / PANEL)
    views = read(root / panel.get("view_report", str(OUTPUT / "panel/reference-views.json")))
    by_id = {task["row"]["task_id"]: task for task in views["tasks"]}
    ids = [task["row"]["task_id"] for task in panel["tasks"]]
    if set(ids) != set(by_id):
        raise ValueError("panel reference views differ from the frozen panel")
    for entry in panel["tasks"]:
        if by_id[entry["row"]["task_id"]]["row"] != entry["row"]:
            raise ValueError(f"panel row differs from reference views: {entry['row']['task_id']}")
    return panel, by_id


def evaluation_protocol(root: Path, panel: dict[str, Any], output_root: Path, seed: int) -> dict[str, Any]:
    study = read(root / STUDY_V5)
    return {
        "protocol_id": STUDY_ID,
        "panel_id": panel["panel_id"],
        "output_root": str(output_root),
        "evaluation_seed": seed,
        "model_id": study["model_id"],
        "model_revision": study["model_revision"],
        "root": str(root),
    }


def binding(panel: dict[str, Any], task_index: int, algorithm: str, modality: str, condition: str) -> dict[str, Any]:
    return {
        "index": task_index,
        "worker": 0,
        "task_index": task_index,
        "task_id": panel["tasks"][task_index]["row"]["task_id"],
        "modality": modality,
        "algorithm": algorithm,
        "condition": condition,
    }


def condition_of(cell: dict[str, Any]) -> str:
    return "pretrained_base" if cell["kind"] == "base" else "process_sft"


def endpoint(port: int) -> str:
    return f"http://127.0.0.1:{port}"


# --------------------------------------------------------------------------------------------- stages


def run_episode(root: Path, protocol: dict, task: dict, spec: dict, checkpoint: str | None, url: str, generate):
    """``expanded_baseline.run_binding`` with a working retained-episode path.

    run_binding's own retained branch replays without the ``contract_id`` key replay_visual_episode requires, so a
    completed episode is identity-checked and independently replayed here and run_binding only runs new/partial ones.
    """

    from .expanded_baseline import _identity, binding_paths, independently_replay, run_binding

    episode, partial, view_output = binding_paths(root, protocol, spec)
    if not episode.exists():
        return run_binding(root, protocol, task, spec, checkpoint, url, generate)
    if partial.exists():
        raise ValueError("completed episode retains a conflicting partial journal")
    report = read(episode)
    expected = _identity(protocol, spec, episode, view_output, checkpoint)
    if any(report.get(k) != v for k, v in expected.items()):
        raise ValueError(f"retained episode binding differs: {episode}")
    if independently_replay(root, task, report, url) != report["result"]:
        raise ValueError(f"retained episode replay differs: {episode}")
    return report, True


def run_train(root: Path, cell: dict[str, Any], *, deadline: float, progress: Callable) -> dict[str, Any]:
    from .visual_model import train_visual

    output = root / training_dir(cell)
    membership = read(root / MEMBERSHIP)
    order = cell_order(membership, cell)
    try:
        verification = verify_final(root, cell)
        resumed_from = "final"
    except ValueError:
        verification = None
    if verification is None:
        if (output / "final").exists():
            shutil.rmtree(output / "final")
        removed = sanitize_checkpoints(output) if output.exists() else []
        checkpoints = sorted(output.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1]))
        resumed_from = checkpoints[-1].name if checkpoints else None
        progress("training_start", cell=cell_key(cell), resumed_from=resumed_from, removed_torn=removed)
        started = time.monotonic()
        result = train_visual(
            training_config(root, cell),
            root,
            cell["algorithm"],
            output,
            deadline=deadline,
            progress=progress,
            resume=True,
            dataset_factory=cell_dataset_factory(root, cell),
            save_steps=CHECKPOINT_EVERY,
            save_total_limit=1,
            bf16_final_adapter=True,
            teacher_diagnostics=False,
        )
        if result["training_record_ids"] != order:
            raise ValueError("trained sample order differs from the frozen cell order")
        write(output / "result.json", {**result, "train_wall_seconds_this_attempt": time.monotonic() - started})
        verification = verify_final(root, cell)
    for path in output.glob("checkpoint-*"):
        shutil.rmtree(path)
    return {
        "cell": cell,
        "records": cell["size"],
        "samples": len(order),
        "epochs": cell["epochs"],
        "order_sha256": sha256(order),
        "set_sha256": sha256(sorted(set(order))),
        "resumed_from": resumed_from,
        "verification": verification,
        "checkpoints_deleted": True,
    }


def load_policy(root: Path, cell: dict[str, Any]):
    from transformers import set_seed

    from .visual_attention import configure_visual_attention
    from .visual_model import VisualPolicy

    study = read(root / STUDY_V5)
    inference = study["inference"]
    set_seed(EVALUATION_SEED)
    adapters = {cell["algorithm"]: str(root / training_dir(cell) / "final")} if cell["kind"] != "base" else {}
    policy = VisualPolicy(
        model_id=study["model_id"],
        revision=study["model_revision"],
        adapter_paths=adapters,
        device="cuda:0",
        max_context_tokens=study["context_tokens"],
        max_new_tokens=study["output_tokens"],
        max_batch_size=inference["max_batch_size"],
        max_batch_input_tokens=inference["max_padded_batch_input_tokens"],
        autocast_adapter_dtype=False,
    )
    configure_visual_attention(policy.model, inference["attention"])
    policy.identity.update(memoize_identical_inputs=False, adapter_storage_dtype="bfloat16")
    return policy, study


def run_eval(root: Path, cell: dict[str, Any], *, gpu: int, deadline: float, progress: Callable) -> dict[str, Any]:
    from .expanded_baseline import binding_paths

    if cell["kind"] != "base":
        verify_final(root, cell)
    panel, tasks = load_panel(root)
    protocol = evaluation_protocol(root, panel, evaluation_root(cell), EVALUATION_SEED)
    condition = condition_of(cell)
    checkpoint = str(training_dir(cell) / "final") if cell["kind"] != "base" else None
    adapter_id = cell["algorithm"] if cell["kind"] != "base" else None
    state: dict[str, Any] = {"policy": None, "calls": 0, "single_above_cap": 0}

    def generate(example):
        if state["policy"] is None:
            state["policy"], state["study"] = load_policy(root, cell)
            state["policy"].stop_at = deadline
        policy, study = state["policy"], state["study"]
        frozen_cap = study["inference"]["max_padded_batch_input_tokens"]
        tokens = example["binding"]["input_tokens"]
        above = tokens > frozen_cap and study["inference"].get("allow_qualified_single_input_above_batch_cap")
        # study-v5: a single qualified input may exceed the padded-batch cap (context guard still applies).
        policy.max_batch_input_tokens = study["context_tokens"] - study["output_tokens"] if above else frozen_cap
        try:
            output = policy.generate([example], adapter_id)[0]
        finally:
            policy.max_batch_input_tokens = frozen_cap
        state["calls"] += 1
        state["single_above_cap"] += int(bool(above))
        return output, policy.last_generation_usage["generated_sequence_tokens"]

    episodes, successes, retained = [], 0, 0
    try:
        for index, entry in enumerate(panel["tasks"]):
            task = tasks[entry["row"]["task_id"]]
            spec = binding(panel, index, cell["algorithm"], cell["modality"], condition)
            report, was_retained = run_episode(
                root, protocol, task, spec, checkpoint, endpoint(GPU_ENDPOINT_PORTS[gpu]), generate
            )
            retained += int(was_retained)
            successes += int(bool(report["result"].get("invariant_valid_success")))
            episodes.append(str(binding_paths(root, protocol, spec)[0].relative_to(root)))
            progress("evaluation", cell=cell_key(cell), completed=index + 1, total=len(panel["tasks"]))
    finally:
        if state["policy"] is not None:
            del state["policy"]
            gc.collect()
            import torch

            torch.cuda.empty_cache()
    return {
        "cell": cell,
        "condition": condition,
        "episodes": episodes,
        "successes": successes,
        "retained": retained,
        "model_calls_this_attempt": state["calls"],
        "single_inputs_above_batch_cap": state["single_above_cap"],
        "checkpoint": checkpoint,
    }


def run_unit(root: Path, unit: str, *, gpu: int, deadline: float, progress: Callable) -> dict[str, Any]:
    stage, cell = parse_unit(unit)
    started = time.time()
    if stage == "train":
        body = run_train(root, cell, deadline=deadline, progress=progress)
    else:
        body = run_eval(root, cell, gpu=gpu, deadline=deadline, progress=progress)
    receipt = {
        "unit": unit,
        "outcome": "PASS",
        **body,
        "gpu": gpu,
        "host": socket.gethostname(),
        "started": started,
        "finished": time.time(),
        "attempt_dir": os.environ.get("EXPANDED_ATTEMPT_DIR"),
    }
    write(receipt_path(root, unit), receipt)
    return receipt


# --------------------------------------------------------------------------------------------- worker


def attempt_deadline(root: Path) -> float:
    """Monotonic deadline from the scheduler attempt (admission + max_seconds, GPU cutoff) minus a save margin."""

    directory = os.environ.get("EXPANDED_ATTEMPT_DIR")
    ledger_path = root / LEDGER
    if not directory or not ledger_path.exists():
        return float("inf")
    from .expanded_scheduler import timestamp

    ledger = json.loads(ledger_path.read_text())
    attempt = next((a for a in ledger["attempts"] if a.get("directory") == directory), None)
    if attempt is None:
        return float("inf")
    wall = min(attempt["admitted"] + attempt["max_seconds"], timestamp(ledger["schedule"]["gpu_cutoff_utc"]))
    return time.monotonic() + (wall - DEADLINE_MARGIN_SECONDS - time.time())


def worker(root: Path, gpu: int, *, max_slots: int | None = None) -> dict[str, Any]:
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(gpu):
        raise ValueError(f"worker --gpu {gpu} requires CUDA_VISIBLE_DEVICES={gpu} (set after sourcing the env)")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError("worker requires a scheduler-assigned MASTER_PORT")
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"]) if os.environ.get("EXPANDED_PROGRESS_PATH") else None
    deadline = attempt_deadline(root)
    handle = worker_handle(gpu)
    log: list[dict[str, Any]] = []
    stop_reason = "queue_empty"
    consecutive = 0
    processed = 0

    def progress(stage, **values):
        record = {"time": time.time(), "stage": stage, **values}
        print(json.dumps(record), flush=True)
        if progress_path is not None:
            done = sum(slot_done(root, s) for s in slots())
            write(progress_path, {"completed": done, "total": len(slots()), "current": record})

    while True:
        exhausted, charged = budget_exhausted(root)
        if exhausted:
            stop_reason = f"budget: charged {charged:.1f} GPU-h > {BUDGET_STOP_GPU_HOURS}"
            break
        if deadline - time.monotonic() < MIN_CLAIM_SECONDS:
            stop_reason = "attempt deadline too close to claim a new slot"
            break
        if max_slots is not None and processed >= max_slots:
            stop_reason = "max_slots"
            break
        slot = claim_next(root, gpu, handle=handle)
        if slot is None:
            break
        processed += 1
        progress("claimed", slot=slot["key"], charged_gpu_hours=charged)
        try:
            for unit in slot["stages"]:
                if unit_done(root, unit):
                    continue
                run_unit(root, unit, gpu=gpu, deadline=deadline, progress=progress)
                progress("unit_done", unit=unit, receipt=str(receipt_path(root, unit).relative_to(root)))
            release(root, slot["key"], handle=handle)
            log.append({"slot": slot["key"], "outcome": "PASS"})
            consecutive = 0
        except Exception as error:
            if time.monotonic() >= deadline and str(error).startswith("VALID_STOP"):
                release(root, slot["key"], handle=handle)
                log.append({"slot": slot["key"], "outcome": "DEADLINE"})
                stop_reason = "attempt deadline (valid stop; resumable)"
                break
            text = traceback.format_exc()
            print(text, flush=True)
            release(root, slot["key"], failure=text, handle=handle)
            log.append({"slot": slot["key"], "outcome": "FAILED", "error": repr(error)})
            consecutive += 1
            with contextlib.suppress(Exception):
                import torch

                gc.collect()
                torch.cuda.empty_cache()
            if consecutive >= MAX_CONSECUTIVE_FAILURES:
                raise RuntimeError(f"{consecutive} consecutive slot failures; stopping worker") from error
    result = {"gpu": gpu, "stop_reason": stop_reason, "slots": log, "queue": queue_summary(root)}
    if os.environ.get("EXPANDED_ATTEMPT_DIR"):
        write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", result)
    return result


# --------------------------------------------------------------------------------------------- controls (CPU)


def control_runs() -> list[tuple[str, int]]:
    return [("exact_reference", EVALUATION_SEED)] + [("random_valid", seed) for seed in RANDOM_VALID_SEEDS]


def _control_episode(args):
    root, condition, seed, algorithm, index, port = args
    panel, tasks = load_panel(root)
    protocol = evaluation_protocol(root, panel, controls_root(condition, seed), seed)
    spec = binding(panel, index, algorithm, "text-state", condition)
    report, retained = run_episode(root, protocol, tasks[spec["task_id"]], spec, None, endpoint(port), None)
    return {
        "condition": condition,
        "seed": seed,
        "algorithm": algorithm,
        "task_id": spec["task_id"],
        "retained": retained,
        "success": bool(report["result"].get("invariant_valid_success")),
    }


def run_controls(root: Path, *, workers: int = 2) -> dict[str, Any]:
    from concurrent.futures import ProcessPoolExecutor, as_completed

    panel, _ = load_panel(root)
    ensure_backend(root, CONTROL_ENDPOINT_PORTS)
    jobs = [
        (root, condition, seed, algorithm, index, CONTROL_ENDPOINT_PORTS[n % len(CONTROL_ENDPOINT_PORTS)])
        for n, (condition, seed, algorithm, index) in enumerate(
            (c, s, a, i) for c, s in control_runs() for a in ALGORITHMS for i in range(len(panel["tasks"]))
        )
    ]
    results, failures = [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_control_episode, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                results.append(future.result())
            except Exception as error:
                failures.append({"job": [str(x) for x in job[1:5]], "error": repr(error)})
            print(
                json.dumps({"stage": "controls", "completed": len(results) + len(failures), "total": len(jobs)}),
                flush=True,
            )
    summary = {
        "outcome": "PASS" if not failures else "INCOMPLETE",
        "episodes": len(results),
        "expected": len(jobs),
        "failures": failures,
        "time": time.time(),
    }
    write(root / OUTPUT / "controls/receipt.json", summary)
    return summary


# --------------------------------------------------------------------------------------------- finalize


def expected_episodes(root: Path, panel: dict[str, Any]) -> list[dict[str, Any]]:
    """Every episode of the frozen design with its metadata, protocol output root, condition and binding."""

    from .expanded_baseline import binding_paths

    specs = []

    def add(meta, output_root, seed, algorithm, modality, condition, checkpoint):
        protocol = evaluation_protocol(root, panel, output_root, seed)
        for index, entry in enumerate(panel["tasks"]):
            spec = binding(panel, index, algorithm, modality, condition)
            episode = binding_paths(root, protocol, spec)[0]
            specs.append(
                {
                    **meta,
                    "algorithm": algorithm,
                    "modality": modality,
                    "condition": condition,
                    "task_id": entry["row"]["task_id"],
                    "domain": entry["row"]["domain"],
                    "stratum": entry["row"].get("difficulty"),
                    "episode": str(episode.relative_to(root)),
                    "checkpoint": checkpoint,
                }
            )

    for slot in slots():
        cell = slot["cell"]
        meta = {
            "kind": cell["kind"],
            "size": cell.get("size"),
            "epochs": cell.get("epochs"),
            "seed": cell.get("seed", EVALUATION_SEED) if cell["kind"] != "base" else None,
        }
        checkpoint = str(training_dir(cell) / "final") if cell["kind"] != "base" else None
        add(
            meta,
            evaluation_root(cell),
            EVALUATION_SEED,
            cell["algorithm"],
            cell["modality"],
            condition_of(cell),
            checkpoint,
        )
    for condition, seed in control_runs():
        for algorithm in ALGORITHMS:
            add(
                {"kind": condition, "size": None, "epochs": None, "seed": seed},
                controls_root(condition, seed),
                seed,
                algorithm,
                "text-state",
                condition,
                None,
            )
    return specs


def episode_metrics(report: dict[str, Any]) -> dict[str, Any]:
    events = report["events"]
    calls = len(events)
    accepted = sum(1 for event in events if event["accepted"])
    first_invalid = next((event["index"] + 1 for event in events if not event["accepted"]), None)
    result = report["result"]
    return {
        "success": bool(result.get("invariant_valid_success")),
        "goal_reached": result.get("goal_reached"),
        "calls": calls,
        "accepted": accepted,
        "valid_op_rate": accepted / calls if calls else None,
        "first_invalid_step": first_invalid,
        "first_invalid_censored": first_invalid is None,
        "termination_reason": result.get("termination_reason"),
        "model_call_limit": result.get("model_call_limit"),
    }


def _replay_one(args):
    root, spec, port, replay = args
    from .expanded_baseline import independently_replay

    path = root / spec["episode"]
    if not path.exists():
        partial = path.with_name(path.name.removesuffix(".json.gz") + ".partial.json.gz")
        return {**spec, "status": "partial" if partial.exists() else "missing"}
    report = read(path)
    row = {**spec, **episode_metrics(report), "status": "recorded", "replayed": False}
    if replay:
        _, tasks = load_panel(root)
        try:
            replayed = independently_replay(root, tasks[spec["task_id"]], report, endpoint(port))
            if replayed != report["result"]:
                raise ValueError("replayed result differs")
            row["replayed"] = True
        except Exception as error:
            row["status"] = "mismatch"
            row["replay_error"] = repr(error)
    return row


def collect_episodes(root: Path, *, replay: bool, workers: int = 1) -> dict[str, Any]:
    panel, _ = load_panel(root)
    specs = expected_episodes(root, panel)
    jobs = [(root, spec, CONTROL_ENDPOINT_PORTS[i % 2], replay) for i, spec in enumerate(specs)]
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_replay_one, jobs, chunksize=8))
    else:
        rows = [_replay_one(job) for job in jobs]
    recorded = [r for r in rows if r["status"] in ("recorded", "mismatch")]
    return {
        "study": STUDY_ID,
        "panel_id": panel["panel_id"],
        "replay_verified": replay,
        "expected": len(rows),
        "recorded": len(recorded),
        "replayed": sum(1 for r in rows if r.get("replayed")),
        "missing": [r["episode"] for r in rows if r["status"] == "missing"],
        "partial": [r["episode"] for r in rows if r["status"] == "partial"],
        "mismatches": [{"episode": r["episode"], "error": r["replay_error"]} for r in rows if r["status"] == "mismatch"],
        "rows": recorded,
    }


def finalize(root: Path, *, workers: int = 4) -> dict[str, Any]:
    table = collect_episodes(root, replay=True, workers=workers)
    table["finalized"] = time.time()
    table["verdict"] = (
        "COMPLETE_REPLAYED"
        if not table["missing"] and not table["partial"] and not table["mismatches"]
        else "INCOMPLETE_EXPLICIT_MISSINGNESS"
    )
    write(root / METRICS / "episodes.json", table)
    columns = [
        "kind", "algorithm", "modality", "size", "epochs", "seed", "condition", "task_id", "domain", "stratum",
        "success", "calls", "accepted", "valid_op_rate", "first_invalid_step", "termination_reason", "replayed",
        "episode",
    ]  # fmt: skip
    import csv

    with (root / METRICS / "episodes.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(table["rows"])
    return {k: v for k, v in table.items() if k != "rows"} | {
        "missing": len(table["missing"]),
        "partial": len(table["partial"]),
        "mismatches": table["mismatches"],
    }


# --------------------------------------------------------------------------------------------- scheduling


def schedule_document() -> dict[str, Any]:
    return {
        "program_id": STUDY_ID,
        "status": "authorized_followup_window",
        "issue": 147,
        "authorization": {
            "granted_by": "author decision 2026-09-26 (docs/experiments/data-cost/issue-147-feasibility.md)",
            "window_gpu_hours_cap": GPU_HOURS_CAP,
            "basis": (
                "108 main cells + compute-matched control + 6 base evaluations; ~615 GPU-h expected, ~770 with x1.25"
            ),
        },
        "start_utc": "2026-09-26T00:00:00Z",
        "gpu_cutoff_utc": "2026-11-15T00:00:00Z",
        "handoff_deadline_utc": "2026-11-16T00:00:00Z",
        "deadline_kind": "soft_handoff",
        "hardware": {
            "gpus": 2,
            "model": "NVIDIA A100 80GB",
            "preserve_unrelated_processes": True,
            "max_own_model_workers_per_gpu": 1,
        },
        "experiment_gpu_hours_cap": GPU_HOURS_CAP,
        "allocations_gpu_hours": {"data_cost": GPU_HOURS_CAP},
        "accounting": {
            "metric": (
                "sum of own allocated model-worker GPU durations across devices; include model loading, saves, "
                "failures and retries"
            ),
            "ledger": str(LEDGER),
            "worker_stop_rule": (
                "a worker claims no new unit once charged GPU-h (terminal attempts + running elapsed) exceeds "
                f"{BUDGET_STOP_GPU_HOURS}"
            ),
            "reset_on_resume": False,
            "automatic_total_extension": False,
        },
        "master_port_pool": [18860, 18861, 18862, 18863],
        "backend_ports": list(range(BACKEND_PORT, BACKEND_PORT + BACKEND_WORKERS)),
    }


def ensure_schedule(root: Path) -> dict[str, Any]:
    path = root / SCHEDULE
    if path.exists():
        existing = json.loads(path.read_text())
        if existing != schedule_document():
            raise ValueError(f"{SCHEDULE} differs from the frozen schedule; the clock cannot reset")
        return existing
    document = schedule_document()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n")
    return document


def worker_command(gpu: int) -> list[str]:
    # A login shell sources the project environment (HF_HOME, PYTHONPATH, ...); the GPU is pinned AFTER sourcing.
    return [
        "bash",
        "-lc",
        f"source {ENV_SCRIPT} && export CUDA_VISIBLE_DEVICES={gpu} && "
        f"exec python scripts/run_data_cost.py worker --gpu {gpu}",
    ]


def hook_command() -> list[str]:
    return [
        "bash",
        "-lc",
        f"source {ENV_SCRIPT} && export CUDA_VISIBLE_DEVICES= && exec python scripts/run_data_cost.py hook",
    ]


def job_document(gpu: int, job_id: str, max_seconds: int, resume_reason: str | None = None) -> dict[str, Any]:
    job = {
        "job_id": job_id,
        "branch": "data_cost",
        "gpus": [gpu],
        "max_seconds": int(max_seconds),
        "total": len(slots()),
        "command": worker_command(gpu),
        "completion_hook": hook_command(),
    }
    if resume_reason:
        job["resume_reason"] = resume_reason
    return job


def base_job_id(gpu: int) -> str:
    return f"data-cost-worker-gpu{gpu}"


def _ledger(root: Path) -> dict[str, Any]:
    path = root / LEDGER
    return json.loads(path.read_text()) if path.exists() else {"attempts": []}


def gpu_state(root: Path, gpu: int) -> dict[str, Any]:
    """Latest attempt on this GPU's job line and the job id/resume flag to use for the next launch."""

    from .expanded_scheduler import alive

    ledger = _ledger(root)
    attempts = [a for a in ledger["attempts"] if a["job_id"].startswith(base_job_id(gpu))]
    active = [a for a in attempts if a["status"] in ("reserved", "running")]
    if active:
        latest = active[-1]
        return {"active": True, "live": alive(latest.get("supervisor")), "attempt": latest}
    if not attempts:
        return {"active": False, "job_id": base_job_id(gpu), "needs_reason": False}
    latest = attempts[-1]
    if latest["status"] == "succeeded":
        # A cleanly exited job line cannot be relaunched; continue on a fresh line.
        lines = {a["job_id"] for a in attempts}
        return {"active": False, "job_id": f"{base_job_id(gpu)}-r{len(lines) + 1}", "needs_reason": False}
    return {"active": False, "job_id": latest["job_id"], "needs_reason": True}


def launch_seconds(root: Path, schedule: dict[str, Any], launching: int) -> int:
    from .expanded_scheduler import charged, timestamp

    ledger = _ledger(root)
    committed = sum(charged(a) for a in ledger["attempts"])
    remaining_hours = GPU_HOURS_CAP - committed
    by_budget = remaining_hours * 3600 / max(1, launching) - 60
    by_cutoff = timestamp(schedule["gpu_cutoff_utc"]) - time.time() - 300
    seconds = int(min(WORKER_MAX_SECONDS, by_budget, by_cutoff))
    if seconds < 3600:
        raise ValueError(f"cannot admit a worker: {seconds} s left under the budget/cutoff")
    return seconds


def launch_workers(
    root: Path, *, resume_reason: str | None = None, gpus=(0, 1), dry_run: bool = False
) -> list[dict[str, Any]]:
    schedule = schedule_document() if dry_run and not (root / SCHEDULE).exists() else ensure_schedule(root)
    plan = []
    for gpu in gpus:
        state = gpu_state(root, gpu)
        if state["active"]:
            plan.append(
                {
                    "gpu": gpu,
                    "action": "skip",
                    "reason": "attempt reserved/running",
                    "job_id": state["attempt"]["job_id"],
                }
            )
            continue
        plan.append({"gpu": gpu, "action": "launch", "job_id": state["job_id"], "needs_reason": state["needs_reason"]})
    launching = [p for p in plan if p["action"] == "launch"]
    if not launching:
        return plan
    if all(slot_done(root, s) for s in slots()):
        return [dict(p, action="skip", reason="all units done") if p["action"] == "launch" else p for p in plan]
    seconds = launch_seconds(root, schedule, len(launching))
    for item in launching:
        reason = resume_reason if item["needs_reason"] else None
        if item["needs_reason"] and not reason:
            reason = "relaunch after an interrupted/failed attempt; queue claims, checkpoints and journals resume"
        job = job_document(item["gpu"], item["job_id"], seconds, reason)
        job_path = root / JOBS / f"{item['job_id']}-job.json"
        item["job"] = str(job_path.relative_to(root))
        item["max_seconds"] = seconds
        if dry_run:
            item["action"] = "would_launch"
            continue
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job_path.write_text(json.dumps(job, indent=1) + "\n")
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/run_expanded_study.py",
                "launch",
                "--schedule",
                str(SCHEDULE),
                "--ledger",
                str(LEDGER),
                "--job",
                str(job_path.relative_to(root)),
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )
        item["returncode"] = completed.returncode
        if completed.returncode != 0:
            item["error"] = completed.stderr[-2000:]
        else:
            attempt = json.loads(completed.stdout)
            item["attempt"] = attempt["attempt"]
            item["master_port"] = attempt["master_port"]
    return plan


def reconcile(root: Path) -> dict[str, Any]:
    if not (root / LEDGER).exists():
        return {"skipped": "no ledger yet"}
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_expanded_study.py",
            "reconcile",
            "--schedule",
            str(SCHEDULE),
            "--ledger",
            str(LEDGER),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("scheduler reconcile refused: " + completed.stderr[-2000:])
    ledger = json.loads(completed.stdout)
    return {"interrupted": [f"{a['job_id']}#{a['attempt']}" for a in ledger["attempts"] if a["status"] == "interrupted"]}


def backend_up(port: int, timeout: float = 1.0) -> bool:
    with socket.socket() as sock:
        sock.settimeout(timeout)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def ensure_backend(root: Path, ports=None, *, wait_seconds: float = 120) -> dict[str, Any]:
    """Start one single-port Planimation backend process per down port (existing services are left alone)."""

    ports = list(ports or range(BACKEND_PORT, BACKEND_PORT + BACKEND_WORKERS))
    down = [port for port in ports if not backend_up(port)]
    if not down:
        return {"backend": "already_up", "ports": ports}
    directory = root / OUTPUT / "backend"
    directory.mkdir(parents=True, exist_ok=True)
    started = {}
    for port in down:
        log = directory / f"backend-{port}-{int(time.time())}.log"
        command = f"source {ENV_SCRIPT} && exec {BACKEND_PYTHON} scripts/serve_issue70_planimation.py --port {port}"
        with log.open("a") as stream:
            process = subprocess.Popen(
                ["bash", "-lc", command], cwd=root, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
            )
        started[port] = {"pid": process.pid, "log": str(log.relative_to(root)), "process": process}
    deadline = time.time() + wait_seconds
    while time.time() < deadline and not all(backend_up(port) for port in down):
        if any(item["process"].poll() is not None for item in started.values()):
            break
        time.sleep(1)
    record = {
        "backend": "started",
        "ports": ports,
        "started": {port: {k: v for k, v in item.items() if k != "process"} for port, item in started.items()},
    }
    write(directory / "service.json", {**record, "time": time.time()})
    failed = [port for port in down if not backend_up(port)]
    if failed:
        raise RuntimeError(f"Planimation backend did not come up on {failed}; see {directory}")
    return record


def resume(root: Path, *, reason: str | None = None) -> dict[str, Any]:
    """One command after a reboot: backend up, reconcile dead attempts, relaunch the missing workers."""

    backend = ensure_backend(root)
    reconciled = reconcile(root)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    plan = launch_workers(root, resume_reason=reason or f"resume {stamp}: reconciled {reconciled}")
    return {"backend": backend, "reconcile": reconciled, "workers": plan}


def status(root: Path) -> dict[str, Any]:
    from .expanded_scheduler import alive

    ledger = _ledger(root)
    attempts = [
        {
            "job": f"{a['job_id']}#{a['attempt']}",
            "status": a["status"],
            "gpus": a["gpus"],
            "live": alive(a.get("supervisor")) if a["status"] in ("reserved", "running") else None,
            "gpu_hours": round(a.get("gpu_hours") or 0.0, 3),
            "directory": a.get("directory"),
        }
        for a in ledger["attempts"]
    ]
    control_receipt = root / OUTPUT / "controls/receipt.json"
    episodes = root / METRICS / "episodes.json"
    return {
        "study": STUDY_ID,
        "queue": queue_summary(root),
        "gpu_hours_charged": round(charged_gpu_hours(ledger), 3),
        "gpu_hours_stop_rule": BUDGET_STOP_GPU_HOURS,
        "gpu_hours_cap": GPU_HOURS_CAP,
        "attempts": attempts,
        "backend_ports_up": {port: backend_up(port) for port in range(BACKEND_PORT, BACKEND_PORT + BACKEND_WORKERS)},
        "controls": read(control_receipt) if control_receipt.exists() else None,
        "finalize": ({k: v for k, v in read(episodes).items() if k != "rows"} if episodes.exists() else None),
        "inputs_present": {str(path): (root / path).exists() for path in (PANEL, MEMBERSHIP, SCENE_VIEWS, SUFFICIENCY)},
    }


def hook() -> dict[str, Any]:
    """Scheduler completion hook (CPU): summarise the attempt; continue the GPU's job line after a clean deadline stop.

    Only a worker that exited 0 because its 7-day attempt clock ran out is relaunched (fresh job line); failures,
    budget stops and an empty queue are never relaunched automatically.
    """

    terminal_path = Path(os.environ["EXPANDED_TERMINAL_PATH"])
    terminal = json.loads(terminal_path.read_text())
    worker_result_path = terminal_path.parent / "worker-result.json"
    worker_result = json.loads(worker_result_path.read_text()) if worker_result_path.exists() else {}
    summary = {
        "job": f"{terminal['job_id']}#{terminal['attempt']}",
        "status": terminal["status"],
        "returncode": terminal.get("returncode"),
        "error": terminal.get("error"),
        "gpu_hours": terminal.get("gpu_hours"),
        "stop_reason": worker_result.get("stop_reason"),
        "queue": queue_summary(ROOT),
        "resume_hint": "source ~/cd_vlaplan && python scripts/run_data_cost.py resume",
    }
    stop = worker_result.get("stop_reason") or ""
    if terminal["status"] == "succeeded" and stop.startswith("attempt deadline"):
        try:
            summary["continuation"] = launch_workers(ROOT, gpus=tuple(terminal["gpus"]))
        except Exception as error:
            summary["continuation"] = {"error": repr(error)}
    write(terminal_path.parent / "data-cost-audit.json", summary)
    return summary
