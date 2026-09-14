#!/usr/bin/env python
"""Select first reference-eligible non-isomorphic candidates in frozen seed order."""

from collections import defaultdict
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.task_isomorphism import context_shape, same_instance


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=("select", "audit"), nargs="?", default="select")
    parser.add_argument("--protocol", type=Path, default=ROOT / "configs/experiments/expanded-study/panel-protocol.json")
    args = parser.parse_args()
    protocol = read(args.protocol)
    path = ROOT / protocol["output_root"] / "structural-selection.json"
    if args.stage == "audit":
        terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
        if terminal["status"] != "succeeded":
            raise RuntimeError(f"selection failed: {terminal['directory']}/worker.log")
        report = read(path)
        assert len(report["strata"]) == 24
        assert report["selected_count"] + len(report["missing_strata"]) == 24
        assert all(
            g["selected"] is None or g["decisions"][-1]["disposition"] == "selected_pending_input_qualification"
            for g in report["strata"]
        )
        write(
            ROOT / f"docs/experiments/expanded-study/panel-structural-selection-{protocol['study_id']}.json",
            dict(
                selected_count=report["selected_count"],
                target_count=24,
                missing_strata=report["missing_strata"],
                final_membership_frozen=False,
                hardware_qualified=False,
                report=str(path.relative_to(ROOT)),
            ),
        )
        print("PASS: structural selection coverage; missing strata retained, hardware qualification pending")
        return
    pool = read(ROOT / protocol["output_root"] / "reference-screen.json")
    if pool["protocol"] != protocol:
        raise ValueError("screening differs from frozen protocol")
    historical = read(ROOT / protocol["historical_inventory"])
    index = defaultdict(list)
    for number, raw in enumerate(historical["task_semantics"]):
        context = json.loads(raw)
        index[context_shape(context)].append((number, context))
    strata = []
    selected = []
    for group in pool["strata"]:
        record = dict(domain=group["domain"], stratum=group["stratum"], selected=None, decisions=[])
        for candidate in group["candidates"]:
            decision = dict(seed=candidate["seed"], disposition=candidate["reason"])
            record["decisions"].append(decision)
            if not candidate["reference_eligible"]:
                continue
            task = read(ROOT / candidate["task_path"])
            context = PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"]).task_context()
            match = next((n for n, c in index[context_shape(context)] if same_instance(context, c)), None)
            if match is not None:
                decision.update(disposition="historical_object_renaming_overlap", historical_context_index=match)
                continue
            if any(same_instance(context, c) for c in selected):
                decision["disposition"] = "within_panel_object_renaming_overlap"
                continue
            selected.append(context)
            record["selected"] = candidate
            decision["disposition"] = "selected_pending_input_qualification"
            break
        strata.append(record)
        write(os.environ["EXPANDED_PROGRESS_PATH"], dict(completed=len(strata)))
        print(
            dict(
                domain=group["domain"],
                stratum=group["stratum"],
                selected=record["selected"]["seed"] if record["selected"] else None,
            ),
            flush=True,
        )
    missing = [
        dict(domain=g["domain"], stratum=g["stratum"], reason="frozen_seed_pool_exhausted")
        for g in strata
        if g["selected"] is None
    ]
    write(
        path,
        dict(
            protocol=protocol,
            strata=strata,
            selected_count=len(selected),
            missing_strata=missing,
            historical_contexts_compared=len(historical["task_semantics"]),
            final_membership_frozen=False,
            hardware_qualified=False,
            model_calls=0,
        ),
    )


if __name__ == "__main__":
    main()
