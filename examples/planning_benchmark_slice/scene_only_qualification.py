"""Native-scene GPU checks using shared shape bounds and all algorithm families."""

import gc
import time

from .modality_view_preparation import frozen_processor, write_json
from .scene_assets import read_json
from .visual_jobs import SemanticProbe, make_policy, probe_examples, qualify_batch
from .visual_model import VisualCollator, load_training_model


def semantic_algorithms(study, worker):
    # Every family/modality is checked; both GPUs independently measure the
    # common worst input and training shapes. This avoids duplicate family work.
    return study["algorithms"][worker :: len(study["launch"]["devices"])]


def qualify_scene_worker(root, study, worker, deadline, progress):
    import torch

    from .matched_workers import experiment, qualifying_examples

    previous = read_json(root / study["text_training_predecessor"])
    prior_path = root / previous["output_root"] / "qualification" / f"gpu-{worker}.json"
    prior = read_json(prior_path)
    if prior["study"] != previous or prior["outcome"] != "PASS":
        raise ValueError("retained text hardware evidence differs")
    native = read_json(root / study["scene_views"])
    if native["study"] != study or not native["text_inputs_unchanged"] or native["outcome"] != "PASS":
        raise ValueError("native qualification requires verified unchanged text inputs")
    results = {
        "text-state": {
            **prior["modalities"]["text-state"],
            "contract_id": study["study_id"],
            "retained_report": str(prior_path.relative_to(root)),
        }
    }
    output = root / study["output_root"] / "qualification"
    started = time.monotonic()
    ex = experiment(root, study, "visual-state", output, deadline)
    preparation_seconds = time.monotonic() - started
    panel = read_json(root / study["output_root"] / "preparation/final-panel.json")
    for modality in ("visual-state", "multimodal-state"):
        path = output / f"{modality}-gpu-{worker}.json"
        if path.exists():
            saved = read_json(path)
            if saved["study"] != study or saved["outcome"] != "PASS":
                raise ValueError("retained native qualification differs")
            results[modality] = saved
            continue

        def tagged(stage, modality=modality, **fields):
            progress(stage, **{"modality": modality, **fields})

        ex.config["modality"] = modality
        tagged("model_loading", completed=0, total=2)
        then = time.monotonic()
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        policy = make_policy(ex)
        inference_load = time.monotonic() - then + preparation_seconds
        policy.stop_at = deadline
        semantics = SemanticProbe(ex)
        algorithms = semantic_algorithms(study, worker)
        cases = []
        torch.cuda.reset_peak_memory_stats()
        for algorithm in algorithms:
            records = [r for r in ex.selected_records if r["algorithm"] == algorithm]
            paired = [
                max(records, key=lambda r: r["tokens"]["input"][modality]),
                min(records, key=lambda r: r["tokens"]["input"][modality]),
            ]
            examples = probe_examples(ex, paired, modality)

            def case_progress(stage, algorithm=algorithm, **fields):
                tagged(stage, algorithm=algorithm, **fields)

            qualify_batch(policy, paired, examples, semantics, case_progress)
            cases.append({"algorithm": algorithm, "record_ids": [r["record_id"] for r in paired]})
            for example in examples:
                for image in example["images"]:
                    image.close()
            tagged("scene_qualification:families", completed=len(cases), total=len(algorithms))

        # The largest final case must cover both all selected token lengths and
        # all image shapes/counts, rather than assuming larger pixels are free.
        finals = qualifying_examples(root, study, modality)
        selected_index, example = max(enumerate(finals), key=lambda pair: pair[1]["binding"]["input_tokens"])
        source_max = max(r["tokens"]["input"][modality] for r in ex.selected_records)
        maximum_pages = max(len(t["static_pages"]) + len(t["goal_pages"]) + 2 for t in native["tasks"].values())
        if example["binding"]["input_tokens"] < source_max or len(example["images"]) < maximum_pages:
            raise ValueError("final hardware probe does not cover the selected native input envelope")
        tagged("scene_qualification:forced_384", completed=0, total=1, input_tokens=example["binding"]["input_tokens"])
        torch.cuda.synchronize()
        then = time.monotonic()
        policy.generate([example], force_full_output=True)
        torch.cuda.synchronize()
        call_seconds = time.monotonic() - then
        timing = {
            "task_id": panel["tasks"][selected_index]["row"]["task_id"],
            "state": example["binding"]["state"],
            "input_tokens": example["binding"]["input_tokens"],
            "image_sizes": example["image_sizes"],
            "seconds_per_call": call_seconds,
            "output_tokens": 384,
        }
        inference_peak = torch.cuda.max_memory_allocated()
        for final in finals:
            for image in final["images"]:
                image.close()
        del policy, finals, examples
        gc.collect()
        torch.cuda.empty_cache()
        if time.monotonic() >= deadline:
            raise RuntimeError("VALID_STOP: qualification allowance exhausted before native backward probe")
        tagged("scene_qualification:training_load", completed=0, total=1)
        then = time.monotonic()
        model = load_training_model(ex.config)
        training_load = time.monotonic() - then + preparation_seconds
        optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=0.0)
        record = max(ex.selected_records, key=lambda r: r["tokens"]["input"][modality] + r["tokens"]["target"])
        then = time.monotonic()
        example = ex.corpus.training_example(record, modality)
        batch = {k: v.to("cuda:0") for k, v in VisualCollator(frozen_processor().processor)([example]).items()}
        if time.monotonic() >= deadline:
            raise RuntimeError("VALID_STOP: qualification allowance exhausted before native backward probe")
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss = model(**batch).loss
        loss.backward()
        optimizer.step()
        torch.cuda.synchronize()
        microstep = time.monotonic() - then
        then = time.monotonic()
        model.save_pretrained(output / f"disposable-{modality}-{worker}")
        save_seconds = time.monotonic() - then
        report = {
            "study": study,
            "contract_id": study["study_id"],
            "worker": worker,
            "outcome": "PASS",
            "modality": modality,
            "semantic_algorithms": algorithms,
            "semantic_cases": cases,
            "seconds_per_call": call_seconds,
            "training_microstep_seconds": microstep,
            "training_record_id": record["record_id"],
            "training_load_seconds": training_load,
            "inference_load_seconds": inference_load,
            "adapter_save_seconds": save_seconds,
            "timing_output_tokens": 384,
            "final_input_timing_probes": [timing],
            "covers_selected_input_envelope": True,
            "dtype": "float32",
            "attention_implementation": study["inference"]["attention"],
            "peak_allocated_bytes": max(inference_peak, torch.cuda.max_memory_allocated()),
            "device": torch.cuda.get_device_name(0),
            "gpu_free_bytes_before_model": free_bytes,
            "gpu_total_bytes": total_bytes,
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            "model_outcomes_used_for_selection": False,
        }
        write_json(path, report)
        results[modality] = report
        for image in example["images"]:
            image.close()
        del batch, loss, optimizer, model, example
        gc.collect()
        torch.cuda.empty_cache()
        tagged("scene_qualification:modality_complete", completed=len(results) - 1, total=2)
    return {"outcome": "PASS", "worker": worker, "modalities": results}
