"""Small, single-seed pilot samples with explicit source-record membership."""

from collections import defaultdict

from .modality_corpus import iter_shard
from .visual_panel import partition_tasks


def balanced_sample(records, limit, max_tokens):
    domains = defaultdict(list)
    for record in records:
        if record["tokens"]["input"]["visual-state"] <= max_tokens:
            domains[record["domain"]].append(record)
    quotas = {d: 0 for d in sorted(domains)}
    remaining = min(limit, sum(map(len, domains.values())))
    while remaining:
        for domain in quotas:
            if remaining and quotas[domain] < len(domains[domain]):
                quotas[domain] += 1
                remaining -= 1
    selected = []
    for domain, count in quotas.items():
        rows = sorted(domains[domain], key=lambda r: (r["task_id"], r["decision_index"]))
        selected.extend(rows[i * (len(rows) - 1) // max(1, count - 1)] for i in range(count))
    return sorted(
        selected,
        key=lambda r: (
            {"easy": 0, "medium": 1, "hard": 2}[r["difficulty"]],
            r["domain"],
            r["task_id"],
            r["decision_index"],
        ),
    )


def build_pilot(experiment, domain_count=3, train_limit=512, diagnostic_limit=32, max_tokens=4096):
    panel = experiment.cost_panel
    if panel is None:
        raise ValueError("pilot preparation requires the measured cost panel")
    domains = defaultdict(list)
    for task in panel["tasks"]:
        if task["selected"]:
            domains[task["domain"]].append(task)
    complete = [
        d
        for d, rows in domains.items()
        if {a for r in rows for a in r["reference_costs"]} == set(experiment.config["algorithms"])
    ]
    chosen = sorted(complete, key=lambda d: (sum(t["proxy_gpu_seconds"] for t in domains[d]), d))[:domain_count]
    selected = sorted(t["task_id"] for d in chosen for t in domains[d])
    train_ids, diagnostic_ids, probes, counts = {}, {}, {}, {}
    for algorithm in experiment.config["algorithms"]:
        training = balanced_sample(
            list(experiment.corpus.records(algorithm=algorithm, split="train")), train_limit, max_tokens
        )
        dev = [r for r in experiment.corpus.records(algorithm=algorithm, split="dev") if r["task_id"] in selected]
        diagnostics = balanced_sample(dev, diagnostic_limit, max_tokens)
        if not training or not diagnostics:
            raise ValueError("pilot requires training and diagnostic examples for every algorithm")
        train_ids[algorithm] = [r["record_id"] for r in training]
        diagnostic_ids[algorithm] = [r["record_id"] for r in diagnostics]
        candidates = training + dev
        probes[algorithm] = list(
            dict.fromkeys(
                [
                    max(candidates, key=lambda r: r["tokens"]["input"]["visual-state"])["record_id"],
                    min(candidates, key=lambda r: r["tokens"]["input"]["visual-state"])["record_id"],
                ]
            )
        )
        counts[algorithm] = {"training": len(training), "diagnostic": len(diagnostics)}
    costs = {
        t["task_id"]: t["proxy_gpu_seconds"] / len(experiment.config["evaluation_seeds"])
        for t in panel["tasks"]
        if t["task_id"] in selected
    }
    rows = [r for r in experiment.dev if r["task_id"] in selected]
    _, loads = partition_tasks(rows, len(experiment.config["devices"]), costs)
    return {
        "schema": "deadline_pilot_v1",
        "study_scope": "deadline_pilot",
        "corpus_report": experiment.config["corpus_report"],
        "source_cost_panel": experiment.config["cost_panel"],
        "evaluation_seed": 17,
        "domains": chosen,
        "selected_task_ids": selected,
        "training_record_ids": train_ids,
        "diagnostic_record_ids": diagnostic_ids,
        "adapter_probe_record_ids": probes,
        "record_counts": counts,
        "max_training_input_tokens": max_tokens,
        "train_limit_per_algorithm": train_limit,
        "diagnostic_limit_per_algorithm": diagnostic_limit,
        "evaluation_costs": costs,
        "evaluation_proxy_seconds": max(loads) * 1.2,
        "model_outcomes_used_for_selection": False,
        "full_matrix_complete": False,
    }


def probe_records_for_pilot(experiment):
    ids = [r for a in experiment.config["algorithms"] for r in experiment.pilot["adapter_probe_record_ids"][a]]
    wanted, found = set(ids), {}
    for result in experiment.corpus.results.values():
        for record in iter_shard(experiment.corpus.root / result["path"]):
            if record["record_id"] in wanted:
                found[record["record_id"]] = record
    return [found[i] for i in ids]
