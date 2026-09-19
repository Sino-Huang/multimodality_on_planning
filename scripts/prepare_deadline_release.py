"""Package terminal experiment evidence and selected replay assets for #108."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.visual_experiment import ALGORITHMS, VisualExperiment
from scripts.run_visual_issue75 import heartbeat, log


def selected_task_files(root, row, view_manifest):
    """Files needed by the trusted runtime and readable views for one selected task."""
    files = {view_manifest, *row["trace_paths"].values()}
    if row["task_id"].startswith("astar-pair-"):
        files.add(str(Path(next(iter(row["trace_paths"].values()))).parent / "task.json"))
    else:
        family, instance = row["task_id"].split("/", 1)
        manifest = (
            "data/bfs_pilot_v6/selected-manifest.jsonl"
            if family == "bfs"
            else "data/bfws_phase_v1/development-manifest.jsonl"
        )
        files.add(manifest)
        source = next(
            r for r in map(json.loads, (root / manifest).read_text().splitlines()) if r["instance_id"] == instance
        )
        files.update((source["domain_path"], source["problem_path"]))
    manifest = read_json(root / view_manifest)
    files.add(manifest["scene_catalog"])
    catalog = read_json(root / manifest["scene_catalog"])
    files.update(state["scene_path"] for state in catalog["states"])
    for pages in manifest["reusable_pages"].values():
        files.update(pages)
    return files


def inventory(configs):
    files, runs, checkpoints = set(), [], []
    for config_path in configs:
        e = VisualExperiment(config_path)
        root = e.output
        if not (root / "result.json").exists():
            raise ValueError(f"cannot export a live or absent experiment: {root}")
        attempt = read_json(root / "attempt.json")
        if (
            attempt["experiment"] != e.config
            or attempt.get("pilot_manifest") != e.pilot
            or attempt.get("cost_panel") != e.cost_panel
        ):
            raise ValueError("export configuration differs from the retained attempt")
        selected = (
            e.pilot["selected_task_ids"]
            if e.pilot
            else e.cost_panel["selected_task_ids"] if e.cost_panel else [r["task_id"] for r in e.dev]
        )
        rows = [r for r in e.dev if r["task_id"] in selected]
        panel = e.corpus.contract["panel_manifest"]
        files.update((str(config_path.resolve().relative_to(ROOT)), e.config["corpus_report"], panel))
        for key in ("pilot_manifest", "cost_panel"):
            if e.config.get(key):
                files.add(e.config[key])
        if e.config.get("qualification_source"):
            source = ROOT / e.config["qualification_source"]
            files.update((str(source.relative_to(ROOT)), str((source.parent / "attempt.json").relative_to(ROOT))))
            files.update(str(p.relative_to(ROOT)) for p in (source.parent / "qualification").rglob("*.json"))
        episode_paths = []
        for path in root.rglob("*"):
            if not path.is_file() or "training" in path.relative_to(root).parts:
                continue
            relative = str(path.relative_to(ROOT))
            files.add(relative)
            if path.name.startswith("episode-") and path.name.endswith(".json.gz"):
                episode_paths.append(relative)
        for algorithm in ALGORITHMS:
            report = root / "training" / f"{algorithm}.json"
            if report.exists():
                files.add(str(report.relative_to(ROOT)))
            final = root / "training" / algorithm / "final"
            if not report.exists() or read_json(report).get("outcome") != "PASS":
                continue
            weights = final / "adapter_model.safetensors"
            config = final / "adapter_config.json"
            if not weights.is_file() or not config.is_file():
                raise ValueError("completed training report lacks final adapter files")
            files.add(str(config.relative_to(ROOT)))
            checkpoints.append(
                {
                    "issue": e.config["source_issue"],
                    "algorithm": algorithm,
                    "path": str(weights.relative_to(ROOT)),
                    "adapter_config": str(config.relative_to(ROOT)),
                    "asset_name": f"issue{e.config['source_issue']}-{algorithm}-adapter.safetensors",
                    "bytes": weights.stat().st_size,
                }
            )
        for i, row in enumerate(rows):
            files.update(selected_task_files(ROOT, row, e.corpus.results[row["task_id"]]["view_manifest"]))
            log("export:task", completed=i + 1, total=len(rows), issue=e.config["source_issue"])
        runs.append(
            {
                "issue": e.config["source_issue"],
                "contract_id": e.config["contract_id"],
                "config": str(config_path.resolve().relative_to(ROOT)),
                "output_root": str(root.relative_to(ROOT)),
                "panel_manifest": panel,
                "corpus_report": e.config["corpus_report"],
                "episode_paths": sorted(episode_paths),
                "training_record_ids": (
                    e.pilot["training_record_ids"]
                    if e.pilot
                    else {
                        algorithm: [r["record_id"] for r in e.corpus.records(algorithm=algorithm, split="train")]
                        for algorithm in ALGORITHMS
                    }
                ),
                "terminal_outcome": read_json(root / "result.json")["outcome"],
            }
        )
    assets = []
    for name in sorted(files):
        path = ROOT / name
        if not path.is_file():
            raise ValueError(f"missing declared replay asset: {name}")
        assets.append({"path": name, "bytes": path.stat().st_size})
    return {
        "schema": "deadline_replay_release_v1",
        "runs": runs,
        "assets": assets,
        "checkpoints": checkpoints,
        "scope": "retained episode replay and final adapters; not a full training-corpus mirror",
        "base_model_included": False,
        "original_experiment_outputs_modified": False,
        "base_model": {"id": e.config["model_id"], "revision": e.config["model_revision"]},
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python_version": sys.version.split()[0],
        "python_packages": {
            name: importlib.metadata.version(name)
            for name in (
                "torch",
                "torchvision",
                "transformers",
                "tokenizers",
                "peft",
                "accelerate",
                "plado",
                "Pillow",
                "numpy",
                "huggingface-hub",
                "safetensors",
            )
        },
    }


def package(index, output):
    if any(output.resolve().is_relative_to(ROOT / run["output_root"]) for run in index["runs"]):
        raise ValueError("release output must be separate from original experiments")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "replay-assets.tar.gz"
    if archive.exists() or (output / "index.json").exists():
        raise ValueError("release output already exists; preserve it and choose a fresh directory")
    with tarfile.open(archive, "w:gz", compresslevel=1, dereference=True) as tar:
        for i, asset in enumerate(index["assets"]):
            tar.add(ROOT / asset["path"], arcname=asset["path"], recursive=False)
            if (i + 1) % 500 == 0 or i + 1 == len(index["assets"]):
                log("export:archive", completed=i + 1, total=len(index["assets"]))
    # Unique upload names reference existing final weights; do not duplicate model files.
    for checkpoint in index["checkpoints"]:
        (output / checkpoint["asset_name"]).symlink_to(ROOT / checkpoint["path"])
    index["archive"] = {"file": archive.name, "bytes": archive.stat().st_size}
    (output / "index.json").write_text(json.dumps(index, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    index = heartbeat(lambda: inventory(args.config), "export")
    if not args.dry_run:
        heartbeat(lambda: package(index, args.output), "export")
    log(
        "export:complete",
        outcome="PASS",
        dry_run=args.dry_run,
        completed=len(index["assets"]),
        total=len(index["assets"]),
        replay_asset_bytes=sum(a["bytes"] for a in index["assets"]),
        checkpoint_bytes=sum(a["bytes"] for a in index["checkpoints"]),
        checkpoints=len(index["checkpoints"]),
        episodes=sum(len(r["episode_paths"]) for r in index["runs"]),
        elapsed_seconds=round(time.monotonic() - started, 2),
    )


if __name__ == "__main__":
    main()
