#!/usr/bin/env python
"""Run, audit, and publish the expanded transfer (#104-#107) branch."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.planning_benchmark_slice import expanded_transfer as branch
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write

PROTOCOL = ROOT / "configs/experiments/expanded-study/transfer-protocol.json"


def _head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def require_worker_environment(worker):
    if worker not in (0, 1):
        raise ValueError("transfer worker is outside the frozen mapping")
    expected_gpu = str(branch.WORKER_GPUS[worker])
    if os.environ.get("CUDA_VISIBLE_DEVICES") != expected_gpu:
        raise ValueError("transfer worker GPU differs from frozen mapping")
    try:
        port = int(os.environ["MASTER_PORT"])
    except (KeyError, ValueError) as error:
        raise ValueError("transfer worker MASTER_PORT is missing or invalid") from error
    if port not in branch.PORT_POOL:
        raise ValueError("transfer worker MASTER_PORT is outside the frozen pool")
    return port


def _progress_path(stage):
    configured = os.environ.get("EXPANDED_PROGRESS_PATH")
    if configured:
        return Path(configured)
    path = ROOT / branch.OUTPUT_ROOT / f"progress-{stage}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_progress(path, values):
    write(Path(path), values)
    print(json.dumps({"stage": "transfer", **values}), flush=True)


def _progress(stage):
    path = _progress_path(stage)

    def progress(**values):
        _write_progress(path, values)

    return progress, path


def _attempt_dir():
    configured = os.environ.get("EXPANDED_ATTEMPT_DIR")
    if configured:
        return Path(configured)
    path = ROOT / branch.OUTPUT_ROOT / "direct-attempt"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _terminal():
    configured = os.environ.get("EXPANDED_TERMINAL_PATH")
    return read(configured) if configured else None


def validate(protocol):
    report = branch.validate_protocol(ROOT, protocol)
    print(json.dumps(report, indent=2))


def freeze(protocol):
    progress, path = _progress("freeze")
    result = branch.freeze_stage(ROOT, protocol, progress=progress)
    write(path, {"completed": 6, "total": 6, "terminal": True})
    summary = {"outcome": result["outcome"], "subsets": {k: v["l0_size"] for k, v in result["subsets"].items()}}
    print(json.dumps(summary, indent=2))


def audit_freeze(protocol):
    terminal = _terminal()
    if terminal is not None and terminal.get("status") != "succeeded":
        raise RuntimeError("transfer freeze job did not succeed")
    result = branch.audit_freeze_stage(ROOT, protocol)
    print(json.dumps({"outcome": result["outcome"]}, indent=2))


def probe(protocol):
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0":
        raise ValueError("transfer probe GPU differs from frozen mapping")
    if "MASTER_PORT" in os.environ and int(os.environ["MASTER_PORT"]) not in branch.PORT_POOL:
        raise ValueError("transfer probe MASTER_PORT is outside the frozen pool")
    progress, path = _progress("probe")
    result = branch.probe_stage(ROOT, protocol, attempt_dir=_attempt_dir(), progress=progress)
    write(path, {"completed": 12, "total": 12, "terminal": True})
    print(json.dumps({"outcome": result["outcome"], "probe_gpu_hours": result["probe_gpu_hours"]}, indent=2))


def audit_probe(protocol):
    terminal = _terminal()
    if terminal is not None and terminal.get("status") != "succeeded":
        raise RuntimeError("transfer probe job did not succeed")
    attempt_probe = _attempt_dir() / "probe.json"
    evidence = read(attempt_probe) if attempt_probe.is_file() else read(ROOT / branch.OUTPUT_ROOT / "probe.json")
    result = branch.audit_probe_stage(ROOT, protocol, evidence)
    print(json.dumps({"outcome": result["outcome"]}, indent=2))


def admit(protocol):
    result = branch.admit_stage(ROOT, protocol)
    print(json.dumps({"decision": result["decision"], "outcome": result["outcome"]}, indent=2))


def run(protocol, worker):
    require_worker_environment(worker)
    progress, path = _progress(f"run-{worker}")
    result = branch.run_worker(ROOT, protocol, worker, attempt_dir=_attempt_dir(), progress=progress)
    total = len(result["cells"]) and sum(row["examples"] for row in result["cells"])
    write(path, {"completed": total, "total": total, "terminal": True})
    print(json.dumps({"outcome": result["outcome"], "examples": result["examples_completed"]}, indent=2))


def audit_run_worker(protocol, worker):
    terminal = _terminal()
    if terminal is None:
        raise RuntimeError("transfer audit-run-worker requires EXPANDED_TERMINAL_PATH")
    result = branch.audit_run_worker(ROOT, protocol, worker, terminal=terminal)
    print(json.dumps({"outcome": result["outcome"], "cells": len(result["cells_audited"])}, indent=2))


def score(protocol):
    progress, path = _progress("score")
    result = branch.score_stage(ROOT, protocol, progress=progress)
    write(path, {"completed": 1, "total": 1, "terminal": True})
    print(json.dumps({"outcome": result["outcome"], "cells": len(result["cells"])}, indent=2))


def audit_score(protocol):
    terminal = _terminal()
    if terminal is not None and terminal.get("status") != "succeeded":
        raise RuntimeError("transfer score job did not succeed")
    result = branch.audit_score_stage(ROOT, protocol)
    print(json.dumps({"outcome": result["outcome"], "cells": result["cells_reparsed"]}, indent=2))


def finalize(protocol):
    result = branch.finalize_stage(ROOT, protocol)
    print(json.dumps({"outcome": result["outcome"], "missing": len(result["missing"])}, indent=2))


def audit_final(protocol):
    terminal = _terminal()
    if terminal is not None and terminal.get("status") != "succeeded":
        raise RuntimeError("transfer finalize job did not succeed")
    result = branch.audit_final_stage(ROOT, protocol)
    print(json.dumps({"outcome": result["outcome"]}, indent=2))


def analyze(protocol):
    result = branch.analyze_stage(ROOT, protocol)
    print(json.dumps({"outcome": result["outcome"], "contrasts": len(result["contrasts"])}, indent=2))


def publish(protocol):
    result = branch.publish(ROOT, protocol)
    print(json.dumps(result, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "validate",
            "freeze",
            "audit-freeze",
            "probe",
            "audit-probe",
            "admit",
            "run",
            "audit-run-worker",
            "score",
            "audit-score",
            "finalize",
            "audit-final",
            "analyze",
            "publish",
        ),
    )
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--worker", type=int, choices=(0, 1))
    args = parser.parse_args(argv)
    protocol = read(args.protocol)
    if args.stage in {"run", "audit-run-worker"} and args.worker is None:
        parser.error(f"{args.stage} requires --worker")
    {
        "validate": lambda: validate(protocol),
        "freeze": lambda: freeze(protocol),
        "audit-freeze": lambda: audit_freeze(protocol),
        "probe": lambda: probe(protocol),
        "audit-probe": lambda: audit_probe(protocol),
        "admit": lambda: admit(protocol),
        "run": lambda: run(protocol, args.worker),
        "audit-run-worker": lambda: audit_run_worker(protocol, args.worker),
        "score": lambda: score(protocol),
        "audit-score": lambda: audit_score(protocol),
        "finalize": lambda: finalize(protocol),
        "audit-final": lambda: audit_final(protocol),
        "analyze": lambda: analyze(protocol),
        "publish": lambda: publish(protocol),
    }[args.stage]()


if __name__ == "__main__":
    main()
