#!/usr/bin/env python
"""Small allocated hardware diagnostic, not model capacity qualification."""

import json
import os
from pathlib import Path
import time

import torch

started = time.time()
assert torch.cuda.device_count() == 1
free, total = torch.cuda.mem_get_info()
x = torch.arange(1024, device="cuda", dtype=torch.float32)
assert torch.equal(x + x, x * 2)
torch.cuda.synchronize()
folder = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
report = dict(
    outcome="PASS",
    device=torch.cuda.get_device_name(0),
    cuda_visible_devices=os.environ["CUDA_VISIBLE_DEVICES"],
    master_port=os.environ["MASTER_PORT"],
    free_bytes=free,
    total_bytes=total,
    elapsed_seconds=time.time() - started,
    model_capacity_qualified=False,
)
(folder / "hardware.json").write_text(json.dumps(report, indent=2) + "\n")
path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
temporary = path.with_suffix(".tmp")
temporary.write_text(json.dumps({"completed": 1}))
temporary.replace(path)
print(json.dumps(report), flush=True)
