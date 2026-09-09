"""Cost-only, shared evaluation panels built from retained hardware measurements."""

import math
from bisect import bisect_left
from collections import Counter, defaultdict

from .modality_corpus import MODALITIES, iter_shard
from .modality_corpus_replay import canonical
from .scene_assets import read_json


def family(algorithm):
    return "additive" if algorithm.startswith("best_first_add_") else algorithm


def partition_tasks(rows, workers, costs):
    """Deterministic task placement shared by the estimate and rollout launcher."""
    loads, partitions = [0.0] * workers, [[] for _ in range(workers)]
    for row in sorted(rows, key=lambda r: (-costs[r["task_id"]], r["task_id"])):
        slot = min(range(workers), key=lambda i: (loads[i], i))
        partitions[slot].append(row)
        loads[slot] += costs[row["task_id"]]
    return partitions, loads


class InputCostCurve:
    """Upper-neighbour interpolation with a monotone envelope, within one algorithm."""

    def __init__(self, points):
        grouped = defaultdict(list)
        for point in points:
            grouped[point["input_tokens"]].append(point["seconds_per_call"])
        self.lengths = sorted(grouped)
        if not self.lengths:
            raise ValueError("missing input-size calibration")
        self.costs = []
        for length in self.lengths:
            self.costs.append(max(max(grouped[length]), self.costs[-1] if self.costs else 0))

    def seconds(self, length):
        index = bisect_left(self.lengths, length)
        if index == len(self.lengths):
            return self.costs[-1] * length / self.lengths[-1]
        return self.costs[index]


def choose_groups(rows, groups, costs, workers, budget_seconds, margin):
    """Preserve coverage, then fill remaining budget with the cheapest whole groups."""
    by_id = {r["task_id"]: r for r in rows}
    candidates = []
    for ids in groups:
        keys = {(by_id[i]["domain"], family(a)) for i in ids for a in by_id[i]["reference_costs"]}
        candidates.append((sum(costs[i] for i in ids), tuple(sorted(ids)), keys))
    candidates.sort(key=lambda g: (g[0], g[1]))
    covered = set()
    mandatory = set()
    for _, ids, keys in candidates:
        if not keys <= covered:
            mandatory.update(ids)
            covered.update(keys)

    def seconds(ids):
        return margin * max(partition_tasks([by_id[i] for i in ids], workers, costs)[1], default=0)

    selected = set(mandatory)
    floor = seconds(selected)
    for _, ids, _ in candidates:
        if not set(ids) <= selected and seconds(selected | set(ids)) <= budget_seconds:
            selected.update(ids)
    return sorted(selected), sorted(mandatory), floor, seconds(selected)


def build_cost_panel(experiment, budget_seconds=54000, margin=1.2, progress=lambda *args, **kwargs: None):
    root = experiment.corpus.root
    config = experiment.config
    qualifications, source_contract = experiment.reused_qualification()
    source = root / config["qualification_source"]
    measurements = defaultdict(list)
    for worker in range(len(qualifications)):
        for path in sorted((source.parent / "qualification" / f"worker-{worker}-probes").glob("*.json")):
            measurement = read_json(path)
            measurements[measurement["record_id"]].append((measurement, str(path.relative_to(root))))

    # Read only sizes, source reference bindings and split labels for costing.
    statistics = {}
    probe_records = {}
    for i, row in enumerate(experiment.panel):
        stats = defaultdict(lambda: {"input_histogram": Counter(), "records": 0})
        for record in iter_shard(root / experiment.corpus.results[row["task_id"]]["path"]):
            stat = stats[record["algorithm"]]
            stat["records"] += 1
            stat["input_histogram"][record["tokens"]["input"]["visual-state"]] += 1
            if record["record_id"] in measurements:
                probe_records[record["record_id"]] = record
        if {a: s["records"] for a, s in stats.items()} != {a: c["decisions"] for a, c in row["reference_costs"].items()}:
            raise ValueError("source record coverage differs from exact-reference costs")
        statistics[row["task_id"]] = stats
        progress("panel:measure", completed=i + 1, total=len(experiment.panel))

    calibration = []
    for record_id, observations in sorted(measurements.items()):
        record = probe_records[record_id]
        calibration.append(
            {
                "record_id": record_id,
                "algorithm": record["algorithm"],
                "input_tokens": record["tokens"]["input"]["visual-state"],
                "seconds_per_call": max(m["seconds_per_call"] for m, _ in observations),
                "batch_size": observations[0][0]["batch_size"],
                "sources": [p for _, p in observations],
            }
        )
    curves = {a: InputCostCurve([p for p in calibration if p["algorithm"] == a]) for a in config["algorithms"]}
    multiplier = config["model_call_multiplier"] * 2 * len(config["evaluation_seeds"])
    costs, entries, identities = {}, [], defaultdict(list)
    for row in experiment.dev:
        task_id = row["task_id"]
        settings = {}
        for algorithm, stat in statistics[task_id].items():
            hist = stat["input_histogram"]
            reference_seconds = sum(n * curves[algorithm].seconds(length) for length, n in hist.items())
            settings[algorithm] = {
                "reference_decisions": stat["records"],
                "maximum_model_calls": stat["records"] * multiplier,
                "mean_input_tokens": sum(n * t for t, n in hist.items()) / stat["records"],
                "maximum_input_tokens": max(hist),
                "reference_input_proxy_gpu_seconds": reference_seconds * multiplier,
            }
        costs[task_id] = sum(s["reference_input_proxy_gpu_seconds"] for s in settings.values())
        view = read_json(root / experiment.corpus.results[task_id]["view_manifest"])
        catalog = read_json(root / view["scene_catalog"])
        identities[canonical(catalog["task_context"])].append(task_id)
        entries.append({**row, "settings": settings, "proxy_gpu_seconds": costs[task_id]})

    groups = sorted((sorted(ids) for ids in identities.values()), key=lambda ids: ids[0])
    workers = len(config["devices"])
    selected, mandatory, floor, selected_seconds = choose_groups(
        experiment.dev, groups, costs, workers, budget_seconds, margin
    )
    selected_set = set(selected)
    full_seconds = margin * max(partition_tasks(experiment.dev, workers, costs)[1])
    for rank, entry in enumerate(sorted(entries, key=lambda e: (-e["proxy_gpu_seconds"], e["task_id"])), 1):
        entry.update(
            cost_rank_descending=rank,
            selected=entry["task_id"] in selected_set,
            selection_reason=(
                "coverage_floor"
                if entry["task_id"] in mandatory
                else "within_budget" if entry["task_id"] in selected_set else "above_remaining_budget"
            ),
        )

    microstep = max(q["training_microstep_seconds"] for q in qualifications)
    training = []
    training_loads, diagnostic_loads = [0.0] * workers, [0.0] * workers
    for index, algorithm in enumerate(config["algorithms"]):
        records, dev_records = experiment.train_counts[algorithm], experiment.dev_counts[algorithm]
        train_seconds = records * config["training"]["epochs"] * microstep
        diagnostic_seconds = 2 * dev_records * microstep
        slot = index % workers
        training_loads[slot] += train_seconds
        diagnostic_loads[slot] += diagnostic_seconds
        training.append(
            {
                "algorithm": algorithm,
                "training_records": records,
                "optimizer_steps": (
                    math.ceil(records / config["training"]["global_batch_size"]) * config["training"]["epochs"]
                ),
                "training_proxy_gpu_seconds": train_seconds,
                "full_dev_diagnostic_records_per_pass": dev_records,
                "diagnostic_proxy_gpu_seconds": diagnostic_seconds,
                "worker": slot,
            }
        )
    return {
        "schema": "shared_cost_panel_v1",
        "outcome": "PASS",
        "scientific_completion": False,
        "corpus_report": config["corpus_report"],
        "source_qualification": config["qualification_source"],
        "qualification_contract_id": source_contract,
        "cost_basis_modality": "visual-state",
        "modalities": list(MODALITIES),
        "model_outcomes_used_for_selection": False,
        "policy": {
            "evaluation_budget_seconds": budget_seconds,
            "margin": margin,
            "coverage": "one whole problem group per available domain/algorithm family, then cheapest additions",
            "calibration": (
                "per-algorithm monotone upper-neighbour input-size curve; proportional extrapolation above last probe"
            ),
            "call_multiplier": multiplier,
            "device_count": workers,
        },
        "selected_task_ids": selected,
        "excluded_task_ids": sorted(set(costs) - selected_set),
        "matched_problem_groups": groups,
        "tasks": sorted(entries, key=lambda e: e["cost_rank_descending"]),
        "calibration": calibration,
        "evaluation": {
            "estimate_kind": "reference_input_full_output_cost_proxy_not_eta",
            "full_proxy_wall_seconds": full_seconds,
            "selected_proxy_wall_seconds": selected_seconds,
            "coverage_floor_proxy_wall_seconds": floor,
            "fits_evaluation_budget": selected_seconds <= budget_seconds,
            "proxy_work_reduction_percent": 100 * (1 - sum(costs[i] for i in selected) / sum(costs.values())),
        },
        "training": {
            "corpus_changed": False,
            "estimate_kind": "global_max_microstep_stress_not_eta",
            "settings": training,
            "training_proxy_wall_seconds": max(training_loads),
            "full_dev_diagnostic_proxy_wall_seconds": max(diagnostic_loads),
            "combined_proxy_wall_seconds": max(a + b for a, b in zip(training_loads, diagnostic_loads, strict=True)),
        },
        "limitations": [
            "Only visual hardware timing is measured; this same panel must be used for other modality comparisons.",
            "Uses 384-token timing and maximum call allowances; live inputs may differ from reference inputs.",
            "Batch-normalized timing, device packing and a margin are cost proxies, not an end-to-end time guarantee.",
            "Training and diagnostics use full source data; short-input training timing is unmeasured.",
            "Reference rendering, adapter qualification and I/O are not timed in these projections.",
        ],
    }


def panel_task_ids(panel, modality, algorithm):
    if modality not in panel["modalities"]:
        raise ValueError("modality is outside the shared panel")
    selected = set(panel["selected_task_ids"])
    return sorted(t["task_id"] for t in panel["tasks"] if t["task_id"] in selected and algorithm in t["reference_costs"])


def load_cost_panel(path, config, dev):
    panel = read_json(path)
    policy = panel["policy"]
    if (
        panel.get("schema") != "shared_cost_panel_v1"
        or panel.get("outcome") != "PASS"
        or panel.get("model_outcomes_used_for_selection") is not False
        or panel["corpus_report"] != config["corpus_report"]
        or panel["source_qualification"] != config["qualification_source"]
        or panel["modalities"] != list(MODALITIES)
        or policy["device_count"] != len(config["devices"])
        or policy["call_multiplier"] != config["model_call_multiplier"] * 2 * len(config["evaluation_seeds"])
    ):
        raise ValueError("cost panel source or experiment settings differ")
    by_id = {r["task_id"]: r for r in dev}
    tasks = panel["tasks"]
    if len(tasks) != len(dev) or {t["task_id"] for t in tasks} != set(by_id):
        raise ValueError("cost panel does not account for every source dev task")
    for task in tasks:
        if any(task[k] != v for k, v in by_id[task["task_id"]].items()):
            raise ValueError("cost panel task/split/algorithm binding differs")
    groups = panel["matched_problem_groups"]
    grouped_ids = [i for group in groups for i in group]
    if len(grouped_ids) != len(dev) or set(grouped_ids) != set(by_id):
        raise ValueError("cost panel problem groups are incomplete")
    costs = {t["task_id"]: t["proxy_gpu_seconds"] for t in tasks}
    if any(not math.isfinite(c) or c <= 0 for c in costs.values()):
        raise ValueError("cost panel requires positive finite costs")
    expected, _, _, _ = choose_groups(
        dev, groups, costs, policy["device_count"], policy["evaluation_budget_seconds"], policy["margin"]
    )
    if panel["selected_task_ids"] != expected or panel["excluded_task_ids"] != sorted(set(by_id) - set(expected)):
        raise ValueError("cost panel selection differs from its cost-only policy")
    if any(t["selected"] != (t["task_id"] in expected) for t in tasks):
        raise ValueError("cost panel selected flags differ")
    return panel
