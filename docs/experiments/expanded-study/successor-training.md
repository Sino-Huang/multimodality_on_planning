# Successor-prediction training closeout (#89)

Goal 9 Phase 2 trained the frozen three-modality successor-SFT cells through the
shared scheduler and independently verified every checkpoint. Each cell ran once
from its verified BFS process adapter on the 512 verified release-001 teacher
labels in frozen membership order: one epoch, global batch 32, exactly 16
optimizer updates, seed 17, sequential sampler, final checkpoint only.

Compact evidence: [successor-training.json](successor-training.json). Runtime
artifacts (reports, receipts, checkpoints) follow the repository's local
outputs convention and are not Git assets.

| Modality | Records | Updates | Tensors changed | Source unchanged |
| --- | ---: | ---: | ---: | --- |
| text-state | 512 | 16 | 504/504 | yes |
| visual-state | 512 | 16 | 504/504 | yes |
| multimodal-state | 512 | 16 | 504/504 | yes |

Every cell binds its completion receipt to the frozen membership, the
release-001 teacher-label hash, the effective training arguments, the source
checkpoint manifest and the final checkpoint fingerprints. Source BFS process
adapters remain byte-identical (recursive per-file manifest). No intermediate
checkpoints exist; no cell required recovery or retraining; training losses are
finite. No development or final-panel diagnostics were declared or run. Goal 8
interaction payloads remain byte-identical to their published hashes.

Scheduler provenance: `successor-train-0` (GPU 0, port 18800, 0.437026 GPUh)
and `successor-train-1` (GPU 1, port 18801, 0.256753 GPUh), one attempt each,
both audit hooks returncode 0; `successor-train-final` (CPU) independently
re-verified all three cells and receipts, hook returncode 0. Training consumed
0.693779 GPU-hours; successor branch cumulative 10.209687 / 64. Runtime commit
`dd4818a`. Missing coverage: none.

Verification:

```bash
source ~/cd_vlaplan
EXPANDED_TERMINAL_PATH=outputs/expanded-study/v1/jobs/successor-train-0/1/terminal.json \
  python scripts/run_expanded_successor_training.py audit-training-worker --worker 0
EXPANDED_TERMINAL_PATH=outputs/expanded-study/v1/jobs/successor-train-1/1/terminal.json \
  python scripts/run_expanded_successor_training.py audit-training-worker --worker 1
EXPANDED_TERMINAL_PATH=outputs/expanded-study/v1/jobs/successor-train-final/1/terminal.json \
  python scripts/run_expanded_successor_training.py audit-training-final
```

#89's deliverable is satisfied; the final held-out comparison is #99 (Goal 9
Phase 3).
