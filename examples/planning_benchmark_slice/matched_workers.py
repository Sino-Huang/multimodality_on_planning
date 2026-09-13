"""Actual matched GPU qualification, training and episode execution."""

from __future__ import annotations

import ctypes
import gc
import os
import signal
import threading
import time
from types import SimpleNamespace
from typing import Any

from .matched_tasks import Progress
from .matched_views import final_view_store
from .modality_corpus import ModalityCorpus
from .modality_view_preparation import write_json
from .scene_assets import read_json
from .visual_episode import VisualSession, replay_visual_episode
from .visual_jobs import SemanticProbe, make_policy, probe_examples, qualify_batch, qualify_device
from .visual_model import train_visual


def experiment(root, study, modality, output, deadline):
    corpus = ModalityCorpus(root, root / study["corpus_report"])
    pilot = read_json(root / study["membership"])
    probes = {}
    for algorithm in study["algorithms"]:
        wanted = set(pilot["training_record_ids"][algorithm] + pilot["diagnostic_record_ids"][algorithm])
        rows = [
            r
            for split in ("train", "dev")
            for r in corpus.records(algorithm=algorithm, split=split)
            if r["record_id"] in wanted
        ]
        probes[algorithm] = [
            max(rows, key=lambda r: r["tokens"]["input"][modality])["record_id"],
            min(rows, key=lambda r: r["tokens"]["input"][modality])["record_id"],
        ]
    pilot["adapter_probe_record_ids"] = probes
    config = {
        **study,
        "contract_id": study["study_id"],
        "modality": modality,
        "pilot_manifest": study["membership"],
        "inference_dtype": study["inference"]["dtype"],
        "inference_attention": study["inference"]["attention"],
        "max_batch_size": study["inference"]["max_batch_size"],
        "max_batch_input_tokens": study["inference"]["max_padded_batch_input_tokens"],
    }
    return SimpleNamespace(
        corpus=corpus,
        pilot=pilot,
        config=config,
        output=output,
        panel=read_json(root / corpus.contract["panel_manifest"])["selected"],
        deadline=lambda: deadline,
    )


def qualifying_examples(root, study, modality):
    panel = read_json(root / study["output_root"] / "preparation/final-panel.json")
    examples = []
    for task in panel["tasks"]:
        maximum = max(task["measurements"], key=lambda r: r["input_tokens"][modality])
        event = read_json(root / task["row"]["reference_paths"][maximum["algorithm"]])["events"][maximum["index"]]
        examples.append(
            final_view_store(root, study, task).observe(event["input"], maximum["algorithm"], modality=modality)
        )
    return examples


def qualify_worker(root, study, worker, deadline, progress):
    import torch

    results = {}
    for modality in study["modalities"]:

        def tagged(stage, **fields):
            progress(stage, **{"modality": modality, **fields})

        tagged("qualification:modality_started", completed=len(results), total=3)
        output = root / study["output_root"] / "qualification" / modality
        ex = experiment(root, study, modality, output, deadline)
        examples = qualifying_examples(root, study, modality)
        results[modality] = qualify_device(ex, worker, tagged, examples)
        for example in examples:
            for image in example["images"]:
                image.close()
        del ex, examples
        gc.collect()
        torch.cuda.empty_cache()
    return {"outcome": "PASS", "worker": worker, "modalities": results}


def train_worker(root, study, job, deadline, progress, resume):
    import torch

    from .visual_pilot import probe_records_for_pilot

    modality, algorithm = job["modality"], job["algorithm"]
    output = root / study["output_root"] / "training" / modality / algorithm
    ex = experiment(root, study, modality, output, deadline)
    result = train_visual(ex.config, root, algorithm, output, deadline=deadline, progress=progress, resume=resume)
    gc.collect()
    torch.cuda.empty_cache()
    # A final checkpoint is never admitted without trained-adapter/base isolation.
    policy = make_policy(ex, {algorithm: str(output / "final")})
    policy.stop_at = deadline
    records = [r for r in probe_records_for_pilot(ex) if r["algorithm"] == algorithm]
    examples = probe_examples(ex, records, modality)
    semantics = SemanticProbe(ex)
    before = policy.generate([examples[0]])[0]
    qualify_batch(policy, records, examples, semantics, progress, algorithm)
    after = policy.generate([examples[0]])[0]
    if semantics.evaluate(records[0], before) != semantics.evaluate(records[0], after):
        raise ValueError("trained adapter leaked into the base condition")
    return {
        **result,
        "modality": modality,
        "adapter_isolation_passed": True,
        "training_settings": study["training"],
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
    }


def evaluate_worker(root, study, job, worker, deadline, progress, resume):
    modality = job["modality"]
    output = root / study["output_root"]
    tasks = read_json(output / "preparation/final-panel.json")["tasks"]
    ex = experiment(root, study, modality, output, deadline)
    policy = make_policy(ex, {a: str(output / "training" / modality / a / "final") for a in study["algorithms"]})
    policy.stop_at = deadline
    selected = [
        (t, a, arm)
        for t in tasks
        for a in study["algorithms"]
        for arm in ("pretrained_base", "process_sft", "exact_reference", "random_valid")
    ]
    selected = selected[worker :: len(study["launch"]["devices"])]
    results = []
    for task, algorithm, arm in selected:
        row = task["row"]
        path = output / "evaluation" / modality / row["task_id"].replace("/", "__") / f"{algorithm}-{arm}.json.gz"
        views = final_view_store(root, study, task)
        if path.exists():
            if not resume:
                raise ValueError("existing evaluation episode requires --resume")
            saved = read_json(path)
            replay_visual_episode(root, row, saved, views)
            results.append(str(path.relative_to(root)))
            continue
        session = VisualSession(root, row, algorithm, arm, 17, path, study["study_id"], views=views)
        while (request := session.next_request()) is not None:
            example = views.observe(dict(request.model_input), algorithm, modality=modality)
            generated = (
                session.reference_output()
                if arm in ("exact_reference", "random_valid")
                else policy.generate([example], algorithm if arm == "process_sft" else None)[0]
            )
            session.submit(generated, example["binding"])
        report = {
            "contract_id": study["study_id"],
            "task_id": row["task_id"],
            "modality": modality,
            "algorithm": algorithm,
            "arm": arm,
            "seed": 17,
            "events": session.events,
            "result": session.result(),
            "output": str(path.relative_to(root)),
            "checkpoint": (
                str((output / "training" / modality / algorithm / "final").relative_to(root))
                if arm == "process_sft"
                else None
            ),
            "model_id": study["model_id"],
            "model_revision": study["model_revision"],
        }
        replay_visual_episode(root, row, report, views)
        write_json(path, report)
        results.append(str(path.relative_to(root)))
        progress("evaluation", completed=len(results), total=len(selected))
    return {"outcome": "PASS", "episodes": results, "modality": modality, "worker": worker}


def worker_main(root, payload):
    """A worker also stops itself if its parent dies or the hard deadline passes."""
    study, job, stage = payload["study"], payload["job"], payload["stage"]
    status = root / payload["status"]
    started = time.time()
    ctypes.CDLL(None).prctl(1, signal.SIGTERM)
    if os.getppid() != payload["parent_pid"]:
        raise RuntimeError("GPU stage owner has disappeared")

    def terminate(*args):
        raise SystemExit("worker terminated by owning stage")

    signal.signal(signal.SIGTERM, terminate)
    timer = threading.Timer(max(0, payload["hard_deadline"] - time.monotonic()), lambda: os._exit(124))
    timer.daemon = True
    timer.start()
    result: dict[str, Any] = {"outcome": "INVALID", "reason": "worker did not finish"}
    code = 0
    with Progress() as progress:
        try:
            if stage == "qualify":
                result = qualify_worker(root, study, payload["worker"], payload["soft_deadline"], progress)
            elif stage == "train":
                result = train_worker(root, study, job, payload["soft_deadline"], progress, payload["resume"])
            elif stage == "evaluate":
                result = evaluate_worker(
                    root, study, job, payload["worker"], payload["soft_deadline"], progress, payload["resume"]
                )
            else:
                raise ValueError("unknown GPU stage")
        except (Exception, SystemExit) as error:
            code = 2
            resource_stop = isinstance(error, SystemExit) or "VALID_STOP" in str(error) or "out of memory" in str(error)
            result = {
                "outcome": "VALID_STOP" if resource_stop else "INVALID",
                "reason": f"{type(error).__name__}: {error}",
            }
            progress(f"{stage}:stopped", **result)
        finally:
            result.update(
                study=study, started=started, finished=time.time(), job=job, code_revision=payload["code_revision"]
            )
            write_json(status, result)
            if result["outcome"] == "PASS":
                write_json(root / job["result_path"], result)
            timer.cancel()
    return code
