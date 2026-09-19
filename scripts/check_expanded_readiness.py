#!/usr/bin/env python
"""Read-only v5 checkpoint and hardware revalidation; never trains or loads a GPU model."""

import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.matched_execution import training_jobs, verify_training_cell


def main():
    import torch
    from safetensors import safe_open

    started = time.time()
    torch.set_num_threads(2)
    study = read(ROOT / "configs/experiments/matched-modalities/study-v5.json")
    cells = []
    for job in training_jobs(ROOT, study):
        report = verify_training_cell(ROOT, study, job)
        checkpoint = ROOT / report["final_checkpoint"]
        tensor_file = checkpoint / "adapter_model.safetensors"
        count = 0
        parameters = 0
        with safe_open(tensor_file, framework="pt", device="cpu") as tensors:
            for key in tensors.keys():
                tensor = tensors.get_tensor(key)
                if not torch.isfinite(tensor).all():
                    raise ValueError(f"nonfinite adapter tensor: {checkpoint}/{key}")
                count += 1
                parameters += tensor.numel()
        if not count:
            raise ValueError(f"empty adapter: {checkpoint}")
        cells.append(
            dict(
                job,
                checkpoint=str(checkpoint.relative_to(ROOT)),
                tensors=count,
                parameters=parameters,
                adapter_bytes=tensor_file.stat().st_size,
                steps=report["steps"],
                seed=report["seed"],
                provenance_passed=True,
                all_tensors_finite=True,
            )
        )
        print(f"verified {len(cells)}/12: {job['modality']} {job['algorithm']}", flush=True)
        if os.environ.get("EXPANDED_PROGRESS_PATH"):
            write(os.environ["EXPANDED_PROGRESS_PATH"], {"completed": len(cells)})
    if len(cells) != 12:
        raise ValueError("expected twelve v5 adapters")
    gpu = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,uuid,name,memory.total,memory.free", "--format=csv"], text=True
    )
    processes = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name,used_memory", "--format=csv"], text=True
    )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    report = dict(
        outcome="PASS",
        started=started,
        ended=time.time(),
        checkpoints=cells,
        cpu_seconds=usage.ru_utime + usage.ru_stime,
        hardware_csv=gpu,
        existing_processes_csv=processes,
        gpu_model_work_performed=False,
        qualification_scope="checkpoint tensors and provenance on CPU; hardware inventory only",
        branch_model_capacity_qualified=False,
    )
    write(ROOT / "docs/experiments/expanded-study/readiness.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
