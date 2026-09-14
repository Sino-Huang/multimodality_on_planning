#!/usr/bin/env python
"""Run frozen reference screening in CPU workers, retaining every disposition."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_candidates import screen
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write

PROTOCOL = ROOT / "configs/experiments/expanded-study/panel-protocol.json"


def screen_stratum(protocol, profile, exclusions):
    results = []
    for seed in profile["seeds"]:
        result = screen(ROOT, protocol, profile, seed, exclusions)
        results.append(
            {
                k: result.get(k)
                for k in ("seed", "reference_eligible", "reason", "row", "task_path", "grounding_estimate")
            }
        )
        print(dict(domain=profile["domain"], stratum=profile["stratum"], seed=seed, reason=result["reason"]), flush=True)
    return dict(domain=profile["domain"], stratum=profile["stratum"], candidates=results)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("screen", "audit"))
    args = parser.parse_args()
    protocol = read(PROTOCOL)
    path = ROOT / protocol["output_root"] / "reference-screen.json"
    if args.stage == "audit":
        terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
        if terminal["status"] != "succeeded":
            raise RuntimeError(f"reference screening failed: inspect {terminal['directory']}/worker.log")
        report = read(path)
        expected = {(p["domain"], p["stratum"]): p["seeds"] for p in protocol["strata"]}
        assert report["protocol"] == protocol
        assert len(report["strata"]) == len(expected) == 24
        for group in report["strata"]:
            assert [c["seed"] for c in group["candidates"]] == expected[group["domain"], group["stratum"]]
            for candidate in group["candidates"]:
                if candidate["reference_eligible"]:
                    assert set(candidate["row"]["reference_costs"]) == set(protocol["reference"]["algorithms"])
        compact = dict(
            status="reference_screen_complete_selection_and_qualification_pending",
            strata=[
                dict(
                    domain=g["domain"],
                    stratum=g["stratum"],
                    reference_eligible=sum(c["reference_eligible"] for c in g["candidates"]),
                    reasons=dict(Counter(c["reason"] for c in g["candidates"])),
                )
                for g in report["strata"]
            ],
            model_calls=0,
            report=str(path.relative_to(ROOT)),
        )
        write(ROOT / "docs/experiments/expanded-study/panel-reference-screen.json", compact)
        print("PASS: every frozen candidate has a reference-screen disposition; final panel not yet qualified")
        return
    exclusions = set(read(ROOT / protocol["historical_inventory"])["task_semantics"])
    groups = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(screen_stratum, protocol, p, exclusions) for p in protocol["strata"]]
        for future in as_completed(futures):
            groups.append(future.result())
            completed = sum(len(g["candidates"]) for g in groups)
            if os.environ.get("EXPANDED_PROGRESS_PATH"):
                write(os.environ["EXPANDED_PROGRESS_PATH"], dict(completed=completed))
            print(dict(completed=completed, total=sum(len(p["seeds"]) for p in protocol["strata"])), flush=True)
    order = {(p["domain"], p["stratum"]): i for i, p in enumerate(protocol["strata"])}
    groups.sort(key=lambda g: order[g["domain"], g["stratum"]])
    write(path, dict(protocol=protocol, strata=groups, final_membership_frozen=False, model_calls=0))


if __name__ == "__main__":
    main()
