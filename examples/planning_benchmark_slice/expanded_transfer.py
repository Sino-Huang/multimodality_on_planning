"""Transfer (#104-#107) branch machinery: zero-shot transfer of planning-trained adapters.

The frozen v1 contract is configs/experiments/expanded-study/transfer-protocol.json. This module
freezes FOLIO/GSM8K/HumanEval subsets before any model output, probes runtime gates, admits
against the 24 GPU-hour branch budget and the absolute GPU cutoff, runs the frozen cells (v1:
base + three BFS LoRA adapters) on two workers, and scores with pinned parsing and a sandboxed
HumanEval executor. GPU stages (probe/run) are executed by the scheduler; every producing stage
has an independent audit.

Extension protocols (e.g. transfer-protocol-v2.json) set "extends" to the v1 protocol id and drive
the cell set/order, output root, subset sizes, worker assignment and publication filenames through
the protocol document itself; they reuse the v1 frozen subsets byte-identically and never rerun
the base cell. A protocol without "extends" follows the v1 paths exactly.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .batched_search_evaluation import form_deterministic_batches, lower_95_throughput_bound
from .modality_corpus_replay import canonical
from .modality_view_preparation import write_json
from .scene_assets import read_json

PROTOCOL_SCHEMA = "expanded_transfer_protocol_v1"
PROTOCOL_ID = "transfer-folio-humaneval-gsm8k-v1"
PROTOCOL_FILE = "configs/experiments/expanded-study/transfer-protocol.json"
BRANCH = "transfer"
OUTPUT_ROOT = "outputs/expanded-study/v1/transfer"
LEDGER_PATH = "outputs/expanded-study/v1/budget.json"
SCHEDULE_DOC = "docs/experiments/expanded-study/schedule.json"
DOCS_DIR = "docs/experiments/expanded-study"
CORPUS_REPORT = "outputs/modality_corpus/issue74-matched-32k-v1/release-001/report.json"
GPU_CUTOFF_UTC = "2026-09-21T11:55:19Z"
PORT_POOL = (18800, 18801, 18802, 18803, 18804, 18805)
CELL_ORDER = ("base", "bfs_text", "bfs_visual", "bfs_multimodal")
ADAPTED_CELLS = ("bfs_text", "bfs_visual", "bfs_multimodal")
BENCHMARK_ORDER = ("folio", "gsm8k", "humaneval")
L0_SIZES = {"folio": 200, "gsm8k": 200, "humaneval": 164}
L1_SIZES = {"folio": 100, "gsm8k": 100, "humaneval": 82}
WORKER_BENCHMARKS = {0: ("gsm8k",), 1: ("folio", "humaneval")}
WORKER_GPUS = {0: 0, 1: 1}
SAFETY_FACTOR = 1.25
BRANCH_GPU_HOURS = 24
MAX_CONTEXT_TOKENS = 8192
MAX_BATCH_SIZE = 8
MAX_BATCH_INPUT_TOKENS = 48_000
SEED = 17
LEAKAGE_NGRAM = 8
# The scheduler hard-caps completion hooks at 300s; bound the sandbox re-execution phase.
RESAMPLE_BUDGET_SECONDS = 150

# v1 frozen subsets, pinned so extension protocols verify and reference them byte-identically.
V1_SUBSETS_PATH = f"{OUTPUT_ROOT}/subsets.json"
V1_SUBSETS_SHA256 = "24157aaadc6f3c2b1bf7ff1e858a3a7bef93f98f68354d8d1334b30bfaa12627"


# ---------------------------------------------------------------------------
# Protocol-driven layout: cell set/order, output root, sizes, worker mapping
# ---------------------------------------------------------------------------
# Every helper falls back to the v1 constants when the protocol lacks the field,
# so the v1 protocol and existing fixtures behave exactly as before.


def cell_order(protocol: Mapping[str, Any]) -> tuple[str, ...]:
    order = protocol.get("execution_topology", {}).get("cell_order_per_benchmark")
    return tuple(order) if order else CELL_ORDER


def adapted_cells(protocol: Mapping[str, Any]) -> tuple[str, ...]:
    order = cell_order(protocol)
    cells = protocol.get("cells", {})
    if cells:
        return tuple(cell for cell in order if cells.get(cell, {}).get("adapter_id"))
    return tuple(cell for cell in order if cell != "base")


def output_root(protocol: Mapping[str, Any]) -> str:
    return str(protocol.get("evidence", {}).get("output_root", OUTPUT_ROOT))


def doc_stem(protocol: Mapping[str, Any]) -> str:
    """Publication filename stem: the output-root basename ('transfer', 'transfer-v2', ...)."""
    return output_root(protocol).rstrip("/").rsplit("/", 1)[-1]


def l0_sizes(protocol: Mapping[str, Any]) -> dict[str, int]:
    benchmarks = protocol.get("benchmarks", {})
    sizes = benchmarks.get("subset_sizes")
    if sizes:
        return dict(sizes)
    per_benchmark = {
        name: spec["subset_size"]
        for name, spec in benchmarks.items()
        if isinstance(spec, Mapping) and "subset_size" in spec
    }
    return per_benchmark or dict(L0_SIZES)


def l1_sizes(protocol: Mapping[str, Any]) -> dict[str, int]:
    sizes = protocol.get("benchmarks", {}).get("l1_subset_sizes")
    return dict(sizes) if sizes else dict(L1_SIZES)


def _worker_ids(protocol: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    workers = protocol.get("execution_topology", {}).get("workers", {})
    return {int(name.rsplit("-", 1)[1]): spec for name, spec in workers.items()}


def worker_benchmarks(protocol: Mapping[str, Any]) -> dict[int, tuple[str, ...]]:
    workers = _worker_ids(protocol)
    if not workers:
        return dict(WORKER_BENCHMARKS)
    return {worker: tuple(spec["benchmarks"]) for worker, spec in workers.items()}


def worker_gpus(protocol: Mapping[str, Any]) -> dict[int, int]:
    workers = _worker_ids(protocol)
    if not workers:
        return dict(WORKER_GPUS)
    return {worker: int(spec["gpu"]) for worker, spec in workers.items()}


def subsets_reference(protocol: Mapping[str, Any]) -> dict[str, str] | None:
    """Pinned v1 subsets reference for extension protocols; None for the v1 protocol."""
    reference = protocol.get("benchmarks", {}).get("subsets_reference")
    if reference:
        return dict(reference)
    if protocol.get("extends"):
        return {"path": V1_SUBSETS_PATH, "sha256": V1_SUBSETS_SHA256}
    return None


def _protocol_ids(protocol: Mapping[str, Any]) -> set[str]:
    """Protocol ids accepted in frozen evidence: the protocol's own plus any inherited v1 id."""
    ids = {protocol["protocol_id"]}
    if protocol.get("extends"):
        ids.add(protocol["extends"])
    return ids

VALIDATE_SCHEMA = "expanded_transfer_validate_v1"
SUBSETS_SCHEMA = "expanded_transfer_subsets_v1"
FREEZE_SCHEMA = "expanded_transfer_freeze_v1"
LEAKAGE_SCHEMA = "expanded_transfer_leakage_v1"
AUDIT_FREEZE_SCHEMA = "expanded_transfer_audit_freeze_v1"
PROBE_SCHEMA = "expanded_transfer_probe_v1"
AUDIT_PROBE_SCHEMA = "expanded_transfer_audit_probe_v1"
ADMISSION_SCHEMA = "expanded_transfer_admission_v1"
RUN_CELL_SCHEMA = "expanded_transfer_run_cell_v1"
RUN_JOURNAL_SCHEMA = "expanded_transfer_run_journal_v1"
WORKER_RESULT_SCHEMA = "expanded_transfer_run_worker_v1"
AUDIT_RUN_SCHEMA = "expanded_transfer_audit_run_worker_v1"
SCORES_SCHEMA = "expanded_transfer_scores_v1"
PREDICTIONS_SCHEMA = "expanded_transfer_predictions_v1"
AUDIT_SCORE_SCHEMA = "expanded_transfer_audit_score_v1"
FINAL_SCHEMA = "expanded_transfer_final_report_v1"
AUDIT_FINAL_SCHEMA = "expanded_transfer_audit_final_v1"
ANALYSIS_SCHEMA = "expanded_transfer_analysis_v1"
PUBLISH_SCHEMA = "expanded_transfer_publish_v1"

FOLIO_SYSTEM = "You are a careful logical reasoner."
FOLIO_USER_TEMPLATE = (
    "Premises:\n{premises}\n\nConclusion: {conclusion}\n\nBased solely on the premises, is the "
    "conclusion True, False, or Uncertain? Answer with exactly one word: True, False, or Uncertain."
)
GSM8K_SYSTEM = "You are a careful mathematical reasoner."
GSM8K_USER_TEMPLATE = (
    "Solve the following grade-school math word problem. Show your reasoning briefly, then give the "
    "final answer on a new line in the form '#### <number>'.\n\nProblem: {question}"
)
HUMANEVAL_SYSTEM = "You are an expert Python programmer."
HUMANEVAL_USER_TEMPLATE = (
    "Complete the following Python function. Respond with the complete function definition only, "
    "without explanations, examples, or tests.\n\n```python\n{prompt}```"
)

FOLIO_LABELS = ("True", "Uncertain", "False")
FOLIO_PREDICTION_RE = re.compile(r"\b(True|False|Uncertain)\b", re.IGNORECASE)
GSM8K_NUMBER_RE = re.compile(r"-?\$?-?\d[\d,]*(?:\.\d+)?")
HUMANEVAL_FENCED_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
DOWNLOAD_URLS = {
    "folio": "https://raw.githubusercontent.com/Yale-LILY/FOLIO/{commit}/{path}",
    "gsm8k": "https://huggingface.co/datasets/openai/gsm8k/resolve/{revision}/{file}",
    "humaneval": "https://huggingface.co/datasets/openai/openai_humaneval/resolve/{revision}/{file}",
}
DATA_FILES = {
    "folio": "folio-validation.jsonl",
    "gsm8k": "gsm8k-test-00000-of-00001.parquet",
    "humaneval": "openai_humaneval-test-00000-of-00001.parquet",
}

SOCKET_BLOCK_PRELUDE = (
    "import socket\n"
    "\n"
    "def _transfer_blocked_socket(*args, **kwargs):\n"
    "    raise RuntimeError('network access is disabled by the transfer sandbox')\n"
    "\n"
    "socket.socket = _transfer_blocked_socket\n"
)


# ---------------------------------------------------------------------------
# Frozen prompt rendering and policy message builders (matched-prompt contract)
# ---------------------------------------------------------------------------


def _require_benchmark(model_input: Mapping[str, Any], benchmark: str) -> None:
    if model_input.get("benchmark") != benchmark:
        raise ValueError(f"model input is not a frozen {benchmark} prompt")


def folio_training_messages(model_input: Mapping[str, Any]) -> list[dict[str, str]]:
    _require_benchmark(model_input, "folio")
    premises = "\n".join(model_input["premises"])
    user = FOLIO_USER_TEMPLATE.format(premises=premises, conclusion=model_input["conclusion"])
    return [{"role": "system", "content": FOLIO_SYSTEM}, {"role": "user", "content": user}]


def gsm8k_training_messages(model_input: Mapping[str, Any]) -> list[dict[str, str]]:
    _require_benchmark(model_input, "gsm8k")
    user = GSM8K_USER_TEMPLATE.format(question=model_input["question"])
    return [{"role": "system", "content": GSM8K_SYSTEM}, {"role": "user", "content": user}]


def humaneval_training_messages(model_input: Mapping[str, Any]) -> list[dict[str, str]]:
    _require_benchmark(model_input, "humaneval")
    user = HUMANEVAL_USER_TEMPLATE.format(prompt=model_input["prompt"])
    return [{"role": "system", "content": HUMANEVAL_SYSTEM}, {"role": "user", "content": user}]


def _as_policy_messages(training_messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {"role": message["role"], "content": [{"type": "text", "text": message["content"]}]}
        for message in training_messages
    ]


def folio_policy_messages(model_input: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _as_policy_messages(folio_training_messages(model_input))


def gsm8k_policy_messages(model_input: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _as_policy_messages(gsm8k_training_messages(model_input))


def humaneval_policy_messages(model_input: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _as_policy_messages(humaneval_training_messages(model_input))


TRAINING_BUILDERS = {
    "folio": folio_training_messages,
    "gsm8k": gsm8k_training_messages,
    "humaneval": humaneval_training_messages,
}
POLICY_BUILDERS = {
    "folio": folio_policy_messages,
    "gsm8k": gsm8k_policy_messages,
    "humaneval": humaneval_policy_messages,
}


def rendered_prompt(benchmark: str, model_input: Mapping[str, Any]) -> dict[str, str]:
    messages = TRAINING_BUILDERS[benchmark](model_input)
    return {"system": messages[0]["content"], "user": messages[1]["content"]}


# ---------------------------------------------------------------------------
# Subset derivation (deterministic, outcome-blind, no RNG)
# ---------------------------------------------------------------------------


def hamilton_apportionment(stratum_sizes: Mapping[str, int], seats: int) -> dict[str, int]:
    """Largest-remainder apportionment; ties break on the stratum key for determinism."""
    if seats < 0 or any(size <= 0 for size in stratum_sizes.values()):
        raise ValueError("apportionment requires non-negative seats and non-empty strata")
    total = sum(stratum_sizes.values())
    quotas = {key: size * seats / total for key, size in stratum_sizes.items()}
    assigned = {key: math.floor(quota) for key, quota in quotas.items()}
    remaining = seats - sum(assigned.values())
    by_remainder = sorted(quotas, key=lambda key: (-(quotas[key] - assigned[key]), key))
    for key in by_remainder[:remaining]:
        assigned[key] += 1
    return assigned


def folio_subset_indices(labels: Sequence[str], subset_size: int) -> tuple[list[int], dict[str, int]]:
    """Label-stratified Hamilton apportionment; first-k per stratum in original file order."""
    stratum_sizes = {label: sum(1 for value in labels if value == label) for label in FOLIO_LABELS}
    if sum(stratum_sizes.values()) != len(labels) or set(labels) - set(FOLIO_LABELS):
        raise ValueError("folio labels outside the frozen label set")
    if len(labels) <= subset_size:
        return list(range(len(labels))), stratum_sizes
    seats = hamilton_apportionment(stratum_sizes, subset_size)
    selected: list[int] = []
    for label in FOLIO_LABELS:
        members = [index for index, value in enumerate(labels) if value == label]
        selected.extend(members[: seats[label]])
    return sorted(selected), seats


def gsm8k_step_count(answer: str) -> int:
    """Reasoning-step proxy: calculator annotations '<<'; fallback non-empty lines before '####'."""
    annotations = answer.count("<<")
    if annotations:
        return annotations
    body = answer.split("####", 1)[0]
    return sum(1 for line in body.splitlines() if line.strip())


def quartile_strata(step_counts: Sequence[int]) -> list[list[int]]:
    """Equal-frequency quartiles: sort by (step count, original index), split ranks into quarters."""
    order = sorted(range(len(step_counts)), key=lambda index: (step_counts[index], index))
    strata: list[list[int]] = [[], [], [], []]
    for rank, index in enumerate(order):
        strata[min(3, (4 * rank) // len(step_counts))].append(index)
    for stratum in strata:
        stratum.sort()
    return strata


def gsm8k_subset_indices(step_counts: Sequence[int], subset_size: int) -> tuple[list[int], dict[str, int]]:
    if len(step_counts) <= subset_size:
        return list(range(len(step_counts))), {f"q{quarter}": 0 for quarter in range(4)}
    strata = quartile_strata(step_counts)
    seats = hamilton_apportionment({f"q{quarter}": len(strata[quarter]) for quarter in range(4)}, subset_size)
    selected: list[int] = []
    for quarter in range(4):
        selected.extend(strata[quarter][: seats[f"q{quarter}"]])
    return sorted(selected), seats


def l1_order(l0_order: Sequence[str]) -> list[str]:
    """Frozen reduced panel: even-numbered positions of the frozen L0 ordered subset."""
    return [example_id for position, example_id in enumerate(l0_order) if position % 2 == 0]


# ---------------------------------------------------------------------------
# Parsing and scoring rules (frozen per benchmark)
# ---------------------------------------------------------------------------


def parse_folio_prediction(raw_output: str) -> tuple[str | None, bool]:
    """First case-insensitive whole-word True|False|Uncertain; else malformed."""
    match = FOLIO_PREDICTION_RE.search(raw_output)
    if match is None:
        return None, True
    return match.group(1).capitalize(), False


def _normalize_number(text: str) -> str:
    return text.replace(",", "").replace("$", "").rstrip(".").strip()


def parse_gsm8k_prediction(raw_output: str) -> tuple[str | None, bool]:
    """Official-style: first number after the last '####'; fallback last number anywhere."""
    if "####" in raw_output:
        tail = raw_output.rsplit("####", 1)[1]
        match = GSM8K_NUMBER_RE.search(tail)
        if match is not None:
            return _normalize_number(match.group(0)), False
    matches = GSM8K_NUMBER_RE.findall(raw_output)
    if not matches:
        return None, True
    return _normalize_number(matches[-1]), False


def parse_gsm8k_gold(answer: str) -> str:
    if "####" not in answer:
        raise ValueError("gsm8k gold answer lacks the '####' marker")
    tail = answer.rsplit("####", 1)[1]
    match = GSM8K_NUMBER_RE.search(tail)
    if match is None:
        raise ValueError("gsm8k gold answer lacks a final number")
    return _normalize_number(match.group(0))


def gsm8k_correct(prediction: str, gold: str) -> bool:
    if prediction == gold:
        return True
    try:
        return math.isclose(float(prediction), float(gold), abs_tol=1e-6)
    except ValueError:
        return False


def extract_humaneval_code(raw_output: str) -> str:
    """First fenced ```python block; else the raw output; strip leading/trailing blank lines."""
    match = HUMANEVAL_FENCED_RE.search(raw_output)
    text = match.group(1) if match is not None else raw_output
    return text.strip("\n").strip()


def humaneval_defines_entry_point(code: str, entry_point: str) -> bool:
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == entry_point
        for node in tree.body
    )


def build_humaneval_program(code: str, test: str, entry_point: str) -> str:
    """Socket-blocking prelude + extracted code + official test + check(entry_point)."""
    return f"{SOCKET_BLOCK_PRELUDE}\n{code}\n\n{test}\n\ncheck({entry_point})\n"


def probe_unshare_network() -> bool:
    """True only when 'unshare -n' actually works on this host."""
    if shutil.which("unshare") is None:
        return False
    try:
        subprocess.run(
            ["unshare", "-n", "true"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return False
    return True


def execute_humaneval_program(
    program: str,
    *,
    wall_timeout_seconds: int = 15,
    rlimit_cpu_seconds: int = 10,
    rlimit_as_bytes: int = 4_294_967_296,
    rlimit_nofile: int = 256,
    use_unshare: bool = False,
) -> dict[str, Any]:
    """Run one scored program under the frozen sandbox limits; never raises on task failure."""
    import resource

    def limits() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (rlimit_cpu_seconds, rlimit_cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (rlimit_as_bytes, rlimit_as_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (rlimit_nofile, rlimit_nofile))

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="transfer-humaneval-") as sandbox:
        Path(sandbox, "program.py").write_text(program)
        command = [sys.executable, "-I", "program.py"]
        if use_unshare:
            command = ["unshare", "-n", *command]
        env = {
            "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
            "HOME": sandbox,
            "CUDA_VISIBLE_DEVICES": "",
        }
        try:
            completed = subprocess.run(
                command,
                cwd=sandbox,
                env=env,
                preexec_fn=limits,
                capture_output=True,
                text=True,
                timeout=wall_timeout_seconds,
            )
        except subprocess.TimeoutExpired as expired:
            return {
                "category": "timeout",
                "wall_seconds": time.monotonic() - started,
                "returncode": None,
                "stderr_tail": (expired.stderr or "")[-2000:] if isinstance(expired.stderr, str) else "",
            }
    wall = time.monotonic() - started
    stderr_tail = completed.stderr[-2000:]
    if completed.returncode == 0:
        category = "passed"
    elif "AssertionError" in stderr_tail:
        category = "wrong_answer"
    else:
        category = "runtime_error"
    return {"category": category, "wall_seconds": wall, "returncode": completed.returncode, "stderr_tail": stderr_tail}


# ---------------------------------------------------------------------------
# Leakage check: normalized-token 8-gram containment vs the SFT corpus
# ---------------------------------------------------------------------------


def normalized_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def token_ngrams(tokens: Sequence[str], n: int = LEAKAGE_NGRAM) -> set[tuple[str, ...]]:
    return {tuple(tokens[offset : offset + n]) for offset in range(len(tokens) - n + 1)}


def leakage_check(
    root: Path,
    corpus_report: str,
    benchmark_inputs: Mapping[str, str],
    *,
    n: int = LEAKAGE_NGRAM,
    progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Report every normalized-token 8-gram shared between a frozen benchmark input and the corpus."""
    index: dict[tuple[str, ...], list[str]] = {}
    for example_id, text in benchmark_inputs.items():
        for ngram in token_ngrams(normalized_tokens(text), n):
            index.setdefault(ngram, []).append(example_id)
    report = read_json(root / corpus_report)
    matches: dict[str, set[str]] = {}
    records_scanned = 0
    tasks = list(report["results"])
    for task_index, result in enumerate(tasks):
        path = root / result["path"]
        if not path.is_file():
            raise ValueError(f"transfer leakage corpus record file is missing: {result['path']}")
        for record in read_json_lines(path):
            records_scanned += 1
            text = canonical(record)
            for ngram in token_ngrams(normalized_tokens(text), n):
                for example_id in index.get(ngram, ()):
                    matches.setdefault(example_id, set()).add(" ".join(ngram))
        if progress is not None and (task_index % 25 == 0 or task_index == len(tasks) - 1):
            progress(completed=task_index + 1, total=len(tasks), stage="leakage")
    return {
        "schema_version": LEAKAGE_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "corpus_report": corpus_report,
        "ngram": n,
        "normalization": "lowercase; [a-z0-9]+ tokens",
        "corpus_text": "canonical JSON of every corpus record in release-001 report results",
        "tasks_scanned": len(tasks),
        "records_scanned": records_scanned,
        "benchmark_inputs": len(benchmark_inputs),
        "items_with_shared_ngrams": len(matches),
        "matches": {example_id: sorted(values) for example_id, values in sorted(matches.items())},
    }


def read_json_lines(path: Path):
    with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


# ---------------------------------------------------------------------------
# Protocol validation
# ---------------------------------------------------------------------------


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def _prompt_fields(template: str) -> set[str]:
    return {field for _literal, field, _spec, _conv in string.Formatter().parse(template) if field}


def validate_protocol(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Hard-fail unless the frozen transfer protocol is internally consistent with reality."""
    if protocol.get("extends"):
        return _validate_extension_protocol(root, protocol)
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if not condition:
            failures.append(f"{name}: {detail}")

    schedule = read_json(root / SCHEDULE_DOC)
    check("schema", protocol.get("schema") == PROTOCOL_SCHEMA, str(protocol.get("schema")))
    check("protocol_id", protocol.get("protocol_id") == PROTOCOL_ID, str(protocol.get("protocol_id")))
    check("program", protocol.get("program") == "expanded-nine-day-v1")
    check("issues", protocol.get("issues") == [104, 105, 106, 107], str(protocol.get("issues")))
    check("branch", protocol.get("branch") == BRANCH)
    check("frozen", protocol.get("frozen_before_any_model_output") is True)
    check("allocation", protocol.get("allocation_gpu_hours") == BRANCH_GPU_HOURS)
    check(
        "allocation_matches_schedule",
        schedule["allocations_gpu_hours"].get(BRANCH) == protocol.get("allocation_gpu_hours"),
    )

    cells = protocol.get("cells", {})
    check("cells_order", sorted(cells) == sorted(CELL_ORDER), str(sorted(cells)))
    check("base_cell", cells.get("base", {}).get("adapter_id") is None)
    adapter_paths: dict[str, Path] = {}
    for cell in ADAPTED_CELLS:
        checkpoint = root / cells.get(cell, {}).get("checkpoint", "")
        adapter_paths[cell] = checkpoint
        check(
            f"adapter_{cell}",
            checkpoint.is_dir()
            and (checkpoint / "adapter_config.json").is_file()
            and (checkpoint / "adapter_model.safetensors").is_file(),
            str(checkpoint),
        )
        check(f"adapter_{cell}_id", cells.get(cell, {}).get("adapter_id") == cell)

    base_model = protocol.get("base_model", {})
    check("base_model_id", base_model.get("model_id") == "Qwen/Qwen3-VL-8B-Instruct")
    check("base_model_revision", base_model.get("revision") == "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b")
    snapshot = (
        root
        / ".cache/hf/hub/models--Qwen--Qwen3-VL-8B-Instruct/snapshots"
        / str(base_model.get("revision"))
    )
    check("base_model_cached", (snapshot / "config.json").is_file(), str(snapshot))

    benchmarks = protocol.get("benchmarks", {})
    check("benchmarks", sorted(benchmarks) == sorted(BENCHMARK_ORDER), str(sorted(benchmarks)))
    folio = benchmarks.get("folio", {})
    folio_seats = hamilton_apportionment({"True": 72, "Uncertain": 69, "False": 63}, 200)
    check(
        "folio_subset_arithmetic",
        folio.get("official_source", {}).get("examples") == 204
        and folio.get("subset_size") == 200
        and folio_seats == {"True": 70, "Uncertain": 68, "False": 62}
        and folio.get("label_set") == list(FOLIO_LABELS),
        str(folio_seats),
    )
    check(
        "folio_prompt",
        folio.get("prompt", {}).get("system") == FOLIO_SYSTEM
        and folio.get("prompt", {}).get("user_template") == FOLIO_USER_TEMPLATE
        and folio.get("prompt", {}).get("premises_join") == "\n",
    )
    check(
        "folio_parsing",
        folio.get("parsing", {}).get("regex") == r"\b(True|False|Uncertain)\b"
        and folio.get("max_new_tokens") == 64,
    )
    gsm8k = benchmarks.get("gsm8k", {})
    check(
        "gsm8k_subset_arithmetic",
        gsm8k.get("official_source", {}).get("examples") == 1319 and gsm8k.get("subset_size") == 200,
    )
    check(
        "gsm8k_prompt",
        gsm8k.get("prompt", {}).get("system") == GSM8K_SYSTEM
        and gsm8k.get("prompt", {}).get("user_template") == GSM8K_USER_TEMPLATE
        and gsm8k.get("max_new_tokens") == 512,
    )
    humaneval = benchmarks.get("humaneval", {})
    check(
        "humaneval_subset_arithmetic",
        humaneval.get("official_source", {}).get("examples") == 164 and humaneval.get("subset_size") == 164,
    )
    check(
        "humaneval_prompt",
        humaneval.get("prompt", {}).get("system") == HUMANEVAL_SYSTEM
        and humaneval.get("prompt", {}).get("user_template") == HUMANEVAL_USER_TEMPLATE
        and humaneval.get("max_new_tokens") == 768,
    )
    sandbox = humaneval.get("sandbox", {})
    check(
        "humaneval_sandbox",
        sandbox.get("wall_timeout_seconds_per_task") == 15
        and sandbox.get("rlimit_cpu_seconds") == 10
        and sandbox.get("rlimit_as_bytes") == 4_294_967_296
        and sandbox.get("rlimit_nofile") == 256,
    )
    for name, spec in benchmarks.items():
        template = spec.get("prompt", {}).get("user_template", "")
        expected_fields = {"folio": {"premises", "conclusion"}, "gsm8k": {"question"}, "humaneval": {"prompt"}}[name]
        check(f"{name}_template_fields", _prompt_fields(template) == expected_fields, str(_prompt_fields(template)))
    check(
        "l1_arithmetic",
        {name: len(l1_order([str(i) for i in range(L0_SIZES[name])])) for name in BENCHMARK_ORDER} == L1_SIZES,
    )
    check("max_context", MAX_CONTEXT_TOKENS > max(64, 512, 768))

    decoding = protocol.get("decoding", {})
    check(
        "decoding",
        decoding.get("do_sample") is False and decoding.get("seed") == SEED and decoding.get("dtype") == "float32",
    )
    topology = protocol.get("execution_topology", {})
    workers = topology.get("workers", {})
    check(
        "topology",
        workers.get("transfer-run-0", {}).get("benchmarks") == ["gsm8k"]
        and workers.get("transfer-run-0", {}).get("gpu") == 0
        and workers.get("transfer-run-1", {}).get("benchmarks") == ["folio", "humaneval"]
        and workers.get("transfer-run-1", {}).get("gpu") == 1
        and topology.get("cell_order_per_benchmark") == list(CELL_ORDER),
    )
    check(
        "port_pool",
        tuple(topology.get("master_port_pool", ())) == PORT_POOL
        and tuple(schedule.get("master_port_pool", ())) == PORT_POOL,
    )
    check("gpu_cutoff", schedule.get("gpu_cutoff_utc") == GPU_CUTOFF_UTC)

    gate = protocol.get("resource_gate", {})
    check("safety_factor", gate.get("safety_factor") == SAFETY_FACTOR)
    ledger_path = root / LEDGER_PATH
    check("ledger_exists", ledger_path.is_file(), str(ledger_path))
    if ledger_path.is_file():
        ledger = read_json(ledger_path)
        check(
            "ledger_branch",
            ledger.get("allocations_gpu_hours", {}).get(BRANCH) == BRANCH_GPU_HOURS
            and ledger.get("schedule") == schedule,
        )
    corpus = protocol.get("leakage_prevention", {})
    check("leakage_corpus", (root / CORPUS_REPORT).is_file() and "issue74-matched-32k-v1" in str(corpus))
    check("output_root", protocol.get("evidence", {}).get("output_root") == OUTPUT_ROOT)

    if failures:
        raise ValueError("transfer protocol validation failed: " + "; ".join(failures))
    return {
        "schema_version": VALIDATE_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "adapter_paths": {cell: str(path.relative_to(root)) for cell, path in adapter_paths.items()},
        "folio_strata_seats": folio_seats,
        "l0_sizes": dict(L0_SIZES),
        "l1_sizes": dict(L1_SIZES),
        "worker_benchmarks": {str(worker): list(bench) for worker, bench in WORKER_BENCHMARKS.items()},
    }


def _validate_extension_protocol(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an extension protocol: adapted cells only, inherited byte-identical v1 subsets."""
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if not condition:
            failures.append(f"{name}: {detail}")

    schedule = read_json(root / SCHEDULE_DOC)
    check("schema", protocol.get("schema") == PROTOCOL_SCHEMA, str(protocol.get("schema")))
    check("extends", protocol.get("extends") == PROTOCOL_ID, str(protocol.get("extends")))
    check(
        "protocol_id",
        bool(protocol.get("protocol_id")) and protocol.get("protocol_id") != PROTOCOL_ID,
        str(protocol.get("protocol_id")),
    )
    check("program", protocol.get("program") == "expanded-nine-day-v1")
    check("issues", protocol.get("issues") == [104, 105, 106, 107], str(protocol.get("issues")))
    check("branch", protocol.get("branch") == BRANCH)
    check("frozen", protocol.get("frozen_before_any_model_output") is True)
    check("allocation_matches_schedule", schedule["allocations_gpu_hours"].get(BRANCH) == BRANCH_GPU_HOURS)

    cells = protocol.get("cells", {})
    order = cell_order(protocol)
    check("cells_nonempty", bool(cells))
    check("cells_order", sorted(cells) == sorted(order), str(sorted(cells)))
    check("no_base_rerun", "base" not in cells)
    adapter_paths: dict[str, Path] = {}
    for cell in order:
        checkpoint = root / cells.get(cell, {}).get("checkpoint", "")
        adapter_paths[cell] = checkpoint
        check(
            f"adapter_{cell}",
            checkpoint.is_dir()
            and (checkpoint / "adapter_config.json").is_file()
            and (checkpoint / "adapter_model.safetensors").is_file(),
            str(checkpoint),
        )
        check(f"adapter_{cell}_id", cells.get(cell, {}).get("adapter_id") == cell)

    base_model = protocol.get("base_model", {})
    check("base_model_id", base_model.get("model_id") == "Qwen/Qwen3-VL-8B-Instruct")
    check("base_model_revision", base_model.get("revision") == "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b")
    snapshot = (
        root / ".cache/hf/hub/models--Qwen--Qwen3-VL-8B-Instruct/snapshots" / str(base_model.get("revision"))
    )
    check("base_model_cached", (snapshot / "config.json").is_file(), str(snapshot))

    benchmarks = protocol.get("benchmarks", {})
    check("benchmarks_inherit", benchmarks.get("inherit") == PROTOCOL_ID, str(benchmarks.get("inherit")))
    check("l0_sizes", l0_sizes(protocol) == L0_SIZES, str(l0_sizes(protocol)))
    check("l1_sizes", l1_sizes(protocol) == L1_SIZES, str(l1_sizes(protocol)))
    check(
        "l1_arithmetic",
        {name: len(l1_order([str(i) for i in range(L0_SIZES[name])])) for name in BENCHMARK_ORDER} == L1_SIZES,
    )
    check("max_context", MAX_CONTEXT_TOKENS > max(64, 512, 768))

    decoding = protocol.get("decoding", {})
    check(
        "decoding",
        decoding.get("inherit") == PROTOCOL_ID
        and decoding.get("do_sample") is False
        and decoding.get("seed") == SEED
        and decoding.get("dtype") == "float32",
    )
    topology = protocol.get("execution_topology", {})
    check(
        "topology",
        worker_benchmarks(protocol) == WORKER_BENCHMARKS
        and worker_gpus(protocol) == WORKER_GPUS
        and tuple(topology.get("cell_order_per_benchmark", ())) == order,
        str(topology.get("workers")),
    )
    check(
        "port_pool",
        tuple(topology.get("master_port_pool", ())) == PORT_POOL
        and tuple(schedule.get("master_port_pool", ())) == PORT_POOL,
    )
    check("gpu_cutoff", schedule.get("gpu_cutoff_utc") == GPU_CUTOFF_UTC)

    gate = protocol.get("resource_gate", {})
    check("safety_factor", gate.get("safety_factor") == SAFETY_FACTOR)
    ledger_path = root / LEDGER_PATH
    check("ledger_exists", ledger_path.is_file(), str(ledger_path))
    if ledger_path.is_file():
        ledger = read_json(ledger_path)
        check(
            "ledger_branch",
            ledger.get("allocations_gpu_hours", {}).get(BRANCH) == BRANCH_GPU_HOURS
            and ledger.get("schedule") == schedule,
        )
    check("leakage_corpus", (root / CORPUS_REPORT).is_file())
    check(
        "output_root",
        output_root(protocol) != OUTPUT_ROOT and output_root(protocol).startswith("outputs/expanded-study/v1/"),
        output_root(protocol),
    )
    reference = subsets_reference(protocol)
    check("subsets_reference", reference is not None)
    if reference is not None:
        source = root / reference.get("path", "")
        check("subsets_reference_exists", source.is_file(), str(source))
        if source.is_file():
            check(
                "subsets_reference_sha256",
                _sha256_path(source) == reference.get("sha256"),
                reference.get("path", ""),
            )
        v1_freeze = root / OUTPUT_ROOT / "freeze.json"
        check(
            "v1_freeze_pass",
            v1_freeze.is_file() and read_json(v1_freeze).get("outcome") == "PASS",
            str(v1_freeze),
        )

    if failures:
        raise ValueError("transfer extension protocol validation failed: " + "; ".join(failures))
    return {
        "schema_version": VALIDATE_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "extends": protocol["extends"],
        "adapter_paths": {cell: str(path.relative_to(root)) for cell, path in adapter_paths.items()},
        "l0_sizes": l0_sizes(protocol),
        "l1_sizes": l1_sizes(protocol),
        "worker_benchmarks": {
            str(worker): list(benchmarks) for worker, benchmarks in worker_benchmarks(protocol).items()
        },
        "subsets_reference": reference,
    }


# ---------------------------------------------------------------------------
# Freeze: download, hash-pin, derive subsets, render prompts, count tokens
# ---------------------------------------------------------------------------


def _download(root: Path, protocol: Mapping[str, Any], benchmark: str) -> dict[str, Any]:
    source = protocol["benchmarks"][benchmark]["official_source"]
    url = DOWNLOAD_URLS[benchmark].format(**source)
    expected = source["sha256"]
    destination = root / OUTPUT_ROOT / "data" / DATA_FILES[benchmark]
    if destination.is_file():
        actual = _sha256_path(destination)
        if actual != expected:
            raise RuntimeError(f"transfer {benchmark} file on disk differs from the frozen sha256")
        return {"url": url, "sha256": actual, "path": str(destination.relative_to(root)), "downloaded": False}
    destination.parent.mkdir(parents=True, exist_ok=True)
    import urllib.request

    temporary = destination.with_suffix(destination.suffix + ".tmp")
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=300) as response, temporary.open("wb") as stream:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                digest.update(block)
                stream.write(block)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != expected:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"transfer {benchmark} download sha256 differs from the frozen pin")
    temporary.replace(destination)
    return {"url": url, "sha256": expected, "path": str(destination.relative_to(root)), "downloaded": True}


def _write_idempotent(path: Path, value: Any) -> bool:
    """Write deterministic JSON; a re-run must reproduce byte-identical content or fail."""
    payload = (json.dumps(value, indent=2) + "\n").encode()
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"transfer freeze is not byte-reproducible: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return True


def _load_benchmark_rows(root: Path, benchmark: str) -> list[dict[str, Any]]:
    path = root / OUTPUT_ROOT / "data" / DATA_FILES[benchmark]
    if benchmark == "folio":
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    import pandas as pd

    frame = pd.read_parquet(path)
    return frame.to_dict(orient="records")


def _folio_entries(rows: Sequence[Mapping[str, Any]], subset_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    labels = [str(row["label"]) for row in rows]
    selected, seats = folio_subset_indices(labels, subset_size)
    entries = []
    for index in selected:
        row = rows[index]
        model_input = {
            "benchmark": "folio",
            "example_id": f"folio-{index}",
            "premises": list(row["premises"]),
            "conclusion": str(row["conclusion"]),
        }
        entries.append(
            {
                "example_id": f"folio-{index}",
                "source_index": index,
                "stratum": str(row["label"]),
                "model_input": model_input,
                "gold": {"label": str(row["label"])},
                "leakage_text": "\n".join(row["premises"]) + "\n" + str(row["conclusion"]),
            }
        )
    return entries, {"strata_sizes": {label: labels.count(label) for label in FOLIO_LABELS}, "strata_seats": seats}


def _gsm8k_entries(rows: Sequence[Mapping[str, Any]], subset_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    step_counts = [gsm8k_step_count(str(row["answer"])) for row in rows]
    selected, seats = gsm8k_subset_indices(step_counts, subset_size)
    strata = quartile_strata(step_counts)
    quartile_of = {index: quarter for quarter in range(4) for index in strata[quarter]}
    entries = []
    for index in selected:
        row = rows[index]
        answer = str(row["answer"])
        model_input = {"benchmark": "gsm8k", "example_id": f"gsm8k-{index}", "question": str(row["question"])}
        entries.append(
            {
                "example_id": f"gsm8k-{index}",
                "source_index": index,
                "stratum": f"q{quartile_of[index]}",
                "step_count": step_counts[index],
                "model_input": model_input,
                "gold": {"answer": answer, "final": parse_gsm8k_gold(answer)},
                "leakage_text": str(row["question"]),
            }
        )
    boundaries = {
        f"q{quarter}": {
            "min_step_count": min(step_counts[i] for i in s),
            "max_step_count": max(step_counts[i] for i in s),
            "size": len(s),
        }
        for quarter, s in enumerate(strata)
    }
    return entries, {"strata_boundaries": boundaries, "strata_seats": seats}


def _humaneval_entries(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries = []
    for index, row in enumerate(rows):
        task_id = str(row["task_id"])
        if task_id != f"HumanEval/{index}":
            raise ValueError("humaneval task order differs from HumanEval/0..163 file order")
        model_input = {"benchmark": "humaneval", "example_id": task_id, "prompt": str(row["prompt"])}
        entries.append(
            {
                "example_id": task_id,
                "source_index": index,
                "stratum": "all",
                "model_input": model_input,
                "gold": {"test": str(row["test"]), "entry_point": str(row["entry_point"])},
                "leakage_text": str(row["prompt"]),
            }
        )
    return entries, {"strata_sizes": {"all": len(entries)}}


def frozen_processor(root: Path, protocol: Mapping[str, Any]):
    os.environ.setdefault("HF_HOME", str(root / ".cache" / "hf"))
    from transformers import AutoProcessor

    return AutoProcessor.from_pretrained(
        protocol["base_model"]["model_id"],
        revision=protocol["base_model"]["revision"],
        local_files_only=True,
    )


def count_input_tokens(processor: Any, benchmark: str, model_input: Mapping[str, Any]) -> int:
    return len(
        processor.tokenizer.apply_chat_template(
            TRAINING_BUILDERS[benchmark](model_input),
            tokenize=True,
            add_generation_prompt=True,
        )
    )


def freeze_stage(
    root: Path,
    protocol: Mapping[str, Any],
    *,
    progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Download, hash-pin and freeze the three benchmark subsets before any model output."""
    reference = subsets_reference(protocol)
    if protocol.get("extends"):
        if reference is None:
            raise ValueError("transfer extension protocol lacks a subsets reference")
        return _freeze_extension_stage(root, protocol, reference, progress=progress)
    started = time.monotonic()
    checks = validate_protocol(root, protocol)
    downloads = {benchmark: _download(root, protocol, benchmark) for benchmark in BENCHMARK_ORDER}

    benchmarks: dict[str, Any] = {}
    leakage_inputs: dict[str, str] = {}
    processor = None
    total_steps = 6
    for step, benchmark in enumerate(BENCHMARK_ORDER, start=1):
        rows = _load_benchmark_rows(root, benchmark)
        expected_total = protocol["benchmarks"][benchmark]["official_source"]["examples"]
        if len(rows) != expected_total:
            raise ValueError(f"transfer {benchmark} example count differs from the frozen source pin")
        if benchmark == "folio":
            entries, strata = _folio_entries(rows, L0_SIZES["folio"])
        elif benchmark == "gsm8k":
            entries, strata = _gsm8k_entries(rows, L0_SIZES["gsm8k"])
        else:
            entries, strata = _humaneval_entries(rows)
        if processor is None:
            processor = frozen_processor(root, protocol)
        for entry in entries:
            prompt = rendered_prompt(benchmark, entry["model_input"])
            entry["system"] = prompt["system"]
            entry["user"] = prompt["user"]
            entry["input_tokens"] = count_input_tokens(processor, benchmark, entry["model_input"])
            leakage_inputs[entry["example_id"]] = entry.pop("leakage_text")
        l0 = [entry["example_id"] for entry in entries]
        l1 = l1_order(l0)
        if len(l0) != L0_SIZES[benchmark] or len(l1) != L1_SIZES[benchmark]:
            raise ValueError(f"transfer {benchmark} subset sizes differ from the frozen panel")
        benchmarks[benchmark] = {
            "source": dict(protocol["benchmarks"][benchmark]["official_source"]),
            "sha256": downloads[benchmark]["sha256"],
            "examples_total": len(rows),
            "max_new_tokens": protocol["benchmarks"][benchmark]["max_new_tokens"],
            **strata,
            "l0_order": l0,
            "l1_order": l1,
            "examples": {entry["example_id"]: entry for entry in entries},
        }
        if progress is not None:
            progress(completed=step, total=total_steps, stage=f"freeze_{benchmark}")

    subsets = {
        "schema_version": SUBSETS_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "frozen_at_utc": protocol["frozen_at_utc"],
        "benchmarks": benchmarks,
    }
    output = root / OUTPUT_ROOT
    _write_idempotent(output / "subsets.json", subsets)
    if progress is not None:
        progress(completed=4, total=total_steps, stage="subsets")

    leakage = leakage_check(root, CORPUS_REPORT, leakage_inputs)
    write_json(output / "leakage.json", leakage)
    if progress is not None:
        progress(completed=5, total=total_steps, stage="leakage")

    sandbox_unshare = probe_unshare_network()
    freeze = {
        "schema_version": FREEZE_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "protocol_checks": checks,
        "downloads": downloads,
        "subsets": {
            benchmark: {
                "l0_size": len(block["l0_order"]),
                "l1_size": len(block["l1_order"]),
                "l0_order": block["l0_order"],
                "l1_order": block["l1_order"],
                "l0_order_sha256": _json_sha256(block["l0_order"]),
                "input_tokens": {
                    "min": min(entry["input_tokens"] for entry in block["examples"].values()),
                    "max": max(entry["input_tokens"] for entry in block["examples"].values()),
                },
                **{
                    key: block[key]
                    for key in ("strata_sizes", "strata_seats", "strata_boundaries")
                    if key in block
                },
            }
            for benchmark, block in benchmarks.items()
        },
        "leakage": {
            "records_scanned": leakage["records_scanned"],
            "benchmark_inputs": leakage["benchmark_inputs"],
            "items_with_shared_ngrams": leakage["items_with_shared_ngrams"],
            "report": "leakage.json",
        },
        "sandbox": {
            "unshare_network_available": sandbox_unshare,
            "decision": "unshare -n" if sandbox_unshare else "socket-blocking prelude only",
        },
        "elapsed_seconds": time.monotonic() - started,
        "frozen_at": time.time(),
    }
    write_json(output / "freeze.json", freeze)
    if progress is not None:
        progress(completed=6, total=total_steps, stage="freeze_evidence")
    return freeze


def _freeze_extension_stage(
    root: Path,
    protocol: Mapping[str, Any],
    reference: Mapping[str, str],
    *,
    progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Verify the pinned v1 subsets by sha256 and copy them byte-identically; never re-derive."""
    started = time.monotonic()
    checks = validate_protocol(root, protocol)
    source = root / reference["path"]
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != reference["sha256"]:
        raise RuntimeError(
            "transfer extension freeze refused: referenced subsets sha256 "
            f"{digest} differs from the pinned {reference['sha256']}"
        )
    subsets = json.loads(raw)
    if subsets.get("schema_version") != SUBSETS_SCHEMA or subsets.get("protocol_id") not in _protocol_ids(protocol):
        raise ValueError("transfer extension referenced subsets differ from the frozen v1 schema")
    output = root / output_root(protocol)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "subsets.json"
    if destination.exists() and destination.read_bytes() != raw:
        raise RuntimeError(f"transfer freeze is not byte-reproducible: {destination}")
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(destination)
    if progress is not None:
        progress(completed=1, total=3, stage="subsets_reference")

    v1_freeze = read_json(root / OUTPUT_ROOT / "freeze.json")
    if v1_freeze.get("outcome") != "PASS":
        raise ValueError("transfer extension requires a PASS v1 freeze")
    v1_leakage = root / OUTPUT_ROOT / "leakage.json"
    if not v1_leakage.is_file():
        raise ValueError("transfer extension requires the v1 leakage report")
    shutil.copyfile(v1_leakage, output / "leakage.json")
    if progress is not None:
        progress(completed=2, total=3, stage="leakage_reference")

    summary = {}
    for benchmark in BENCHMARK_ORDER:
        block = subsets["benchmarks"][benchmark]
        summary[benchmark] = {
            "l0_size": len(block["l0_order"]),
            "l1_size": len(block["l1_order"]),
            "l0_order": block["l0_order"],
            "l1_order": block["l1_order"],
            "l0_order_sha256": _json_sha256(block["l0_order"]),
            "input_tokens": {
                "min": min(entry["input_tokens"] for entry in block["examples"].values()),
                "max": max(entry["input_tokens"] for entry in block["examples"].values()),
            },
            **{key: block[key] for key in ("strata_sizes", "strata_seats", "strata_boundaries") if key in block},
        }
    sandbox_unshare = probe_unshare_network()
    freeze = {
        "schema_version": FREEZE_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "extends": protocol["extends"],
        "method": "referenced-v1: v1 frozen subsets verified by sha256 and copied byte-identically",
        "protocol_checks": checks,
        "subsets_reference": {
            "path": reference["path"],
            "sha256": reference["sha256"],
            "verified_sha256": "sha256:" + digest,
            "copied_bytes": len(raw),
            "byte_identical": True,
        },
        "subsets": summary,
        "leakage": {
            **v1_freeze.get("leakage", {}),
            "status": "inherited_from_v1",
            "source": str(v1_leakage.relative_to(root)),
        },
        "sandbox": {
            "unshare_network_available": sandbox_unshare,
            "decision": "unshare -n" if sandbox_unshare else "socket-blocking prelude only",
        },
        "elapsed_seconds": time.monotonic() - started,
        "frozen_at": time.time(),
    }
    write_json(output / "freeze.json", freeze)
    if progress is not None:
        progress(completed=3, total=3, stage="freeze_evidence")
    return freeze


# ---------------------------------------------------------------------------
# audit-freeze: independent re-download, re-hash, re-derive, byte-compare
# ---------------------------------------------------------------------------


def _audit_apportionment(stratum_sizes: Mapping[str, int], seats: int) -> dict[str, int]:
    """Independent largest-remainder implementation using exact fractions."""
    from fractions import Fraction

    total = sum(stratum_sizes.values())
    quotas = {key: Fraction(size * seats, total) for key, size in stratum_sizes.items()}
    assigned = {key: quota.numerator // quota.denominator for key, quota in quotas.items()}
    remaining = seats - sum(assigned.values())
    order = sorted(quotas, key=lambda key: (assigned[key] - quotas[key], key))
    for key in order[:remaining]:
        assigned[key] += 1
    return assigned


def _audit_folio_indices(labels: Sequence[str], subset_size: int) -> list[int]:
    seats = _audit_apportionment({label: labels.count(label) for label in FOLIO_LABELS}, subset_size)
    selected: list[int] = []
    for label in FOLIO_LABELS:
        taken = 0
        for index, value in enumerate(labels):
            if value == label and taken < seats[label]:
                selected.append(index)
                taken += 1
    return sorted(selected)


def _audit_gsm8k_indices(step_counts: Sequence[int], subset_size: int) -> list[int]:
    n = len(step_counts)
    order = sorted(range(n), key=lambda index: (step_counts[index], index))
    boundaries = [-((-quarter * n) // 4) for quarter in range(5)]
    strata = [sorted(order[boundaries[quarter] : boundaries[quarter + 1]]) for quarter in range(4)]
    seats = _audit_apportionment({f"q{quarter}": len(strata[quarter]) for quarter in range(4)}, subset_size)
    selected: list[int] = []
    for quarter in range(4):
        selected.extend(strata[quarter][: seats[f"q{quarter}"]])
    return sorted(selected)


def _audit_l1(l0: Sequence[str]) -> list[str]:
    return [example_id for index, example_id in enumerate(l0) if index % 2 == 0]


def audit_freeze_stage(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Re-download to a temp dir, re-hash, re-derive subsets independently, byte-compare."""
    reference = subsets_reference(protocol)
    if protocol.get("extends"):
        if reference is None:
            raise ValueError("transfer extension protocol lacks a subsets reference")
        return _audit_freeze_extension(root, protocol, reference)
    stored = read_json(root / OUTPUT_ROOT / "subsets.json")
    if stored.get("schema_version") != SUBSETS_SCHEMA or stored.get("protocol_id") != protocol["protocol_id"]:
        raise ValueError("transfer stored subsets differ from the frozen schema")
    import pandas as pd

    comparisons: dict[str, Any] = {"files": {}}
    rows_by_benchmark: dict[str, list[dict[str, Any]]] = {}
    with tempfile.TemporaryDirectory(prefix="transfer-audit-freeze-") as temporary:
        temp_root = Path(temporary)
        for benchmark in BENCHMARK_ORDER:
            source = protocol["benchmarks"][benchmark]["official_source"]
            url = DOWNLOAD_URLS[benchmark].format(**source)
            target = temp_root / DATA_FILES[benchmark]
            import urllib.request

            with urllib.request.urlopen(url, timeout=300) as response:
                target.write_bytes(response.read())
            retained = root / OUTPUT_ROOT / "data" / DATA_FILES[benchmark]
            comparisons["files"][benchmark] = {
                "redownload_sha256_matches": _sha256_path(target) == source["sha256"],
                "retained_sha256_matches": _sha256_path(retained) == source["sha256"],
            }
            if benchmark == "folio":
                rows_by_benchmark[benchmark] = [
                    json.loads(line) for line in target.read_text().splitlines() if line.strip()
                ]
            else:
                rows_by_benchmark[benchmark] = pd.read_parquet(target).to_dict(orient="records")
        folio_indices = _audit_folio_indices(
            [str(row["label"]) for row in rows_by_benchmark["folio"]], L0_SIZES["folio"]
        )
        gsm8k_counts = [gsm8k_step_count(str(row["answer"])) for row in rows_by_benchmark["gsm8k"]]
        gsm8k_indices = _audit_gsm8k_indices(gsm8k_counts, L0_SIZES["gsm8k"])
        humaneval_indices = list(range(len(rows_by_benchmark["humaneval"])))
    processor = frozen_processor(root, protocol)
    audit_ids = {
        "folio": [f"folio-{index}" for index in folio_indices],
        "gsm8k": [f"gsm8k-{index}" for index in gsm8k_indices],
        "humaneval": [f"HumanEval/{index}" for index in humaneval_indices],
    }
    for benchmark, indices in (
        ("folio", folio_indices),
        ("gsm8k", gsm8k_indices),
        ("humaneval", humaneval_indices),
    ):
        block = stored["benchmarks"][benchmark]
        ids = audit_ids[benchmark]
        entry_checks = True
        for index, example_id in zip(indices, ids, strict=True):
            row = rows_by_benchmark[benchmark][index]
            if benchmark == "folio":
                model_input = {
                    "benchmark": "folio",
                    "example_id": example_id,
                    "premises": list(row["premises"]),
                    "conclusion": str(row["conclusion"]),
                }
            elif benchmark == "gsm8k":
                model_input = {"benchmark": "gsm8k", "example_id": example_id, "question": str(row["question"])}
            else:
                model_input = {"benchmark": "humaneval", "example_id": example_id, "prompt": str(row["prompt"])}
            prompt = rendered_prompt(benchmark, model_input)
            stored_entry = block["examples"].get(example_id, {})
            entry_checks = (
                entry_checks
                and stored_entry.get("source_index") == index
                and stored_entry.get("model_input") == model_input
                and stored_entry.get("system") == prompt["system"]
                and stored_entry.get("user") == prompt["user"]
                and stored_entry.get("input_tokens")
                == count_input_tokens(processor, benchmark, model_input)
            )
        comparisons[benchmark] = {
            "l0_order_matches": block["l0_order"] == ids,
            "l1_order_matches": block["l1_order"] == _audit_l1(ids),
            "subset_size": len(ids),
            "entries_match": entry_checks,
        }
    freeze = read_json(root / OUTPUT_ROOT / "freeze.json")
    comparisons["freeze_evidence_orders_match"] = all(
        freeze["subsets"][benchmark]["l0_order"] == stored["benchmarks"][benchmark]["l0_order"]
        for benchmark in BENCHMARK_ORDER
    )

    def _flatten(value: Any) -> list[Any]:
        if isinstance(value, dict):
            return [item for nested in value.values() for item in _flatten(nested)]
        return [value]

    flat = _flatten(comparisons)
    passed = all(
        value is True or (isinstance(value, int) and not isinstance(value, bool) and value > 0) for value in flat
    )
    result = {
        "schema_version": AUDIT_FREEZE_SCHEMA,
        "outcome": "PASS" if passed else "INVALID",
        "protocol_id": protocol["protocol_id"],
        "comparisons": comparisons,
        "audited_at": time.time(),
    }
    write_json(root / OUTPUT_ROOT / "audit-freeze.json", result)
    if result["outcome"] != "PASS":
        raise RuntimeError("transfer audit-freeze independent re-derivation differs")
    return result


def _audit_freeze_extension(
    root: Path, protocol: Mapping[str, Any], reference: Mapping[str, str]
) -> dict[str, Any]:
    """Extension audit: v2 subsets byte-identical to the pinned v1 freeze; v1 evidence untouched."""
    out = root / output_root(protocol)
    stored_raw = (out / "subsets.json").read_bytes()
    source_raw = (root / reference["path"]).read_bytes()
    digest = hashlib.sha256(stored_raw).hexdigest()
    subsets = json.loads(stored_raw)
    freeze = read_json(out / "freeze.json")
    comparisons = {
        "subsets_byte_identical_to_v1": stored_raw == source_raw,
        "subsets_sha256_matches_pin": digest == reference["sha256"],
        "subsets_protocol_is_v1": subsets.get("protocol_id") == protocol.get("extends"),
        "freeze_schema": freeze.get("schema_version") == FREEZE_SCHEMA
        and freeze.get("protocol_id") == protocol["protocol_id"],
        "freeze_records_pin": freeze.get("subsets_reference", {}).get("sha256") == reference["sha256"],
        "freeze_evidence_orders_match": all(
            freeze["subsets"][benchmark]["l0_order"] == subsets["benchmarks"][benchmark]["l0_order"]
            and freeze["subsets"][benchmark]["l1_order"] == subsets["benchmarks"][benchmark]["l1_order"]
            for benchmark in BENCHMARK_ORDER
        ),
        "v1_subsets_untouched": hashlib.sha256((root / OUTPUT_ROOT / "subsets.json").read_bytes()).hexdigest()
        == reference["sha256"],
        "leakage_inherited": freeze.get("leakage", {}).get("status") == "inherited_from_v1",
    }
    passed = all(comparisons.values())
    result = {
        "schema_version": AUDIT_FREEZE_SCHEMA,
        "outcome": "PASS" if passed else "INVALID",
        "protocol_id": protocol["protocol_id"],
        "comparisons": comparisons,
        "audited_at": time.time(),
    }
    write_json(out / "audit-freeze.json", result)
    if not passed:
        raise RuntimeError("transfer audit-freeze extension verification differs")
    return result


# ---------------------------------------------------------------------------
# Probe (GPU): outcome-blind runtime gates; probe outputs are never scored
# ---------------------------------------------------------------------------


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("quantile of an empty sample")
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def probe_example_selection(block: Mapping[str, Any]) -> dict[str, str]:
    """p50/p95 input-token-length examples of the frozen L0 subset, plus the minimum."""
    entries = sorted(block["examples"].values(), key=lambda entry: (entry["input_tokens"], entry["example_id"]))
    last = len(entries) - 1
    return {
        "min": entries[0]["example_id"],
        "p50": entries[int(0.50 * last)]["example_id"],
        "p95": entries[int(0.95 * last)]["example_id"],
    }


def benchmark_request(
    benchmark: str,
    entry: Mapping[str, Any],
    adapter_id: str | None,
    *,
    session_prefix: str = "transfer",
):
    from .model_search_episode import SearchPolicyRequest

    return SearchPolicyRequest(
        session_id=f"{session_prefix}:{benchmark}:{entry['example_id']}",
        adapter_id=adapter_id,
        seed=SEED,
        instance_id=entry["example_id"],
        decision_index=0,
        model_input=dict(entry["model_input"]),
    )


def adapter_fingerprints(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    fingerprints = {}
    for cell in adapted_cells(protocol):
        checkpoint = root / protocol["cells"][cell]["checkpoint"]
        fingerprints[cell] = {
            "checkpoint": protocol["cells"][cell]["checkpoint"],
            "adapter_config_sha256": "sha256:" + _sha256_path(checkpoint / "adapter_config.json"),
            "adapter_model_sha256": "sha256:" + _sha256_path(checkpoint / "adapter_model.safetensors"),
        }
    return fingerprints


def _generated_tokens(policy: Any, text: str) -> int:
    return len(policy.processor.tokenizer(text, add_special_tokens=False)["input_ids"])


def probe_stage(
    root: Path,
    protocol: Mapping[str, Any],
    *,
    attempt_dir: Path,
    progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """GPU probe: parity, determinism, isolation, token-limit guard, latency, throughput."""
    import torch
    from transformers import set_seed

    from .qwen_text_policy import BatchedPolicyAdapter

    os.environ.setdefault("HF_HOME", str(root / ".cache" / "hf"))
    attempt_dir = Path(attempt_dir)
    started_all = time.monotonic()
    out = root / output_root(protocol)
    order = cell_order(protocol)
    adapted = adapted_cells(protocol)
    subsets = read_json(out / "subsets.json")
    if subsets.get("schema_version") != SUBSETS_SCHEMA or subsets.get("protocol_id") not in _protocol_ids(protocol):
        raise ValueError("transfer probe requires frozen subsets")
    freeze = read_json(out / "freeze.json")
    if freeze.get("outcome") != "PASS":
        raise ValueError("transfer probe requires a PASS freeze")
    set_seed(SEED)
    load_started = time.monotonic()
    policy = BatchedPolicyAdapter(
        model_id=protocol["base_model"]["model_id"],
        revision=protocol["base_model"]["revision"],
        adapter_paths={cell: root / protocol["cells"][cell]["checkpoint"] for cell in adapted},
        device="cuda:0",
        max_new_tokens=64,
        max_context_tokens=MAX_CONTEXT_TOKENS,
        max_batch_size=MAX_BATCH_SIZE,
        max_batch_input_tokens=MAX_BATCH_INPUT_TOKENS,
        inference_dtype="float32",
        training_message_builder=lambda model_input: TRAINING_BUILDERS[model_input["benchmark"]](model_input),
        policy_message_builder=lambda model_input: POLICY_BUILDERS[model_input["benchmark"]](model_input),
    )
    load_seconds = time.monotonic() - load_started
    load_vram = torch.cuda.memory_allocated()

    selections = {benchmark: probe_example_selection(subsets["benchmarks"][benchmark]) for benchmark in BENCHMARK_ORDER}
    cells: dict[str, dict[str, Any]] = {}
    isolation_pre: list[str] | None = None
    isolation_requests = []
    if "base" not in order:
        # Extension protocols run no base cell; capture the uncached base outputs (adapter_id=None)
        # explicitly so adapter isolation is still verified pre/post the adapted cells.
        folio_block = subsets["benchmarks"]["folio"]
        picked = []
        for key in ("min", "p50", "p95"):
            example_id = selections["folio"][key]
            if example_id not in picked:
                picked.append(example_id)
        policy.max_new_tokens = folio_block["max_new_tokens"]
        isolation_requests = [
            benchmark_request("folio", folio_block["examples"][example_id], None, session_prefix="transfer-probe")
            for example_id in picked
        ]
        isolation_pre = list(policy._generate_uncached(None, isolation_requests))
    total_cells = len(BENCHMARK_ORDER) * len(order)
    completed_cells = 0
    for benchmark in BENCHMARK_ORDER:
        block = subsets["benchmarks"][benchmark]
        policy.max_new_tokens = block["max_new_tokens"]
        picked = []
        for key in ("min", "p50", "p95"):
            example_id = selections[benchmark][key]
            if example_id not in picked:
                picked.append(example_id)
        entries = [block["examples"][example_id] for example_id in picked]
        cells[benchmark] = {}
        for cell in order:
            adapter_id = None if cell == "base" else cell
            requests = [
                benchmark_request(benchmark, entry, adapter_id, session_prefix="transfer-probe") for entry in entries
            ]
            batched_started = time.monotonic()
            batched_outputs = policy._generate_uncached(adapter_id, requests)
            batched_latency = time.monotonic() - batched_started
            batched_generated = sum(_generated_tokens(policy, output) for output in batched_outputs)
            per_example = []
            for request, entry in zip(requests, entries, strict=True):
                example_started = time.monotonic()
                output = policy._generate_uncached(adapter_id, [request])[0]
                per_example.append(
                    {
                        "example_id": entry["example_id"],
                        "input_tokens": entry["input_tokens"],
                        "latency_seconds": time.monotonic() - example_started,
                        "generated_tokens": _generated_tokens(policy, output),
                    }
                )
            parity = policy.verify_scalar_parity(requests)
            determinism = policy.verify_determinism(requests)
            if benchmark == "folio" and cell == "base":
                isolation_pre = list(batched_outputs)
                isolation_requests = list(requests)
            if not parity:
                raise RuntimeError(f"VALID_STOP: transfer scalar/batch parity failed for {benchmark}/{cell}")
            if not determinism:
                raise RuntimeError(f"VALID_STOP: transfer repeated-batch determinism failed for {benchmark}/{cell}")
            cells[benchmark][cell] = {
                "adapter_id": adapter_id,
                "max_new_tokens": block["max_new_tokens"],
                "raw_outputs": dict(zip(picked, batched_outputs, strict=True)),
                "batched": {
                    "batch_size": len(requests),
                    "latency_seconds": batched_latency,
                    "generated_tokens": batched_generated,
                    "throughput_tokens_per_second": batched_generated / max(batched_latency, 1e-9),
                },
                "per_example": per_example,
                "scalar_batch_parity": parity,
                "repeated_batch_determinism": determinism,
            }
            completed_cells += 1
            if progress is not None:
                progress(completed=completed_cells, total=total_cells, stage=f"probe_{benchmark}_{cell}")

    policy.max_new_tokens = subsets["benchmarks"]["folio"]["max_new_tokens"]
    if isolation_pre is None or not isolation_requests:
        raise RuntimeError("VALID_STOP: transfer adapter isolation baseline was not captured")
    isolation_post = policy._generate_uncached(None, isolation_requests)
    adapter_isolation = {
        "benchmark": "folio",
        "example_ids": [request.instance_id for request in isolation_requests],
        "byte_identical": isolation_pre == isolation_post,
        "method": "base outputs before any adapter load vs base outputs (adapters disabled) after all adapter cells",
    }
    if not adapter_isolation["byte_identical"]:
        raise RuntimeError("VALID_STOP: transfer adapter isolation failed")

    guard_entries = []
    for benchmark in BENCHMARK_ORDER:
        block = subsets["benchmarks"][benchmark]
        guard_entries.append(
            max(entry["input_tokens"] for entry in block["examples"].values()) + block["max_new_tokens"]
        )
    folio_block = subsets["benchmarks"]["folio"]
    min_entry = folio_block["examples"][selections["folio"]["min"]]
    guard_request = benchmark_request("folio", min_entry, None, session_prefix="transfer-guard")
    original_context = policy.max_context_tokens
    policy.max_new_tokens = folio_block["max_new_tokens"]
    policy.max_context_tokens = min_entry["input_tokens"] + folio_block["max_new_tokens"] - 1
    oversize_raises = False
    try:
        policy._generate_uncached(None, [guard_request])
    except ValueError as error:
        oversize_raises = "context" in str(error)
    finally:
        policy.max_context_tokens = original_context
    token_limit_guard = {
        "max_context_tokens": MAX_CONTEXT_TOKENS,
        "max_input_plus_allowance_per_benchmark": dict(zip(BENCHMARK_ORDER, guard_entries, strict=True)),
        "all_frozen_inputs_fit": all(value <= MAX_CONTEXT_TOKENS for value in guard_entries),
        "oversize_context_raises": oversize_raises,
    }
    if not oversize_raises:
        raise RuntimeError("VALID_STOP: transfer token-limit guard is not enforced")

    throughput = {}
    latency = {}
    for benchmark in BENCHMARK_ORDER:
        samples = [cells[benchmark][cell]["batched"]["throughput_tokens_per_second"] for cell in order]
        throughput[benchmark] = {
            "samples_tokens_per_second": samples,
            "lower_95_tokens_per_second": lower_95_throughput_bound(samples),
        }
        per_example_seconds = [
            row["latency_seconds"] for cell in order for row in cells[benchmark][cell]["per_example"]
        ]
        latency[benchmark] = {
            "per_example_seconds": per_example_seconds,
            "p50_seconds_per_example": _quantile(per_example_seconds, 0.50),
            "p95_seconds_per_example": _quantile(per_example_seconds, 0.95),
        }

    result = {
        "schema_version": PROBE_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "gpu": {"index": 0, "name": torch.cuda.get_device_name(0)},
        "load": {"wall_seconds": load_seconds, "vram_bytes_after_load": load_vram},
        "policy_identity": dict(policy.identity),
        "adapter_fingerprints": adapter_fingerprints(root, protocol),
        "probe_examples": selections,
        "max_new_tokens": {
            benchmark: subsets["benchmarks"][benchmark]["max_new_tokens"] for benchmark in BENCHMARK_ORDER
        },
        "cells": cells,
        "adapter_isolation": adapter_isolation,
        "token_limit_guard": token_limit_guard,
        "throughput": throughput,
        "latency": latency,
        "probe_outputs_scored": False,
        "probe_gpu_hours": (time.monotonic() - started_all) / 3600,
        "finished_at": time.time(),
    }
    write_json(attempt_dir / "probe.json", result)
    write_json(out / "probe.json", result)
    return result


def audit_probe_stage(root: Path, protocol: Mapping[str, Any], probe: Mapping[str, Any]) -> dict[str, Any]:
    """CPU hook: probe.json schema/completeness — every required measurement, every cell."""
    problems: list[str] = []
    if probe.get("schema_version") != PROBE_SCHEMA or probe.get("protocol_id") != protocol["protocol_id"]:
        problems.append("schema/protocol")
    if probe.get("outcome") != "PASS":
        problems.append("outcome")
    if not probe.get("load", {}).get("wall_seconds"):
        problems.append("load wall time")
    order = cell_order(protocol)
    for benchmark in BENCHMARK_ORDER:
        block = probe.get("cells", {}).get(benchmark, {})
        if sorted(block) != sorted(order):
            problems.append(f"{benchmark} cells covered: {sorted(block)}")
            continue
        for cell in order:
            entry = block[cell]
            if entry.get("scalar_batch_parity") is not True:
                problems.append(f"{benchmark}/{cell} parity")
            if entry.get("repeated_batch_determinism") is not True:
                problems.append(f"{benchmark}/{cell} determinism")
            if not entry.get("per_example") or not entry.get("raw_outputs"):
                problems.append(f"{benchmark}/{cell} measurements")
        if probe.get("throughput", {}).get(benchmark, {}).get("lower_95_tokens_per_second", 0) <= 0:
            problems.append(f"{benchmark} throughput")
        if probe.get("latency", {}).get(benchmark, {}).get("p95_seconds_per_example", 0) <= 0:
            problems.append(f"{benchmark} p95 latency")
        selection = probe.get("probe_examples", {}).get(benchmark, {})
        if sorted(selection) != ["min", "p50", "p95"]:
            problems.append(f"{benchmark} probe selection")
    if probe.get("adapter_isolation", {}).get("byte_identical") is not True:
        problems.append("adapter isolation")
    guard = probe.get("token_limit_guard", {})
    if guard.get("all_frozen_inputs_fit") is not True or guard.get("oversize_context_raises") is not True:
        problems.append("token-limit guard")
    if probe.get("probe_outputs_scored") is not False:
        problems.append("probe outputs must never be scored")
    result = {
        "schema_version": AUDIT_PROBE_SCHEMA,
        "outcome": "PASS" if not problems else "INVALID",
        "protocol_id": protocol["protocol_id"],
        "problems": problems,
        "audited_at": time.time(),
    }
    write_json(root / output_root(protocol) / "audit-probe.json", result)
    if problems:
        raise RuntimeError("transfer probe evidence is incomplete: " + "; ".join(problems))
    return result


# ---------------------------------------------------------------------------
# Cost admission (CPU): L0 full panel, L1 frozen reduced panel, L2 VALID_STOP
# ---------------------------------------------------------------------------


def _branch_spent(ledger: Mapping[str, Any]) -> float:
    total = 0.0
    for attempt in ledger.get("attempts", []):
        if attempt.get("branch") != BRANCH:
            continue
        if attempt.get("status") in ("reserved", "running"):
            total += float(attempt.get("max_seconds", 0.0)) * len(attempt.get("gpus", [])) / 3600
        else:
            total += float(attempt.get("gpu_hours", 0.0))
    return total


def decide_admission(
    protocol: Mapping[str, Any],
    probe: Mapping[str, Any],
    *,
    branch_spent_gpu_hours: float,
    now_epoch: float,
    cutoff_epoch: float,
) -> dict[str, Any]:
    """Frozen admission arithmetic: p95 probe latency x subset size x cell count + load, x 1.25."""
    cap = float(protocol.get("allocation_gpu_hours", BRANCH_GPU_HOURS))
    safety = SAFETY_FACTOR
    load_seconds = float(probe["load"]["wall_seconds"])
    remainder = cap - branch_spent_gpu_hours
    cell_count = len(cell_order(protocol))
    workers = worker_benchmarks(protocol)
    arithmetic: dict[str, Any] = {}
    for level, sizes in (("L0", l0_sizes(protocol)), ("L1", l1_sizes(protocol))):
        per_worker_seconds = {
            str(worker): sum(
                probe["latency"][benchmark]["p95_seconds_per_example"] * sizes[benchmark] * cell_count
                for benchmark in benchmarks
            )
            + load_seconds
            for worker, benchmarks in workers.items()
        }
        required_gpu_hours = sum(per_worker_seconds.values()) * safety / 3600
        wall_seconds = max(per_worker_seconds.values()) * safety
        fits_branch = required_gpu_hours <= remainder
        fits_per_worker = all(seconds * safety / 3600 <= cap for seconds in per_worker_seconds.values())
        fits_cutoff = now_epoch + wall_seconds <= cutoff_epoch
        arithmetic[level] = {
            "subset_sizes": sizes,
            "per_worker_seconds": per_worker_seconds,
            "required_gpu_hours": required_gpu_hours,
            "required_wall_seconds": wall_seconds,
            "safety_factor": safety,
            "fits_branch_remainder": fits_branch,
            "fits_per_worker_24h": fits_per_worker,
            "fits_absolute_cutoff": fits_cutoff,
            "fits": fits_branch and fits_per_worker and fits_cutoff,
        }
    if arithmetic["L0"]["fits"]:
        decision, outcome = "L0", "PASS"
    elif arithmetic["L1"]["fits"]:
        decision, outcome = "L1", "PASS"
    else:
        decision, outcome = "L2", "VALID_STOP"
    authorized = None
    if outcome == "PASS":
        authorized = {
            "decision": decision,
            "subset_sizes": arithmetic[decision]["subset_sizes"],
            "selection": (
                "full frozen L0 subsets"
                if decision == "L0"
                else "frozen L1 reduced panel: even-numbered positions of each frozen L0 ordered subset"
            ),
        }
    return {
        "schema_version": ADMISSION_SCHEMA,
        "decision": decision,
        "outcome": outcome,
        "protocol_id": protocol["protocol_id"],
        "branch_cap_gpu_hours": cap,
        "branch_spent_gpu_hours": branch_spent_gpu_hours,
        "branch_remainder_gpu_hours": remainder,
        "arithmetic": arithmetic,
        "measured_inputs": {
            "p95_seconds_per_example": {
                benchmark: probe["latency"][benchmark]["p95_seconds_per_example"] for benchmark in BENCHMARK_ORDER
            },
            "model_load_seconds": load_seconds,
            "probe_gpu_hours": probe.get("probe_gpu_hours"),
        },
        "authorized_subsets": authorized,
        "ledger_mutated": False,
        "decided_at": now_epoch,
    }


def admit_stage(root: Path, protocol: Mapping[str, Any], *, now_epoch: float | None = None) -> dict[str, Any]:
    out = root / output_root(protocol)
    probe_path = out / "probe.json"
    if not probe_path.is_file():
        raise RuntimeError("VALID_STOP: transfer admission requires a completed probe")
    probe = read_json(probe_path)
    if probe.get("schema_version") != PROBE_SCHEMA or probe.get("outcome") != "PASS":
        raise RuntimeError("transfer admission requires a PASS probe")
    ledger = read_json(root / LEDGER_PATH)
    cutoff = read_json(root / SCHEDULE_DOC)["gpu_cutoff_utc"]
    from .expanded_scheduler import timestamp

    result = decide_admission(
        protocol,
        probe,
        branch_spent_gpu_hours=_branch_spent(ledger),
        now_epoch=time.time() if now_epoch is None else now_epoch,
        cutoff_epoch=timestamp(cutoff),
    )
    write_json(out / "admission.json", result)
    return result


def require_admission_gate(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """GPU evaluation work is authorized only by a PASS admission (L0 full or L1 reduced)."""
    path = root / output_root(protocol) / "admission.json"
    if not path.is_file():
        raise RuntimeError("VALID_STOP: transfer cost admission has not run")
    admission = read_json(path)
    if (
        admission.get("schema_version") != ADMISSION_SCHEMA
        or admission.get("protocol_id") != protocol["protocol_id"]
        or admission.get("outcome") != "PASS"
        or admission.get("decision") not in ("L0", "L1")
        or admission.get("ledger_mutated") is not False
        or not isinstance(admission.get("authorized_subsets"), dict)
        or admission["authorized_subsets"].get("decision") != admission.get("decision")
    ):
        raise RuntimeError(
            "VALID_STOP: transfer admission did not authorize execution "
            f"(decision={admission.get('decision')}, outcome={admission.get('outcome')}); "
            "arithmetic is published in admission.json"
        )
    return admission


def authorized_ids(subsets: Mapping[str, Any], admission: Mapping[str, Any], benchmark: str) -> list[str]:
    block = subsets["benchmarks"][benchmark]
    key = "l1_order" if admission["decision"] == "L1" else "l0_order"
    ids = list(block[key])
    expected = admission["authorized_subsets"]["subset_sizes"][benchmark]
    if len(ids) != expected:
        raise ValueError("transfer authorized subset size differs from the frozen order")
    return ids


# ---------------------------------------------------------------------------
# Run (GPU): journal per (benchmark, cell) with safe resume
# ---------------------------------------------------------------------------


def _run_paths(root: Path, benchmark: str, cell: str, protocol: Mapping[str, Any] | None = None) -> tuple[Path, Path]:
    base = output_root(protocol) if protocol else OUTPUT_ROOT
    run_dir = root / base / "run" / benchmark
    final = run_dir / f"{cell}.json.gz"
    journal = run_dir / f"{cell}.partial.json.gz"
    return final, journal


def _run_identity(
    protocol: Mapping[str, Any],
    benchmark: str,
    cell: str,
    level: str,
    allowance: int,
    fingerprints: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": RUN_CELL_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "benchmark": benchmark,
        "cell": cell,
        "adapter_id": None if cell == "base" else cell,
        "subset_level": level,
        "max_new_tokens": allowance,
        "model_id": protocol["base_model"]["model_id"],
        "model_revision": protocol["base_model"]["revision"],
        "adapter_fingerprint": fingerprints.get(cell),
    }


def run_cell(
    root: Path,
    protocol: Mapping[str, Any],
    subsets: Mapping[str, Any],
    policy: Any,
    *,
    benchmark: str,
    cell: str,
    ids: Sequence[str],
    level: str,
    fingerprints: Mapping[str, Any],
    progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Run one (benchmark, cell): batch via the frozen caps, journal each example, resume-safe."""
    block = subsets["benchmarks"][benchmark]
    final, journal = _run_paths(root, benchmark, cell, protocol)
    identity = _run_identity(protocol, benchmark, cell, level, block["max_new_tokens"], fingerprints)
    if final.is_file():
        report = read_json(final)
        if any(report.get(key) != value for key, value in identity.items()) or report.get("order") != list(ids):
            raise ValueError(f"transfer retained cell differs: {benchmark}/{cell}")
        if journal.is_file():
            raise ValueError(f"transfer completed cell retains a conflicting journal: {benchmark}/{cell}")
        if progress is not None:
            progress(completed_delta=len(ids), stage=f"retained_{benchmark}_{cell}")
        return report

    entries: dict[str, Any] = {}
    started = time.time()
    resumptions = 0
    if journal.is_file():
        saved = read_json(journal)
        if any(saved.get(key) != value for key, value in identity.items() if key != "schema_version"):
            raise ValueError(f"transfer partial journal identity differs: {benchmark}/{cell}")
        if saved.get("schema_version") != RUN_JOURNAL_SCHEMA:
            raise ValueError(f"transfer partial journal schema differs: {benchmark}/{cell}")
        entries = dict(saved["entries"])
        started = saved.get("started", started)
        resumptions = int(saved.get("resumptions", 0)) + 1
    adapter_id = identity["adapter_id"]
    pending = [example_id for example_id in ids if example_id not in entries]
    requests = []
    for example_id in pending:
        entry = block["examples"][example_id]
        rendered = rendered_prompt(benchmark, entry["model_input"])
        if rendered["user"] != entry["user"] or rendered["system"] != entry["system"]:
            raise ValueError(f"transfer prompt differs from frozen subsets: {example_id}")
        requests.append(benchmark_request(benchmark, entry, adapter_id))
    policy.max_new_tokens = block["max_new_tokens"]
    batches = form_deterministic_batches(requests, token_length=policy.input_token_length)
    for batch in batches:
        batch_started = time.monotonic()
        outputs = policy.generate_many(batch.requests)
        latency = time.monotonic() - batch_started
        for request, output in zip(batch.requests, outputs, strict=True):
            entries[request.instance_id] = {
                "raw_output": output,
                "input_tokens": block["examples"][request.instance_id]["input_tokens"],
                "generated_tokens": _generated_tokens(policy, output),
                "batch_size": len(batch.requests),
                "batch_latency_seconds": latency,
            }
        write_json(
            journal,
            {
                **identity,
                "schema_version": RUN_JOURNAL_SCHEMA,
                "entries": entries,
                "started": started,
                "resumptions": resumptions,
            },
        )
        if progress is not None:
            progress(completed_delta=len(batch.requests), stage=f"{benchmark}_{cell}")
    report = {
        **identity,
        "examples": len(ids),
        "order": list(ids),
        "entries": {example_id: entries[example_id] for example_id in ids},
        "generated_tokens_total": sum(entries[example_id]["generated_tokens"] for example_id in ids),
        "input_tokens_total": sum(entries[example_id]["input_tokens"] for example_id in ids),
        "started": started,
        "finished_at": time.time(),
    }
    write_json(final, report)
    journal.unlink(missing_ok=True)
    return report


def run_worker(
    root: Path,
    protocol: Mapping[str, Any],
    worker: int,
    *,
    attempt_dir: Path,
    progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    if worker not in worker_benchmarks(protocol):
        raise ValueError("transfer worker is outside the frozen mapping")
    os.environ.setdefault("HF_HOME", str(root / ".cache" / "hf"))
    from transformers import set_seed

    from .qwen_text_policy import BatchedPolicyAdapter

    out = root / output_root(protocol)
    order = cell_order(protocol)
    admission = require_admission_gate(root, protocol)
    level = admission["decision"]
    subsets = read_json(out / "subsets.json")
    if subsets.get("schema_version") != SUBSETS_SCHEMA or subsets.get("protocol_id") not in _protocol_ids(protocol):
        raise ValueError("transfer run requires frozen subsets")
    from .expanded_scheduler import timestamp

    cutoff = timestamp(read_json(root / SCHEDULE_DOC)["gpu_cutoff_utc"])
    if time.time() >= cutoff:
        raise RuntimeError("VALID_STOP: transfer GPU cutoff has passed")
    benchmarks = worker_benchmarks(protocol)[worker]
    selected = {benchmark: authorized_ids(subsets, admission, benchmark) for benchmark in benchmarks}
    total_units = sum(len(ids) for ids in selected.values()) * len(order)
    completed_units = 0

    def unit_progress(*, completed_delta: int, stage: str) -> None:
        nonlocal completed_units
        completed_units += completed_delta
        if progress is not None:
            progress(completed=completed_units, total=total_units, stage=stage)

    set_seed(SEED)
    load_started = time.monotonic()
    policy = BatchedPolicyAdapter(
        model_id=protocol["base_model"]["model_id"],
        revision=protocol["base_model"]["revision"],
        adapter_paths={cell: root / protocol["cells"][cell]["checkpoint"] for cell in adapted_cells(protocol)},
        device="cuda:0",
        max_new_tokens=64,
        max_context_tokens=MAX_CONTEXT_TOKENS,
        max_batch_size=MAX_BATCH_SIZE,
        max_batch_input_tokens=MAX_BATCH_INPUT_TOKENS,
        inference_dtype="float32",
        training_message_builder=lambda model_input: TRAINING_BUILDERS[model_input["benchmark"]](model_input),
        policy_message_builder=lambda model_input: POLICY_BUILDERS[model_input["benchmark"]](model_input),
    )
    load_seconds = time.monotonic() - load_started
    fingerprints = adapter_fingerprints(root, protocol)
    started = time.monotonic()
    reports: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for benchmark in benchmarks:
        for cell in order:
            if time.time() >= cutoff:
                missing.append({"benchmark": benchmark, "cell": cell})
                continue
            report = run_cell(
                root,
                protocol,
                subsets,
                policy,
                benchmark=benchmark,
                cell=cell,
                ids=selected[benchmark],
                level=level,
                fingerprints=fingerprints,
                progress=unit_progress,
            )
            reports.append(
                {
                    "benchmark": benchmark,
                    "cell": cell,
                    "examples": report["examples"],
                    "generated_tokens_total": report["generated_tokens_total"],
                    "output": str(_run_paths(root, benchmark, cell, protocol)[0].relative_to(root)),
                }
            )
    result = {
        "schema_version": WORKER_RESULT_SCHEMA,
        "outcome": "PASS" if not missing else "VALID_STOP",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "gpu": worker_gpus(protocol)[worker],
        "admission_decision": level,
        "benchmarks": list(benchmarks),
        "cells": reports,
        "missing": missing,
        "examples_completed": sum(row["examples"] for row in reports),
        "policy_identity": dict(policy.identity),
        "adapter_fingerprints": fingerprints,
        "model_load_seconds": load_seconds,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": int(os.environ["MASTER_PORT"]) if os.environ.get("MASTER_PORT") else None,
        "elapsed_seconds": time.monotonic() - started,
    }
    write_json(Path(attempt_dir) / "worker-result.json", result)
    return result


def audit_run_worker(
    root: Path,
    protocol: Mapping[str, Any],
    worker: int,
    *,
    terminal: Mapping[str, Any],
) -> dict[str, Any]:
    """CPU hook: declared coverage == produced coverage; provenance; no duplicates."""
    if worker not in worker_benchmarks(protocol):
        raise ValueError("transfer worker is outside the frozen mapping")
    if terminal.get("status") != "succeeded":
        raise RuntimeError(f"transfer run worker {worker} did not succeed")
    directory = Path(str(terminal["directory"]))
    result = read_json(directory / "worker-result.json")
    if result.get("schema_version") != WORKER_RESULT_SCHEMA or result.get("worker") != worker:
        raise ValueError("transfer worker result provenance differs")
    admission = require_admission_gate(root, protocol)
    subsets = read_json(root / output_root(protocol) / "subsets.json")
    fingerprints = adapter_fingerprints(root, protocol)
    problems: list[str] = []
    produced = {(row["benchmark"], row["cell"]): row for row in result.get("cells", [])}
    declared_missing = {(row["benchmark"], row["cell"]) for row in result.get("missing", [])}
    audited_cells = []
    order = cell_order(protocol)
    for benchmark in worker_benchmarks(protocol)[worker]:
        ids = authorized_ids(subsets, admission, benchmark)
        for cell in order:
            key = (benchmark, cell)
            final, journal = _run_paths(root, benchmark, cell, protocol)
            if not final.is_file():
                if key not in declared_missing:
                    problems.append(f"{benchmark}/{cell} missing but not declared")
                continue
            if key not in produced:
                problems.append(f"{benchmark}/{cell} produced but not declared")
                continue
            report = read_json(final)
            identity = _run_identity(
                protocol,
                benchmark,
                cell,
                admission["decision"],
                subsets["benchmarks"][benchmark]["max_new_tokens"],
                fingerprints,
            )
            if any(report.get(k) != v for k, v in identity.items()):
                problems.append(f"{benchmark}/{cell} identity differs")
                continue
            if journal.is_file():
                problems.append(f"{benchmark}/{cell} retains a partial journal")
            report_order = report.get("order", [])
            entries = report.get("entries", {})
            if report_order != ids or sorted(entries) != sorted(ids) or len(set(report_order)) != len(report_order):
                problems.append(f"{benchmark}/{cell} coverage differs")
                continue
            for example_id in ids:
                entry = entries[example_id]
                frozen = subsets["benchmarks"][benchmark]["examples"][example_id]
                rendered = rendered_prompt(benchmark, frozen["model_input"])
                if (
                    rendered["user"] != frozen["user"]
                    or not isinstance(entry.get("raw_output"), str)
                    or entry.get("input_tokens") != frozen["input_tokens"]
                ):
                    problems.append(f"{benchmark}/{cell}/{example_id} provenance differs")
                    break
            else:
                audited_cells.append({"benchmark": benchmark, "cell": cell, "examples": len(ids)})
    declared_cells = [(row["benchmark"], row["cell"]) for row in result.get("cells", [])]
    if len(declared_cells) != len(set(declared_cells)):
        problems.append("duplicate produced cells")
    if problems:
        outcome = "INVALID"
    else:
        outcome = "PASS" if result.get("outcome") == "PASS" else "VALID_STOP"
    audit = {
        "schema_version": AUDIT_RUN_SCHEMA,
        "outcome": outcome,
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "cells_audited": audited_cells,
        "missing": sorted(f"{benchmark}/{cell}" for benchmark, cell in declared_missing),
        "problems": problems,
        "audited_at": time.time(),
    }
    write_json(directory / "independent-audit.json", audit)
    if problems:
        raise RuntimeError("transfer run worker audit failed: " + "; ".join(problems))
    return audit


# ---------------------------------------------------------------------------
# Score (CPU): pinned parsing, sandboxed HumanEval execution
# ---------------------------------------------------------------------------


def _score_folio(gold: Mapping[str, Any], raw_output: str) -> dict[str, Any]:
    prediction, malformed = parse_folio_prediction(raw_output)
    correct = prediction == gold["label"] if not malformed else False
    return {
        "prediction": prediction,
        "gold": gold["label"],
        "correct": correct,
        "malformed": malformed,
        "category": "malformed" if malformed else ("correct" if correct else "incorrect"),
    }


def _score_gsm8k(gold: Mapping[str, Any], raw_output: str) -> dict[str, Any]:
    prediction, malformed = parse_gsm8k_prediction(raw_output)
    correct = gsm8k_correct(prediction, gold["final"]) if not malformed else False
    return {
        "prediction": prediction,
        "gold": gold["final"],
        "correct": correct,
        "malformed": malformed,
        "category": "malformed" if malformed else ("correct" if correct else "incorrect"),
    }


def _score_humaneval(gold: Mapping[str, Any], raw_output: str, *, use_unshare: bool) -> dict[str, Any]:
    code = extract_humaneval_code(raw_output)
    if not code or not humaneval_defines_entry_point(code, gold["entry_point"]):
        return {
            "prediction": None,
            "gold": gold["entry_point"],
            "correct": False,
            "malformed": True,
            "category": "malformed",
            "extracted_code": code,
            "execution": None,
        }
    program = build_humaneval_program(code, gold["test"], gold["entry_point"])
    execution = execute_humaneval_program(program, use_unshare=use_unshare)
    return {
        "prediction": code,
        "gold": gold["entry_point"],
        "correct": execution["category"] == "passed",
        "malformed": False,
        "category": execution["category"],
        "extracted_code": code,
        "execution": execution,
    }


def _cell_latency_seconds(entries: Mapping[str, Any]) -> float:
    """Sum batch wall time exactly once per batch from the per-example shares."""
    return sum(entry["batch_latency_seconds"] / entry["batch_size"] for entry in entries.values())


def score_stage(
    root: Path, protocol: Mapping[str, Any], *, progress: Callable[..., None] | None = None
) -> dict[str, Any]:
    freeze = read_json(root / output_root(protocol) / "freeze.json")
    use_unshare = bool(freeze.get("sandbox", {}).get("unshare_network_available"))
    subsets = read_json(root / output_root(protocol) / "subsets.json")
    cells: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    scores_dir = root / output_root(protocol) / "scores"
    order = cell_order(protocol)
    total = sum(len(block["l0_order"]) for block in subsets["benchmarks"].values()) * len(order)
    completed = 0
    for benchmark in BENCHMARK_ORDER:
        block = subsets["benchmarks"][benchmark]
        for cell in order:
            final, _journal = _run_paths(root, benchmark, cell, protocol)
            if not final.is_file():
                missing.append({"benchmark": benchmark, "cell": cell})
                continue
            report = read_json(final)
            predictions = []
            counts: dict[str, int] = {}
            correct = 0
            malformed = 0
            for example_id in report["order"]:
                entry = report["entries"][example_id]
                gold = block["examples"][example_id]["gold"]
                raw_output = entry["raw_output"]
                if benchmark == "folio":
                    scored = _score_folio(gold, raw_output)
                elif benchmark == "gsm8k":
                    scored = _score_gsm8k(gold, raw_output)
                else:
                    scored = _score_humaneval(gold, raw_output, use_unshare=use_unshare)
                correct += int(scored["correct"])
                malformed += int(scored["malformed"])
                counts[scored["category"]] = counts.get(scored["category"], 0) + 1
                predictions.append(
                    {
                        "example_id": example_id,
                        "raw_output": raw_output,
                        "input_tokens": entry["input_tokens"],
                        "generated_tokens": entry["generated_tokens"],
                        **scored,
                    }
                )
                completed += 1
                if progress is not None and completed % 25 == 0:
                    progress(completed=completed, total=total, stage=f"score_{benchmark}_{cell}")
            write_json(
                scores_dir / f"predictions-{benchmark}-{cell}.jsonl.gz",
                {
                    "schema_version": PREDICTIONS_SCHEMA,
                    "protocol_id": protocol["protocol_id"],
                    "benchmark": benchmark,
                    "cell": cell,
                    "subset_level": report["subset_level"],
                    "predictions": predictions,
                },
            )
            cells.append(
                {
                    "benchmark": benchmark,
                    "cell": cell,
                    "subset_level": report["subset_level"],
                    "examples": len(report["order"]),
                    "correct": correct,
                    "accuracy": correct / len(report["order"]),
                    "malformed": malformed,
                    "categories": counts,
                    "generated_tokens_total": report["generated_tokens_total"],
                    "input_tokens_total": report["input_tokens_total"],
                    "latency_seconds": _cell_latency_seconds(report["entries"]),
                    "predictions": str((scores_dir / f"predictions-{benchmark}-{cell}.jsonl.gz").relative_to(root)),
                }
            )
    result = {
        "schema_version": SCORES_SCHEMA,
        "outcome": "PASS" if not missing else "VALID_STOP",
        "protocol_id": protocol["protocol_id"],
        "metric": {
            "folio": "accuracy over the frozen subset; malformed reported separately",
            "gsm8k": "accuracy over the frozen subset; malformed reported separately",
            "humaneval": "pass@1 with a single greedy sample; failures reported by category",
        },
        "sandbox": freeze.get("sandbox"),
        "cells": cells,
        "missing": missing,
        "scored_at": time.time(),
    }
    write_json(root / output_root(protocol) / "scores.json", result)
    if progress is not None:
        progress(completed=completed, total=total, stage="scored")
    return result


# ---------------------------------------------------------------------------
# audit-score: independent re-parse/re-score; duplicated small logic, no reuse
# ---------------------------------------------------------------------------


def _audit_parse_folio(raw_output: str) -> str | None:
    for word in re.findall(r"[A-Za-z]+", raw_output):
        lowered = word.lower()
        if lowered in ("true", "false", "uncertain"):
            return lowered.capitalize()
    return None


_AUDIT_NUMBER = re.compile(r"-?\$?-?[0-9][0-9,]*(?:\.[0-9]+)?")


def _audit_clean_number(text: str) -> str:
    cleaned = text.replace("$", "").replace(",", "")
    while cleaned.endswith("."):
        cleaned = cleaned[:-1]
    return cleaned.strip()


def _audit_parse_gsm8k(raw_output: str) -> str | None:
    if "####" in raw_output:
        tail = raw_output.split("####")[-1]
        found = _AUDIT_NUMBER.search(tail)
        if found is not None:
            return _audit_clean_number(found.group(0))
    found = _AUDIT_NUMBER.findall(raw_output)
    return _audit_clean_number(found[-1]) if found else None


def _audit_gsm8k_equal(prediction: str, gold: str) -> bool:
    if prediction == gold:
        return True
    try:
        return abs(float(prediction) - float(gold)) <= 1e-6
    except ValueError:
        return False


def _audit_extract_humaneval(raw_output: str) -> str:
    """Independent implementation of the frozen extraction rule (first complete block only).

    A ```python candidate must be followed by a whitespace run containing a newline, and the
    block must close at the next ```; candidates failing either check are skipped. An
    unterminated fence is not a complete block, so the raw output is the fallback. This
    mirrors HUMANEVAL_FENCED_RE semantics exactly without reusing it.
    """
    rest = raw_output
    while "```python" in rest:
        rest = rest.split("```python", 1)[1]
        index = 0
        while index < len(rest) and rest[index].isspace():
            index += 1
        head = rest[:index]
        if "\n" not in head:
            continue
        tail = rest[head.rindex("\n") + 1 :]
        if "```" not in tail:
            continue
        return tail.split("```", 1)[0].strip("\n").strip()
    return raw_output.strip("\n").strip()


def _audit_defines(code: str, entry_point: str) -> bool:
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    names = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return entry_point in names


def audit_score_stage(
    root: Path, protocol: Mapping[str, Any], *, resample_budget_seconds: float = RESAMPLE_BUDGET_SECONDS
) -> dict[str, Any]:
    scores = read_json(root / output_root(protocol) / "scores.json")
    if scores.get("schema_version") != SCORES_SCHEMA or scores.get("protocol_id") != protocol["protocol_id"]:
        raise ValueError("transfer scores evidence differs from the frozen schema")
    freeze = read_json(root / output_root(protocol) / "freeze.json")
    use_unshare = bool(freeze.get("sandbox", {}).get("unshare_network_available"))
    subsets = read_json(root / output_root(protocol) / "subsets.json")
    problems: list[str] = []
    resample_report: list[dict[str, Any]] = []
    resample_started = time.monotonic()
    resample_planned = 0
    resample_re_executed = 0
    resample_skipped = 0
    for cell_report in scores.get("cells", []):
        benchmark, cell = cell_report["benchmark"], cell_report["cell"]
        predictions = read_json(root / cell_report["predictions"])["predictions"]
        correct = 0
        malformed = 0
        counts: dict[str, int] = {}
        for position, prediction in enumerate(predictions):
            raw_output = prediction["raw_output"]
            gold = subsets["benchmarks"][benchmark]["examples"][prediction["example_id"]]["gold"]
            if benchmark == "folio":
                parsed = _audit_parse_folio(raw_output)
                is_malformed = parsed is None
                is_correct = parsed == gold["label"] if parsed is not None else False
                category = "malformed" if is_malformed else ("correct" if is_correct else "incorrect")
            elif benchmark == "gsm8k":
                parsed = _audit_parse_gsm8k(raw_output)
                is_malformed = parsed is None
                is_correct = _audit_gsm8k_equal(parsed, gold["final"]) if parsed is not None else False
                category = "malformed" if is_malformed else ("correct" if is_correct else "incorrect")
            else:
                code = _audit_extract_humaneval(raw_output)
                if not code or not _audit_defines(code, gold["entry_point"]):
                    is_malformed, is_correct, category = True, False, "malformed"
                    if prediction.get("category") != "malformed":
                        problems.append(f"{benchmark}/{cell}/{prediction['example_id']} malformed mismatch")
                else:
                    is_malformed = False
                    category = prediction["category"]
                    is_correct = category == "passed"
                if position % 10 == 0 and not is_malformed:
                    resample_planned += 1
                    if time.monotonic() - resample_started >= resample_budget_seconds:
                        resample_skipped += 1
                    else:
                        program = build_humaneval_program(code, gold["test"], gold["entry_point"])
                        execution = execute_humaneval_program(program, use_unshare=use_unshare)
                        resample_re_executed += 1
                        resample_report.append(
                            {
                                "example_id": prediction["example_id"],
                                "cell": cell,
                                "recorded": prediction["category"],
                                "reexecuted": execution["category"],
                            }
                        )
                        if (execution["category"] == "passed") != (prediction["category"] == "passed"):
                            problems.append(
                                f"{benchmark}/{cell}/{prediction['example_id']} sandbox re-execution differs"
                            )
            correct += int(is_correct)
            malformed += int(is_malformed)
            counts[category] = counts.get(category, 0) + 1
        if (
            correct != cell_report["correct"]
            or malformed != cell_report["malformed"]
            or counts != cell_report["categories"]
        ):
            problems.append(f"{benchmark}/{cell} metrics differ")
    result = {
        "schema_version": AUDIT_SCORE_SCHEMA,
        "outcome": "PASS" if not problems else "INVALID",
        "protocol_id": protocol["protocol_id"],
        "cells_reparsed": len(scores.get("cells", [])),
        "humaneval_resample": {
            "planned": resample_planned,
            "re_executed": resample_re_executed,
            "skipped_for_time": resample_skipped,
            "budget_seconds": resample_budget_seconds,
            "complete": resample_skipped == 0,
            "executions": resample_report,
        },
        "problems": problems,
        "audited_at": time.time(),
    }
    write_json(root / output_root(protocol) / "audit-score.json", result)
    if problems:
        raise RuntimeError("transfer audit-score differs: " + "; ".join(problems))
    return result


# ---------------------------------------------------------------------------
# Finalize / audit-final: rebuild summary tables from raw retained outputs
# ---------------------------------------------------------------------------


def _build_final_report(root: Path, protocol: Mapping[str, Any], *, audit: bool) -> dict[str, Any]:
    """Rebuild per-benchmark tables from raw run outputs; audit uses the duplicated parsers."""
    out = root / output_root(protocol)
    subsets = read_json(out / "subsets.json")
    admission_path = out / "admission.json"
    admission = read_json(admission_path) if admission_path.is_file() else None
    predictions_dir = out / "scores"
    benchmarks: dict[str, Any] = {}
    missing: list[dict[str, str]] = []
    for benchmark in BENCHMARK_ORDER:
        block = subsets["benchmarks"][benchmark]
        benchmarks[benchmark] = {}
        for cell in cell_order(protocol):
            final, _journal = _run_paths(root, benchmark, cell, protocol)
            if not final.is_file():
                missing.append({"benchmark": benchmark, "cell": cell})
                continue
            report = read_json(final)
            predictions_path = predictions_dir / f"predictions-{benchmark}-{cell}.jsonl.gz"
            predictions = (
                {row["example_id"]: row for row in read_json(predictions_path)["predictions"]}
                if predictions_path.is_file()
                else {}
            )
            correct = 0
            malformed = 0
            counts: dict[str, int] = {}
            for example_id in report["order"]:
                entry = report["entries"][example_id]
                raw_output = entry["raw_output"]
                gold = block["examples"][example_id]["gold"]
                retained = predictions.get(example_id)
                if retained is not None and retained.get("raw_output") != raw_output:
                    raise ValueError(f"transfer retained prediction differs from raw output: {example_id}")
                if benchmark == "humaneval":
                    if retained is None:
                        raise ValueError(f"transfer humaneval execution log is missing: {example_id}")
                    if audit:
                        code = _audit_extract_humaneval(raw_output)
                        if (not code or not _audit_defines(code, gold["entry_point"])) != (
                            retained["category"] == "malformed"
                        ):
                            raise ValueError(f"transfer humaneval malformed audit differs: {example_id}")
                    category = retained["category"]
                    is_correct = category == "passed"
                    is_malformed = category == "malformed"
                elif benchmark == "folio":
                    parsed = _audit_parse_folio(raw_output) if audit else parse_folio_prediction(raw_output)[0]
                    is_malformed = parsed is None
                    is_correct = parsed == gold["label"] if parsed is not None else False
                    category = "malformed" if is_malformed else ("correct" if is_correct else "incorrect")
                else:
                    if audit:
                        parsed = _audit_parse_gsm8k(raw_output)
                        is_correct = _audit_gsm8k_equal(parsed, gold["final"]) if parsed is not None else False
                    else:
                        parsed = parse_gsm8k_prediction(raw_output)[0]
                        is_correct = gsm8k_correct(parsed, gold["final"]) if parsed is not None else False
                    is_malformed = parsed is None
                    category = "malformed" if is_malformed else ("correct" if is_correct else "incorrect")
                if retained is not None and retained.get("category") != category:
                    raise ValueError(f"transfer score category differs from retained prediction: {example_id}")
                correct += int(is_correct)
                malformed += int(is_malformed)
                counts[category] = counts.get(category, 0) + 1
            total = len(report["order"])
            benchmarks[benchmark][cell] = {
                "examples": total,
                "correct": correct,
                "accuracy": correct / total,
                "malformed": malformed,
                "categories": counts,
                "generated_tokens_total": report["generated_tokens_total"],
                "input_tokens_total": report["input_tokens_total"],
                "latency_seconds": _cell_latency_seconds(report["entries"]),
            }
    freeze = read_json(out / "freeze.json")
    return {
        "schema_version": FINAL_SCHEMA,
        "outcome": "PASS" if not missing else "VALID_STOP",
        "protocol_id": protocol["protocol_id"],
        "admission_decision": admission.get("decision") if admission else None,
        "benchmarks": benchmarks,
        "missing": missing,
        "leakage": freeze.get("leakage"),
        "sandbox": freeze.get("sandbox"),
        "limitations": [
            "single decoding seed (17); no variance estimated",
            "Qwen3-VL-8B-Instruct pretraining data is not auditable by this project; possible base-model "
            "benchmark contamination is disclosed, not measured",
            "FOLIO is the v0.0 validation split (official public evaluation set), not the access-gated HF v2 update",
        ],
    }


def finalize_stage(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    report = _build_final_report(root, protocol, audit=False)
    path = root / output_root(protocol) / "final-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def audit_final_stage(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Independent rebuild; requires byte-equality with final-report.json."""
    rebuilt = _build_final_report(root, protocol, audit=True)
    path = root / output_root(protocol) / "final-report.json"
    expected = (json.dumps(rebuilt, indent=2) + "\n").encode()
    actual = path.read_bytes()
    result = {
        "schema_version": AUDIT_FINAL_SCHEMA,
        "outcome": "PASS" if actual == expected else "INVALID",
        "protocol_id": protocol["protocol_id"],
        "byte_equal": actual == expected,
        "audited_at": time.time(),
    }
    write_json(root / output_root(protocol) / "audit-final.json", result)
    if actual != expected:
        raise RuntimeError("transfer final report differs from the independent audit rebuild")
    return result


# ---------------------------------------------------------------------------
# Analyze + publish
# ---------------------------------------------------------------------------


def _extension_base_rows(root: Path, protocol: Mapping[str, Any], admission: Mapping[str, Any]) -> dict[str, Any]:
    """v1 per-benchmark rows when an extension's admission level matches v1's (paired subsets); else {}."""
    if not protocol.get("extends"):
        return {}
    path = root / OUTPUT_ROOT / "final-report.json"
    if not path.is_file():
        return {}
    report = read_json(path)
    if report.get("protocol_id") != protocol["extends"]:
        return {}
    if report.get("admission_decision") != admission.get("decision"):
        return {}
    return report.get("benchmarks", {})


def analyze_stage(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    out = root / output_root(protocol)
    path = out / "final-report.json"
    report = read_json(path) if path.is_file() else None
    admission = read_json(out / "admission.json")
    extension = protocol.get("extends")
    v1_rows = _extension_base_rows(root, protocol, admission)
    contrasts: list[dict[str, Any]] = []
    if report is not None and report.get("benchmarks"):
        for benchmark in BENCHMARK_ORDER:
            cells = report["benchmarks"].get(benchmark, {})
            base_row = cells.get("base")
            base_source = "final-report.json"
            if base_row is None:
                base_row = v1_rows.get(benchmark, {}).get("base")
                base_source = f"{OUTPUT_ROOT}/final-report.json (v1 base cell, same frozen subsets and level)"
            if base_row is None:
                continue
            for cell in adapted_cells(protocol):
                row = cells.get(cell)
                if row is None or row["examples"] != base_row["examples"]:
                    continue
                contrasts.append(
                    {
                        "benchmark": benchmark,
                        "cell": cell,
                        "accuracy": row["accuracy"],
                        "base_accuracy": base_row["accuracy"],
                        "delta_vs_base": row["accuracy"] - base_row["accuracy"],
                        "malformed": row["malformed"],
                        "base_source": base_source,
                    }
                )
    contract = (
        "descriptive zero-shot transfer deltas per cell vs base; no adapter selection or rerun by "
        "transfer-test success"
    )
    if extension:
        contract += (
            "; extension authorized after v1 results were observed (disclosed in the protocol and the "
            "published narrative); base values are the v1 base cell on identical frozen subsets when the "
            "admission levels match"
        )
    result = {
        "schema_version": ANALYSIS_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "admission_decision": admission.get("decision"),
        "contrasts": contrasts,
        "comparison_contract": contract,
        "limitations": (report or {}).get("limitations", []),
    }
    if extension:
        result["extends"] = extension
    write_json(out / "analysis.json", result)
    return result


def _fmt_sha(value: str | None) -> str:
    if not value:
        return "—"
    return value[:20] + "…"


def _write_markdown(path: Path, title: str, lines: Sequence[str]) -> None:
    path.write_text(f"# {title}\n\n" + "\n".join(lines).strip() + "\n")


def _copy_evidence(root: Path, source: Path, name: str) -> Path:
    target = root / DOCS_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def publish(root: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Copy compact byte-identical evidence JSONs and render the Markdown narrative."""
    out = root / output_root(protocol)
    stem = doc_stem(protocol)
    admission = read_json(out / "admission.json")
    freeze = read_json(out / "freeze.json")
    targets = [
        str(_copy_evidence(root, out / "freeze.json", f"{stem}-protocol-checks.json").relative_to(root)),
        str(_copy_evidence(root, out / "admission.json", f"{stem}-admission.json").relative_to(root)),
    ]
    if admission.get("decision") in ("L0", "L1") and (out / "scores.json").is_file():
        targets.append(str(_copy_evidence(root, out / "scores.json", f"{stem}-scores.json").relative_to(root)))
        if (out / "final-report.json").is_file():
            targets.append(
                str(_copy_evidence(root, out / "final-report.json", f"{stem}-final-report.json").relative_to(root))
            )
        targets.append(str(_publish_results(root, protocol, freeze, admission).relative_to(root)))
    else:
        targets.append(str(_publish_valid_stop(root, protocol, freeze, admission).relative_to(root)))
    result = {
        "schema_version": PUBLISH_SCHEMA,
        "outcome": "PASS",
        "protocol_id": protocol["protocol_id"],
        "published": targets,
        "published_at": time.time(),
    }
    write_json(out / "publish.json", result)
    return result


def _subset_lines(freeze: Mapping[str, Any]) -> list[str]:
    lines = [
        "| Benchmark | L0 | L1 | Strata | L0 order sha256 |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for benchmark in BENCHMARK_ORDER:
        block = freeze["subsets"][benchmark]
        seats = block.get("strata_seats", {})
        lines.append(
            f"| {benchmark} | {block['l0_size']} | {block['l1_size']} | "
            f"{json.dumps(seats, sort_keys=True)} | `{_fmt_sha(block['l0_order_sha256'])}` |"
        )
    return lines


def _publish_results(
    root: Path, protocol: Mapping[str, Any], freeze: Mapping[str, Any], admission: Mapping[str, Any]
) -> Path:
    out = root / output_root(protocol)
    stem = doc_stem(protocol)
    extension = protocol.get("extends")
    order = cell_order(protocol)
    report = read_json(out / "final-report.json")
    scores = read_json(out / "scores.json")
    leakage = freeze["leakage"]
    v1_rows = _extension_base_rows(root, protocol, admission)
    if extension:
        cell_list = ", ".join(f"`{cell}`" for cell in order)
        lines = [
            f"Zero-shot transfer of the remaining planning-trained adapters for `{protocol['protocol_id']}` "
            f"(admission decision **{admission['decision']}**), extending `{extension}`.",
            "",
            f"Cells: {cell_list}. The base cell was already run under v1 and is not rerun; v1 base values "
            "are referenced where the admission levels match. Greedy decoding, seed 17, fp32; per-benchmark "
            "max_new_tokens folio 64 / gsm8k 512 / humaneval 768.",
            "",
            "## Extension provenance",
            "",
            protocol.get("extension_rationale", ""),
            "",
            "- Extension timing: this extension was authorized **after** the v1 BFS transfer results were "
            "observed; it is exhaustive over every remaining verified trained cell, so it does not select "
            "adapters by observed transfer success.",
            "- v1 base/BFS evidence: [transfer-results.md](transfer-results.md); v1 evidence is never "
            "overwritten.",
            "",
            "## Frozen subsets",
            "",
            *_subset_lines(freeze),
            "",
            "Subsets are the v1 frozen subsets reused byte-identically (sha256 "
            f"`{freeze.get('subsets_reference', {}).get('sha256', '—')}`), verified at freeze; no "
            "re-selection and no re-derivation.",
            "",
            "## Results",
            "",
            "| Benchmark | Cell | Examples | Correct | Accuracy/pass@1 | Malformed | Categories |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    else:
        lines = [
            f"Zero-shot transfer of planning-trained BFS LoRA adapters for `{protocol['protocol_id']}` "
            f"(admission decision **{admission['decision']}**).",
            "",
            "Cells: base Qwen3-VL-8B-Instruct plus the `bfs_text`, `bfs_visual` and `bfs_multimodal` adapters; "
            "greedy decoding, seed 17, fp32; per-benchmark max_new_tokens folio 64 / gsm8k 512 / humaneval 768.",
            "",
            "## Frozen subsets",
            "",
            *_subset_lines(freeze),
            "",
            "Subset selection used label strata (folio), reasoning-step quartiles (gsm8k) and full coverage "
            "(humaneval) only — never model outcomes. L1 is the even-numbered positions of each frozen L0 order.",
            "",
            "## Results",
            "",
            "| Benchmark | Cell | Examples | Correct | Accuracy/pass@1 | Malformed | Categories |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    for benchmark in BENCHMARK_ORDER:
        base_row = v1_rows.get(benchmark, {}).get("base")
        if base_row is not None:
            lines.append(
                f"| {benchmark} | base (v1 reference) | {base_row['examples']} | {base_row['correct']} | "
                f"{base_row['accuracy']:.4f} | {base_row['malformed']} | "
                f"{json.dumps(base_row['categories'], sort_keys=True)} |"
            )
        for cell in order:
            row = report["benchmarks"].get(benchmark, {}).get(cell)
            if row is None:
                lines.append(f"| {benchmark} | {cell} | 0 | — | — | — | missing |")
                continue
            lines.append(
                f"| {benchmark} | {cell} | {row['examples']} | {row['correct']} | {row['accuracy']:.4f} | "
                f"{row['malformed']} | {json.dumps(row['categories'], sort_keys=True)} |"
            )
    if extension and not v1_rows:
        lines += [
            "",
            "v1 base values are not paired with this extension's admission level; see "
            "[transfer-results.md](transfer-results.md) for the v1 base cell.",
        ]
    lines += [
        "",
        "## Costs",
        "",
        "| Benchmark | Cell | Generated tokens | Input tokens | Latency (s) |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for benchmark in BENCHMARK_ORDER:
        for cell in order:
            row = report["benchmarks"].get(benchmark, {}).get(cell)
            if row is None:
                continue
            lines.append(
                f"| {benchmark} | {cell} | {row['generated_tokens_total']} | {row['input_tokens_total']} | "
                f"{row['latency_seconds']:.1f} |"
            )
    lines += [
        "",
        f"Admission measured probe inputs: {json.dumps(admission['measured_inputs']['p95_seconds_per_example'])} "
        f"seconds/example p95; model load {admission['measured_inputs']['model_load_seconds']:.1f}s; probe "
        f"{admission['measured_inputs']['probe_gpu_hours']:.3f} GPU-h.",
        "",
        "## Missingness",
        "",
        f"Missing (benchmark, cell) coverage: {json.dumps(report['missing'])}. "
        f"Scores outcome: {scores['outcome']}; final report outcome: {report['outcome']}.",
        "",
        "## Leakage check",
        "",
        f"Normalized-token 8-gram containment of every frozen benchmark input against the full "
        f"issue74-matched-32k-v1 SFT corpus ({leakage['records_scanned']} records): "
        f"**{leakage['items_with_shared_ngrams']}** benchmark items share an 8-gram (details in leakage.json).",
        "",
        "## Limitations",
        "",
        "- Single decoding seed (17); no variance estimated.",
        "- Qwen3-VL-8B-Instruct pretraining data is not auditable by this project; possible base-model "
        "benchmark contamination is disclosed, not measured.",
        "- FOLIO is the v0.0 validation split (the official public evaluation set; test labels unreleased), "
        "not the access-gated HF yale-nlp/FOLIO v2 update.",
    ]
    if extension:
        lines.append(
            "- This extension was authorized after the v1 BFS transfer results were observed; the timing is "
            "disclosed in Extension provenance and contrasts reference the v1 base cell."
        )
    lines += [
        "",
        f"Compact evidence: [{stem}-protocol-checks.json]({stem}-protocol-checks.json), "
        f"[{stem}-admission.json]({stem}-admission.json), "
        f"[{stem}-scores.json]({stem}-scores.json) and "
        f"[{stem}-final-report.json]({stem}-final-report.json) (byte-identical copies).",
    ]
    path = root / DOCS_DIR / f"{stem}-results.md"
    title = "Transfer benchmark results (#104-#107)" if not extension else "Transfer extension results (#104-#107)"
    _write_markdown(path, title, lines)
    return path


def _publish_valid_stop(
    root: Path, protocol: Mapping[str, Any], freeze: Mapping[str, Any], admission: Mapping[str, Any]
) -> Path:
    stem = doc_stem(protocol)
    extension = protocol.get("extends")
    arithmetic = admission["arithmetic"]
    if extension:
        protocol_line = f"- Protocol: `{protocol['protocol_id']}`, extending `{extension}`."
    else:
        protocol_line = f"- Protocol: `{protocol['protocol_id']}` (`{PROTOCOL_FILE}`)."
    lines = [
        f"The `transfer` branch is terminal **{admission['outcome']}** at the frozen cost-admission gate "
        f"(decision **{admission['decision']}**). No transfer evaluation was launched; the only GPU work was "
        "the outcome-blind runtime probe. This is a terminal evidence publication, not a ticket-completion claim.",
        "",
        f"- Branch: `transfer`, {admission['branch_cap_gpu_hours']} GPU-h cap; spent "
        f"{admission['branch_spent_gpu_hours']:.4f}; remainder {admission['branch_remainder_gpu_hours']:.4f}.",
        protocol_line,
        f"- Base model: `{protocol['base_model']['model_id']}` @ `{protocol['base_model']['revision']}`.",
    ]
    if extension:
        lines += [
            "",
            "Extension timing: this extension was authorized **after** the v1 BFS transfer results were "
            "observed; it is exhaustive over every remaining verified trained cell and does not select "
            "adapters by observed transfer success.",
        ]
    lines += [
        "",
        "## Frozen subsets",
        "",
        *_subset_lines(freeze),
        "",
        "## Admission arithmetic",
        "",
        f"Basis: per benchmark p95 probe seconds/example x subset size x {len(cell_order(protocol))} cells "
        "plus one measured model load "
        f"per worker, times safety factor {arithmetic['L0']['safety_factor']}.",
        "",
        "| Level | Required GPU-h | Required wall-h | Fits remainder | Fits cutoff |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for level in ("L0", "L1"):
        row = arithmetic[level]
        lines.append(
            f"| {level} | {row['required_gpu_hours']:.3f} | {row['required_wall_seconds'] / 3600:.3f} | "
            f"{row['fits_branch_remainder']} | {row['fits_absolute_cutoff']} |"
        )
    leakage = freeze["leakage"]
    lines += [
        "",
        "## Leakage check",
        "",
        f"Normalized-token 8-gram containment against the full SFT corpus ({leakage['records_scanned']} "
        f"records): **{leakage['items_with_shared_ngrams']}** benchmark items share an 8-gram.",
        "",
        "## Limitations",
        "",
        "- Single decoding seed (17); no variance estimated.",
        "- Qwen3-VL-8B-Instruct pretraining data is not auditable by this project; possible base-model "
        "benchmark contamination is disclosed, not measured.",
        "- FOLIO is the v0.0 validation split, not the access-gated HF yale-nlp/FOLIO v2 update.",
        "",
        f"Compact evidence: [{stem}-protocol-checks.json]({stem}-protocol-checks.json) and "
        f"[{stem}-admission.json]({stem}-admission.json) (byte-identical copies).",
    ]
    path = root / DOCS_DIR / f"{stem}-valid-stop.md"
    title = "Transfer terminal VALID_STOP (#104-#107)"
    if extension:
        title = "Transfer extension terminal VALID_STOP (#104-#107)"
    _write_markdown(path, title, lines)
    return path
