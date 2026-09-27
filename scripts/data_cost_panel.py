#!/usr/bin/env python
"""#147 data-cost evaluation panel: screen -> select -> views -> freeze -> audit.

Every stage is resumable: screened candidates, prepared task views and the frozen membership are
retained and reused when the protocol is unchanged. `all` runs every stage in order.
Views need the Planimation backend on the protocol endpoints:
  .cache/issue70-backend-venv/bin/python scripts/serve_issue70_planimation.py --port 18094 --workers 2
"""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.data_cost_panel import (
    SELECTED,
    exclusion_inventory,
    membership_sha256,
    select_strata,
)
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.expanded_views import reference_catalog
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.scene_profiles import compact_grid_vfg
from scripts.prepare_expanded_views import prepare_task
from scripts.screen_expanded_panel import screen_stratum

PROTOCOL = ROOT / "configs/experiments/data-cost/panel-protocol.json"
PANEL = ROOT / "configs/experiments/data-cost/panel.json"
SNAPSHOTS = ROOT / "configs/experiments/data-cost/tasks"
SUMMARY = ROOT / "docs/experiments/data-cost/panel-summary.json"
V2_PROTOCOL = ROOT / "configs/experiments/expanded-study/panel-protocol-v2.json"
REPAIRS = {"scene_profiles.compact_grid_vfg": compact_grid_vfg}


def log(stage, **fields):
    print(json.dumps(dict(stage=stage, **fields), default=str), flush=True)


def paths(protocol):
    root = ROOT / protocol["output_root"]
    return dict(
        inventory=root / "exclusion-inventory.json",
        screen=root / "reference-screen.json",
        selection=root / "structural-selection.json",
        views=ROOT / protocol["views"]["view_report"],
    )


def retained(path, protocol):
    """Return a finished stage report, refusing one produced under another protocol."""
    if not path.exists():
        return None
    report = read(path)
    if report["protocol"] != protocol:
        raise ValueError(f"{path.relative_to(ROOT)} was produced under a different protocol")
    return report


def inventory(protocol):
    path = paths(protocol)["inventory"]
    report = retained(path, protocol)
    if report is None:

        def progress(stage, completed, total):
            if completed % 50 == 0 or completed == total:
                log(stage, completed=completed, total=total)

        report = exclusion_inventory(ROOT, protocol, progress)
        write(path, report)
    log("inventory", counts=report["counts"], distinct=report["distinct_semantics"])
    return report


def screen(protocol, workers):
    path = paths(protocol)["screen"]
    if retained(path, protocol) is not None:
        return log("screen", status="retained")
    exclusions = set(inventory(protocol)["task_semantics"])
    groups = []
    # Each candidate retains candidate.json; a restarted screen re-reads finished candidates.
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(screen_stratum, protocol, p, exclusions) for p in protocol["strata"]]
        for future in as_completed(futures):
            groups.append(future.result())
            log("screen", strata=len(groups), total=len(protocol["strata"]))
    order = {(p["domain"], p["stratum"]): i for i, p in enumerate(protocol["strata"])}
    groups.sort(key=lambda g: order[g["domain"], g["stratum"]])
    write(path, dict(protocol=protocol, strata=groups, final_membership_frozen=False, model_calls=0))


def task_context(candidate):
    task = read(ROOT / candidate["task_path"])
    return PDDLStateAuthority.from_pddl(task["domain_pddl"], task["problem_pddl"]).task_context()


def selection(protocol):
    pool = retained(paths(protocol)["screen"], protocol)
    historical = [json.loads(s) for s in inventory(protocol)["task_semantics"]]
    strata, missing = select_strata(pool["strata"], historical, task_context)
    return dict(
        protocol=protocol,
        strata=strata,
        selected_count=sum(g["selected"] is not None for g in strata),
        missing_strata=missing,
        historical_contexts_compared=len(historical),
        model_calls=0,
    )


def select(protocol):
    path = paths(protocol)["selection"]
    report = retained(path, protocol)
    if report is None:
        if retained(paths(protocol)["screen"], protocol) is None:
            raise ValueError("run screen first")
        report = selection(protocol)
        write(path, report)
    log("select", selected=report["selected_count"], missing=report["missing_strata"])


def repair(protocol, domain):
    spec = protocol["views"]["domain_render_repairs"].get(domain, {})
    transform = spec.get("vfg_transform")
    return dict(render_overrides=spec.get("render_overrides"), vfg_transform=transform and REPAIRS[transform])


def require_backend(endpoints):
    for endpoint in endpoints:
        try:
            urllib.request.urlopen(endpoint, timeout=10)
        except urllib.error.HTTPError:
            pass  # A live Django backend answers unknown roots with an HTTP error.
        except OSError as error:
            raise RuntimeError(
                f"Planimation backend unreachable at {endpoint}; start it with "
                "`.cache/issue70-backend-venv/bin/python scripts/serve_issue70_planimation.py --port 18094 --workers 2`"
            ) from error


def views(protocol, workers):
    path = paths(protocol)["views"]
    if retained(path, protocol) is not None:
        return log("views", status="retained")
    report = retained(paths(protocol)["selection"], protocol)
    if report is None:
        raise ValueError("run select first")
    endpoints = protocol["views"]["endpoints"]
    require_backend(endpoints)
    groups = [g for g in report["strata"] if g["selected"] is not None]
    tasks = []
    # prepare_task retains views/<name>/result.json; a restart re-reads finished tasks.
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(prepare_task, protocol, g, i, endpoint=endpoints[i % len(endpoints)], **repair(protocol, g["domain"]))
            for i, g in enumerate(groups)
        ]
        for future in as_completed(futures):
            tasks.append(future.result())
            log("views", completed=len(tasks), total=len(groups), task=tasks[-1]["row"]["task_id"])
    tasks.sort(key=lambda t: t["row"]["task_id"])
    write(path, dict(protocol=protocol, tasks=tasks, complete_live_input_bounds=False, hardware_qualified=False))


def snapshot(row):
    target = SNAPSHOTS / f"{row['domain']}-{row['difficulty']}.json"
    source = read(ROOT / row["task_path"])
    if target.exists() and read(target) != source:
        raise ValueError(f"retained task snapshot {target.relative_to(ROOT)} differs from its source task")
    write(target, source)
    return str(target.relative_to(ROOT))


def stratum_summary(group, protocol):
    selected = group["selected"]
    decisions = group["decisions"]
    return dict(
        domain=group["domain"],
        stratum=group["stratum"],
        seeds_available=len(next(p for p in protocol["strata"] if (p["domain"], p["stratum"]) == (group["domain"], group["stratum"]))["seeds"]),
        seeds_tried=len(decisions),
        rejections=dict(Counter(d["disposition"] for d in decisions if d["disposition"] != SELECTED)),
        selected_task=selected and selected["row"]["task_id"],
        selected_seed=selected and selected["seed"],
        reference_costs=selected and selected["row"]["reference_costs"],
    )


def freeze(protocol):
    report = retained(paths(protocol)["views"], protocol)
    if report is None:
        raise ValueError("run views first")
    choice = retained(paths(protocol)["selection"], protocol)
    tasks = [
        dict(row=t["row"], source_snapshot=snapshot(t["row"]), reference_paths=t["reference_paths"])
        for t in report["tasks"]
    ]
    digest = membership_sha256(tasks)
    frozen_at = read(PANEL)["frozen_at"] if PANEL.exists() and read(PANEL)["membership_sha256"] == digest else time.time()
    domains = Counter(t["row"]["domain"] for t in tasks)
    panel = dict(
        program_id=protocol["program_id"],
        panel_id=protocol["study_id"],
        frozen_at=frozen_at,
        protocol=str(PROTOCOL.relative_to(ROOT)),
        algorithms=protocol["reference"]["algorithms"],
        modalities=protocol["views"]["modalities"],
        reference_decision_multiplier=2,
        evaluation_seed=17,
        view_report=protocol["views"]["view_report"],
        view_runtime="examples.planning_benchmark_slice.expanded_views.ExpandedTaskViews",
        task_count=len(tasks),
        target_problems=protocol["target_problems"],
        domains_with_both_strata=sorted(d for d, n in domains.items() if n == 2),
        missing_strata=choice["missing_strata"],
        membership_sha256=digest,
        membership_sha256_scope="sha256 of compact JSON of sorted [task_id, reference_costs] pairs",
        tasks=tasks,
    )
    write(PANEL, panel)
    maxima = {t["row"]["task_id"]: t["reference_input_maxima"] for t in report["tasks"]}
    strata = [stratum_summary(g, protocol) for g in choice["strata"]]
    for entry in strata:
        entry["reference_input_maxima"] = maxima.get(entry["selected_task"])
    write(
        SUMMARY,
        dict(
            panel=str(PANEL.relative_to(ROOT)),
            membership_sha256=digest,
            selected_count=len(tasks),
            target_problems=protocol["target_problems"],
            missing_strata=choice["missing_strata"],
            historical_contexts_compared=choice["historical_contexts_compared"],
            screened_candidates=sum(len(g["decisions"]) for g in choice["strata"]),
            strata=strata,
            model_calls=0,
        ),
    )
    log("freeze", tasks=len(tasks), missing=len(choice["missing_strata"]), sha256=digest)


def audit(protocol):
    """Recompute every admission fact from retained evidence; raise on any disagreement."""
    domains = protocol["domains"]
    assert domains == sorted(domains) and len(domains) == 15
    assert [(p["domain"], p["stratum"]) for p in protocol["strata"]] == [
        (d, s) for d in domains for s in protocol["strata_names"]
    ]
    v2 = {(p["domain"], p["stratum"]): p for p in read(V2_PROTOCOL)["strata"]}
    revised = {(r["domain"], r["stratum"]): r for r in protocol.get("profile_revisions", [])}
    for p in protocol["strata"]:
        d, s = domains.index(p["domain"]), protocol["strata_names"].index(p["stratum"])
        key = (p["domain"], p["stratum"])
        count = 64 if key in revised else 16
        assert p["seeds"] == [947000 + 1000 * d + 100 * s + k for k in range(count)], key
        if key in v2:
            old = {k: v2[key][k] for k in ("arguments", "walk_steps", "walk_origin")}
            old.update(revised.get(key, {}).get("revised", {}))
            assert all(p[k] == old[k] for k in old), key
    screen = retained(paths(protocol)["screen"], protocol)
    assert [[c["seed"] for c in g["candidates"]] for g in screen["strata"]] == [p["seeds"] for p in protocol["strata"]]
    stored = retained(paths(protocol)["selection"], protocol)
    assert selection(protocol) == stored, "selection is not reproducible from the screen and exclusions"
    assert stored["selected_count"] + len(stored["missing_strata"]) == len(protocol["strata"])
    panel = read(PANEL)
    report = retained(paths(protocol)["views"], protocol)
    views_by_id = {t["row"]["task_id"]: t for t in report["tasks"]}
    selected = {g["selected"]["row"]["task_id"]: g["selected"] for g in stored["strata"] if g["selected"]}
    assert set(views_by_id) == set(selected) == {t["row"]["task_id"] for t in panel["tasks"]}
    assert panel["membership_sha256"] == membership_sha256(panel["tasks"])
    assert panel["missing_strata"] == stored["missing_strata"]
    limits, bound = protocol["reference"], protocol["views"]["max_context_tokens"] - protocol["views"]["output_tokens"]
    for task in panel["tasks"]:
        row = task["row"]
        assert row == selected[row["task_id"]]["row"] == views_by_id[row["task_id"]]["row"]
        assert read(ROOT / task["source_snapshot"]) == read(ROOT / row["task_path"])
        # Independent replay: every retained operation is accepted and reproduces the stored result.
        reference_catalog(ROOT, row, task["reference_paths"], protocol["study_id"])
        for algorithm, path in task["reference_paths"].items():
            reference = read_json(ROOT / path)
            assert reference["result"]["invariant_valid_success"] and reference["result"]["goal_reached"]
            cost = row["reference_costs"][algorithm]
            assert cost == dict(decisions=len(reference["events"]), expansions=reference["result"]["expansion_count"])
            assert cost["decisions"] <= limits["max_decisions_per_algorithm"]
            assert cost["expansions"] <= limits["max_expansions_per_algorithm"]
        view = views_by_id[row["task_id"]]
        assert view["outcome"] == "REFERENCE_VIEWS_PASS"
        assert len(view["measurements"]) == sum(c["decisions"] for c in row["reference_costs"].values())
        assert set(view["reference_input_maxima"]) == set(protocol["views"]["modalities"])
        assert all(v <= bound for v in view["reference_input_maxima"].values()), row["task_id"]
        manifest = read(ROOT / view["native_views"]["source_manifest"])
        recipe = read(ROOT / view["native_views"]["view_id"] / "recipe.json")
        spec = protocol["views"]["domain_render_repairs"].get(row["domain"], {})
        assert manifest.get("render_overrides") == spec.get("render_overrides")
        assert recipe.get("vfg_transform") == (spec.get("vfg_transform") and "compact_grid_vfg")
        log("audit", task=row["task_id"], costs=row["reference_costs"], maxima=view["reference_input_maxima"])
    print(
        f"PASS: {len(panel['tasks'])}/{protocol['target_problems']} panel tasks replay-verified for "
        f"{'+'.join(limits['algorithms'])}, views PASS within {bound} input tokens; "
        f"missing strata: {[(m['domain'], m['stratum']) for m in panel['missing_strata']]}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=("screen", "select", "views", "freeze", "audit", "all"))
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    protocol = read(args.protocol)
    stages = ("screen", "select", "views", "freeze", "audit") if args.stage == "all" else (args.stage,)
    for stage in stages:
        if stage in ("screen", "views"):
            globals()[stage](protocol, args.workers)
        else:
            globals()[stage](protocol)


if __name__ == "__main__":
    main()
