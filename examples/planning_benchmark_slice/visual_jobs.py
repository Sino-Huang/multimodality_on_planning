"""GPU qualification, reference/model episodes, and visual development adjudication."""

from __future__ import annotations

import gc
import json
import statistics
import time

from .modality_corpus import iter_shard
from .modality_corpus_replay import canonical
from .modality_view_preparation import frozen_processor, write_json
from .scene_assets import read_json
from .visual_episode import VisualSession, VisualTaskViews, replay_visual_episode
from .visual_experiment import ALGORITHMS, ROOT
from .visual_model import VisualCollator, VisualDataset, VisualPolicy, load_training_model
from .visual_panel import partition_tasks


def select_probes(experiment):
    if experiment.pilot:
        from .visual_pilot import probe_records_for_pilot

        return sorted(
            probe_records_for_pilot(experiment),
            key=lambda r: -r["tokens"]["input"][experiment.config["modality"]],
        )
    probes = {}
    c = experiment.config
    for result in experiment.corpus.results.values():
        for record in iter_shard(ROOT / result["path"]):
            maximum = max(record["tokens"]["input"].values())
            bucket = next(n for n in c["input_bins"] if maximum <= n)
            key = (record["algorithm"], record["difficulty"], bucket)
            if key not in probes or maximum > max(probes[key]["tokens"]["input"].values()):
                probes[key] = record
    # Exercise the largest visual inputs first so memory failures surface early.
    return sorted(probes.values(), key=lambda r: (-r["tokens"]["input"]["visual-state"], r["record_id"]))


def semantic_output(experiment, record, output):
    row = next(r for r in experiment.panel if r["task_id"] == record["task_id"])
    session = VisualSession(
        ROOT, row, record["algorithm"], "pretrained_base", 17, experiment.output, experiment.config["contract_id"]
    )
    source = experiment.corpus.results[row["task_id"]]
    for retained in iter_shard(ROOT / source["path"]):
        if retained["algorithm"] != record["algorithm"]:
            continue
        request = session.next_request()
        if request is None or dict(request.model_input) != retained["authoritative_input"]:
            raise ValueError("qualification corpus/live semantic input mismatch")
        if retained["decision_index"] == record["decision_index"]:
            session.submit(output)
            successor = session.next_request()
            try:
                parsed = json.loads(output)
                operation = parsed.get("typed_operation", parsed) if isinstance(parsed, dict) else None
            except ValueError:
                operation = None
            return {
                "operation": operation,
                "accepted": session.events[-1]["accepted"],
                "next_input": dict(successor.model_input) if successor else None,
                "result": session.result() if successor is None else None,
            }
        session.submit(canonical(retained["target"]))
    raise ValueError("qualification record is absent from source")


def make_policy(experiment, adapters=None):
    from .visual_attention import configure_visual_attention

    c = experiment.config
    policy = VisualPolicy(
        model_id=c["model_id"],
        revision=c["model_revision"],
        adapter_paths=adapters or {},
        device="cuda:0",
        max_context_tokens=c["context_tokens"],
        max_new_tokens=c["output_tokens"],
        max_batch_size=c["max_batch_size"],
        max_batch_input_tokens=c["max_batch_input_tokens"],
    )
    configure_visual_attention(policy.model, c["inference_attention"])
    policy.identity.update(attention_implementation=c["inference_attention"], memoize_identical_inputs=False)
    return policy


def probe_examples(experiment, records, modality="visual-state"):
    examples = []
    for record in records:
        example = experiment.corpus.training_example(record, modality)
        example["messages"] = example["messages"][:-1]
        examples.append(example)
    return examples


def probe_records(config, records, primary, modality):
    partner = min(
        (r for r in records if r["algorithm"] == primary["algorithm"]), key=lambda r: r["tokens"]["input"][modality]
    )
    size = min(config["max_batch_size"], config["max_batch_input_tokens"] // primary["tokens"]["input"][modality])
    return [primary if i % 2 == 0 else partner for i in range(size)]


class SemanticProbe:
    def __init__(self, experiment):
        self.experiment = experiment
        self.cache = {}

    def evaluate(self, record, output):
        key = (record["algorithm"], record["record_id"], output)
        if key not in self.cache:
            self.cache[key] = semantic_output(self.experiment, record, output)
        return self.cache[key]


def qualify_batch(policy, records, examples, semantics, progress, adapter=None):
    """Compare each distinct scalar input against every position in two batches."""
    unique = {r["record_id"]: (r, e) for r, e in zip(records, examples, strict=True)}
    total = len(unique) + 2
    scalar_results = {}
    for i, (key, (record, example)) in enumerate(unique.items()):
        progress("qualification_call", completed=i, total=total, operation="scalar", record_id=key)
        output = policy.generate([example], adapter)[0]
        scalar_results[key] = semantics.evaluate(record, output)
    for repeat in range(2):
        progress(
            "qualification_call",
            completed=len(unique) + repeat,
            total=total,
            operation="batch" if repeat == 0 else "repeated_batch",
            batch_size=len(examples),
        )
        outputs = policy.generate(examples, adapter)
        for record, output in zip(records, outputs, strict=True):
            if semantics.evaluate(record, output) != scalar_results[record["record_id"]]:
                raise ValueError("scalar/batch/repeated operation or trusted runtime result differs")
    progress("qualification_call", completed=total, total=total, operation="semantic_check_complete")


def qualify_device(experiment, worker, progress):
    import torch

    c = experiment.config
    started = time.monotonic()
    deadline = experiment.deadline()
    records = select_probes(experiment)
    free_bytes, total_bytes = torch.cuda.mem_get_info()
    progress("model_loading", completed=0, total=len(records), gpu_free_bytes=free_bytes, gpu_total_bytes=total_bytes)
    policy = make_policy(experiment)
    policy.stop_at = deadline
    timings = []
    semantics = SemanticProbe(experiment)
    for i, record in enumerate(records):
        if time.monotonic() >= deadline:
            raise RuntimeError("VALID_STOP: qualification clock exhausted")
        batch_records = probe_records(c, records, record, c["modality"])
        then = time.monotonic()
        examples = probe_examples(experiment, batch_records, c["modality"])
        composition_seconds = time.monotonic() - then

        def probe_progress(stage, probe=i + 1, primary_record=record["record_id"], **fields):
            progress(stage, probe=probe, probes=len(records), primary_record=primary_record, **fields)

        torch.cuda.reset_peak_memory_stats()
        qualify_batch(policy, batch_records, examples, semantics, probe_progress)
        probe_progress("qualification_timing", completed=0, total=1, operation="full_384_tokens")
        then = time.monotonic()
        policy.generate(examples, force_full_output=True)
        torch.cuda.synchronize()
        seconds_per_call = (composition_seconds + time.monotonic() - then) / len(examples)
        timings.append(seconds_per_call)
        write_json(
            experiment.output / "qualification" / f"worker-{worker}-probes" / f"{i:03d}.json",
            {
                "record_id": record["record_id"],
                "modality": c["modality"],
                "outcome": "PASS",
                "batch_size": len(examples),
                "distinct_scalar_inputs": len({r["record_id"] for r in batch_records}),
                "seconds_per_call": seconds_per_call,
                "composition_seconds": composition_seconds,
                "elapsed_seconds": time.monotonic() - started,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                "gpu_free_bytes": torch.cuda.mem_get_info()[0],
            },
        )

        progress(
            "qualification",
            completed=i + 1,
            total=len(records),
            eta_seconds=(time.monotonic() - started) / (i + 1) * (len(records) - i - 1),
        )
    del policy
    gc.collect()
    torch.cuda.empty_cache()
    model = load_training_model(c)
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=0.0)
    collator = VisualCollator(frozen_processor().processor)
    training_times = []
    for algorithm in ALGORITHMS:
        dataset = VisualDataset(
            ROOT,
            ROOT / c["corpus_report"],
            algorithm,
            modality=c["modality"],
            record_ids=experiment.pilot["training_record_ids"][algorithm] if experiment.pilot else None,
        )
        dev_dataset = VisualDataset(
            ROOT,
            ROOT / c["corpus_report"],
            algorithm,
            split="dev",
            modality=c["modality"],
            record_ids=experiment.pilot["diagnostic_record_ids"][algorithm] if experiment.pilot else None,
        )
        dataset.records.extend(dev_dataset.records)
        del dev_dataset
        index = max(
            range(len(dataset)), key=lambda i, records=dataset.records: records[i]["tokens"]["input"][c["modality"]]
        )
        if time.monotonic() >= deadline:
            raise RuntimeError("VALID_STOP: qualification clock exhausted before training probe")
        batch = {k: v.to("cuda:0") for k, v in collator([dataset[index]]).items()}
        then = time.monotonic()
        optimizer.zero_grad(set_to_none=True)
        if time.monotonic() >= deadline:
            raise RuntimeError("VALID_STOP: cutoff before hardware training probe")
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss = model(**batch).loss
        loss.backward()
        optimizer.step()  # lr=0; disposable hardware probe, no trained checkpoint or learned update.
        torch.cuda.synchronize()
        training_times.append(time.monotonic() - then)
        progress("training_hardware_probe", completed=len(training_times), total=4, algorithm=algorithm)
        del dataset, batch, loss
    return {
        "contract_id": c["contract_id"],
        "worker": worker,
        "outcome": "PASS",
        "probe_records": len(records),
        "seconds_per_call": max(timings),
        "training_microstep_seconds": max(training_times),
        "dtype": "float32",
        "attention_implementation": c["inference_attention"],
        "model_outcomes_used_for_selection": False,
        "device": torch.cuda.get_device_name(0),
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "elapsed_seconds": time.monotonic() - started,
        "timing_output_tokens": 384,
    }


def selected_rows(experiment):
    selection = read_json(experiment.output / "qualification.json")["selection"]["task_ids"]
    return [r for r in experiment.dev if r["task_id"] in selection]


def jobs_for(experiment, reference, worker, workers):
    rows = selected_rows(experiment)
    # Whole task groups remain together, including both additive settings.
    costs = {r["task_id"]: sum(c["decisions"] for c in r["reference_costs"].values()) for r in rows}
    if experiment.cost_panel and not reference:
        costs = {t["task_id"]: t["proxy_gpu_seconds"] for t in experiment.cost_panel["tasks"]}
    if experiment.pilot and not reference:
        costs = experiment.pilot["evaluation_costs"]
    partitions, _ = partition_tasks(rows, workers, costs)
    jobs = []
    arms = ("exact_reference", "random_valid") if reference else ("pretrained_base", "process_sft")
    for algorithm in ALGORITHMS:
        for arm in arms:
            for row in sorted(partitions[worker], key=lambda r: r["task_id"]):
                if algorithm not in row["reference_costs"]:
                    continue
                for seed in ([17] if arm == "exact_reference" else experiment.config["evaluation_seeds"]):
                    jobs.append((row, algorithm, arm, seed))
    return jobs


def run_jobs(experiment, worker, reference, progress, resume=False):
    c = experiment.config
    workers = len(c["backend_endpoints"]) if reference else len(c["devices"])
    jobs = jobs_for(experiment, reference, worker, workers)
    stage = "references" if reference else "evaluation"
    shard = experiment.output / stage / f"worker-{worker}"
    adapters = {a: str(experiment.output / "training" / a / "final") for a in ALGORITHMS}
    policy = None if reference else make_policy(experiment, adapters)
    if policy:
        policy.stop_at = experiment.deadline()
        # Actual trained adapter/base isolation, before any scientific episode generation.
        semantics = SemanticProbe(experiment)
        if experiment.pilot:
            from .visual_pilot import probe_records_for_pilot

            all_records = probe_records_for_pilot(experiment)
        else:
            all_records = select_probes(experiment)
        for algorithm in ALGORITHMS:
            records = [r for r in all_records if r["algorithm"] == algorithm]
            for probe_index, record in enumerate(records[:1] if experiment.pilot else records):
                if time.monotonic() >= experiment.deadline():
                    raise RuntimeError("VALID_STOP: cutoff during trained-adapter qualification")
                batch_records = probe_records(c, records, record, c["modality"])
                examples = probe_examples(experiment, batch_records, c["modality"])
                before = policy.generate([examples[0]])[0]
                qualify_batch(policy, batch_records, examples, semantics, progress, algorithm)
                after = policy.generate([examples[0]])[0]
                if semantics.evaluate(record, before) != semantics.evaluate(record, after):
                    raise ValueError("trained adapter leaked into base condition")
                progress("trained_adapter_probe", completed=probe_index + 1, total=len(records), algorithm=algorithm)

    results = []
    active = []
    waiting = iter(enumerate(jobs))
    exhausted = False
    views_by_task = {}

    def schedule():
        nonlocal exhausted
        while len(active) < c["max_batch_size"] and not exhausted:
            item = next(waiting, None)
            if item is None:
                exhausted = True
                return
            number, (row, algorithm, arm, seed) = item
            path = shard / f"episode-{number:05d}.json.gz"
            if row["task_id"] not in views_by_task:
                # Drop inactive task caches; state recipes remain persisted for later seeds.
                active_ids = {a["row"]["task_id"] for a in active}
                for task_id in list(views_by_task):
                    if task_id not in active_ids:
                        views_by_task[task_id].save()
                        del views_by_task[task_id]
                views_by_task[row["task_id"]] = VisualTaskViews(
                    ROOT,
                    row,
                    experiment.corpus.results[row["task_id"]]["view_manifest"],
                    shard / "views" / row["task_id"].replace("/", "__"),
                    c["backend_endpoints"][worker],
                )
            views = views_by_task[row["task_id"]]
            if path.exists():
                if not resume:
                    raise ValueError("existing episode requires --resume")
                report = read_json(path)
                if (report["contract_id"], report["task_id"], report["algorithm"], report["arm"], report["seed"]) != (
                    c["contract_id"],
                    row["task_id"],
                    algorithm,
                    arm,
                    seed,
                ):
                    raise ValueError("episode attempt identity differs")
                replay_visual_episode(ROOT, row, report, views)
                results.append(
                    {
                        "path": str(path.relative_to(ROOT)),
                        "task_id": row["task_id"],
                        "algorithm": algorithm,
                        "arm": arm,
                        "seed": seed,
                        "result": report["result"],
                    }
                )
                continue
            session = VisualSession(ROOT, row, algorithm, arm, seed, path, c["contract_id"], views=views)
            active.append({"row": row, "session": session, "path": path, "views": views})

    def finish(item):
        session = item["session"]
        views = item["views"]
        views.save()
        report = {
            "contract_id": c["contract_id"],
            "modality": c["modality"],
            "task_id": item["row"]["task_id"],
            "algorithm": session.algorithm,
            "arm": session.arm,
            "seed": session.seed,
            "events": session.events,
            "result": session.result(),
            "output": str(item["path"].relative_to(ROOT)),
            "view_root": str(views.output.relative_to(ROOT)),
        }
        replay_visual_episode(ROOT, item["row"], report, views)
        write_json(item["path"], report)
        results.append(
            {
                "path": str(item["path"].relative_to(ROOT)),
                "task_id": session.row["task_id"],
                "algorithm": session.algorithm,
                "arm": session.arm,
                "seed": session.seed,
                "result": report["result"],
            }
        )
        active.remove(item)
        progress(stage, completed=len(results), total=len(jobs), task_id=session.row["task_id"])

    while active or not exhausted:
        if len(results) == len(jobs):
            break
        if time.monotonic() >= experiment.deadline():
            raise RuntimeError("VALID_STOP: matrix cutoff with incomplete episode coverage")
        schedule()
        requests = []
        for item in active[:]:
            session = item["session"]
            request = session.next_request()
            if request is None:
                finish(item)
            else:
                example = item["views"].observe(dict(request.model_input), session.algorithm, modality=c["modality"])
                requests.append((item, example))
        # Each active episode contributes at most one call in a deterministic round.
        batches = []
        for item, example in requests:
            session = item["session"]
            adapter = session.algorithm if session.arm == "process_sft" else None
            if reference:
                if time.monotonic() >= experiment.deadline():
                    break
                session.submit(session.reference_output(), example["binding"])
                if session.next_request() is None:
                    finish(item)
                continue
            if (
                not batches
                or batches[-1][0] != adapter
                or len(batches[-1][1]) >= c["max_batch_size"]
                or max([e["binding"]["input_tokens"] for _, e in batches[-1][1]] + [example["binding"]["input_tokens"]])
                * (len(batches[-1][1]) + 1)
                > c["max_batch_input_tokens"]
            ):
                batches.append((adapter, []))
            batches[-1][1].append((item, example))
        for adapter, batch in batches:
            if time.monotonic() >= experiment.deadline():
                raise RuntimeError("VALID_STOP: cutoff before new model calls")
            assert policy is not None
            outputs = policy.generate([e for _, e in batch], adapter)
            for (item, example), output in zip(batch, outputs, strict=True):
                item["session"].submit(output, example["binding"])
                if item["session"].next_request() is None:
                    finish(item)
        if requests:
            progress(
                f"{stage}:round",
                completed=len(results),
                total=len(jobs),
                active=len(active),
                decisions=sum(len(a["session"].events) for a in active),
            )
    return {"contract_id": c["contract_id"], "outcome": "PASS", "worker": worker, "episodes": results}


def adjudicate(experiment, progress):
    from .best_first_development import _paired_bootstrap_lower_bound

    c = experiment.config
    reports = [read_json(experiment.output / f"{stage}.json") for stage in ("references", "evaluation")]
    episodes = [r for report in reports for r in report["episodes"]]
    rows = selected_rows(experiment)
    expected = {
        (r["task_id"], a, arm, seed)
        for r in rows
        for a in r["reference_costs"]
        for arm in ("exact_reference", "random_valid", "pretrained_base", "process_sft")
        for seed in ([17] if arm == "exact_reference" else c["evaluation_seeds"])
    }
    if (
        len(episodes) != len(expected)
        or {(e["task_id"], e["algorithm"], e["arm"], e["seed"]) for e in episodes} != expected
    ):
        raise ValueError("adjudication lacks complete frozen episode coverage")
    for i, item in enumerate(episodes):
        report = read_json(ROOT / item["path"])
        row = next(r for r in rows if r["task_id"] == item["task_id"])
        views = VisualTaskViews(
            ROOT,
            row,
            experiment.corpus.results[row["task_id"]]["view_manifest"],
            ROOT / report["view_root"],
            c["backend_endpoints"][0],
            read_only=True,
        )
        if replay_visual_episode(ROOT, row, report, views) != item["result"]:
            raise ValueError("adjudication episode result differs")
        progress("adjudication", completed=i + 1, total=len(episodes))
        if time.monotonic() >= experiment.deadline("gate"):
            raise RuntimeError("VALID_STOP: certification exceeded original gate clock")
    metrics = {}
    passed = True
    for algorithm in ALGORITHMS:
        arm_rows = {
            arm: [e for e in episodes if e["algorithm"] == algorithm and e["arm"] == arm]
            for arm in ("exact_reference", "random_valid", "pretrained_base", "process_sft")
        }
        rates = {
            arm: statistics.mean(float(e["result"]["invariant_valid_success"]) for e in group)
            for arm, group in arm_rows.items()
        }
        invalid = {
            arm: (
                sum(e["result"]["invalid_operation_count"] for e in group)
                / max(1, sum(e["result"]["decision_count"] for e in group))
            )
            for arm, group in arm_rows.items()
        }
        budget = {
            arm: sum(e["result"]["decision_count"] for e in group) / sum(e["result"]["model_call_limit"] for e in group)
            for arm, group in arm_rows.items()
        }
        best = max(("random_valid", "pretrained_base"), key=lambda arm: rates[arm])
        ids = {e["task_id"] for e in arm_rows["process_sft"]}

        def per_task(arm, arm_rows=arm_rows, ids=ids):
            return {
                identity: statistics.mean(
                    float(e["result"]["invariant_valid_success"]) for e in arm_rows[arm] if e["task_id"] == identity
                )
                for identity in ids
            }

        lower = _paired_bootstrap_lower_bound(
            per_task("process_sft"), per_task(best), resamples=c["bootstrap"]["resamples"], seed=c["bootstrap"]["seed"]
        )
        metrics[algorithm] = {
            "invariant_valid_success": rates,
            "invalid_operation_rate": invalid,
            "budget_usage": budget,
            "best_control": best,
            "gain": rates["process_sft"] - rates[best],
            "paired_bootstrap_lower_bound": lower,
            "advantage_established": lower > 0 and not bool(experiment.pilot),
            "per_seed_success": {
                str(seed): {
                    arm: statistics.mean(
                        float(e["result"]["invariant_valid_success"]) for e in arm_rows[arm] if e["seed"] == seed
                    )
                    for arm in ("random_valid", "pretrained_base", "process_sft")
                }
                for seed in c["evaluation_seeds"]
            },
        }
        passed &= (
            rates["exact_reference"] >= c["thresholds"]["exact_success"]
            and rates["process_sft"] >= c["thresholds"]["learned_success"]
            and invalid["process_sft"] <= c["thresholds"]["maximum_invalid_rate"]
        )
    family = {
        arm: statistics.mean(
            [
                metrics["bfs"]["invariant_valid_success"][arm],
                metrics["best_first_width"]["invariant_valid_success"][arm],
                statistics.mean(metrics[a]["invariant_valid_success"][arm] for a in ALGORITHMS[2:]),
            ]
        )
        for arm in arm_rows
    }
    return {
        "contract_id": c["contract_id"],
        "outcome": "PASS" if passed else "VALID_STOP",
        "complete_selected_coverage": True,
        "episodes": len(episodes),
        "metrics": metrics,
        "family_normalized_success": family,
        "scientific_completion": bool(passed) and not bool(experiment.pilot),
        "study_scope": c.get("study_scope", "development_matrix"),
        "modality": c["modality"],
        "comparison_scope": c.get("comparison_scope", "within_modality"),
        "pilot_complete": bool(experiment.pilot),
        "full_matrix_complete": bool(passed) and not bool(experiment.pilot),
        "uncertainty_scope": "descriptive_pilot_only" if experiment.pilot else "whole_problem_instance_bootstrap",
        "training_seed_variance_claim": False,
    }
