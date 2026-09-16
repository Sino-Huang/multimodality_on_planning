# Expanded full-state successor protocol

Goal 7 defines the reusable boundary for #85 and freezes the ordinary config for
#86. `successor-protocol.json` is authoritative. The interface and runner were
implemented before any successor prediction was collected or any persistent
successor-training update was applied.

## Prediction and authority boundary

Each request supplies the complete task context, current dynamic state, BFS
Search Memory and one grounded action. Candidate `target_state_id`, target-state
and evaluation fields are removed before projection, so the process corpus does
not reveal the successor label. Static facts remain in task context and are
represented in the output only by an immutable SHA-256 context identity. They
are never mixed into the predicted dynamic state.

The model must return one strict JSON object containing the copied source state,
grounded action and static-context identity plus the complete sorted,
duplicate-free dynamic atoms and numeric fluents. It must also provide the
canonical state identity derived from those exact lists. The trusted verifier
classifies schema, static-context, source identity, action identity,
applicability, state identity and exact effect agreement separately. It retains
the raw prediction and trusted transition evidence. A wrong prediction is never
applied, normalized, repaired or replaced with the trusted state. Downstream
search status has its own field and is not inferred from local transition
validity.

Replay starts from a fresh PDDL authority and registers each non-initial source
only through its complete producing-action path. It then reruns strict parsing
and every authority check from the retained raw prediction. A correct prediction
may enter the search only after exact equality with the authority transition;
the runtime does not substitute a different state.

## Frozen membership and target allowance

The original ordered 512-record BFS membership contains 421 accepted
transitions and 91 frontier-retirement operations. Retirement has no successor
state and cannot be relabelled as one. The successor membership therefore keeps
those 421 accepted records and fills the remaining 91 positions by fixed
round-robin task order over unused accepted BFS transitions from the same 25
training tasks. This selection uses operation type and frozen order only, never
model predictions or held-out outcomes. Development and final tasks are
excluded.

All 512 complete targets were measured with the pinned Qwen tokenizer before
qualification. Target lengths range from 124 to 383 tokens; median is 236, p90
is 274, p95 is 299 and p99 is 383. The 512-token output allowance is the measured
maximum times the 1.25 qualification factor, rounded to the next 64-token
boundary. It is not the old 384-token operation allowance, and full states are
never truncated to fit that older cap.

All three modalities share the same 512 record IDs, query semantics and targets.
Visual and multimodal inputs use unlabelled 128px initial/current scenes with
complete static-context and partial-goal pages. Collection makes exactly one
call per fixed record and retains the raw prediction separately from the trusted
training target.

## Training and evaluation freeze

Each modality has one seed-17 successor-SFT run from its verified BFS process
adapter. Training uses 512 records, one epoch, microbatch 1, gradient
accumulation 32, global batch 32, a sequential sampler without reshuffling and
exactly 16 optimizer updates. Only the final checkpoint enters evaluation; no
training-seed variance is claimed.

Evaluation compares model-generated and trusted successors under the same
deterministic observable canonical BFS action order. A rejected generated state
is an invalid-successor outcome; the trusted successor is not inserted so search
can continue. Schema and transition validity, downstream search, calls and
compute are reported separately.

Cost admission is outcome blind. Qualification first projects the complete
three-modality, three-development-task and 24-unseen-task coverage. If it does
not fit 64 GPU-hours, the preregistered fallback keeps all development tasks and
one minimum exact-reference-cost task per each of the 12 unseen domains, with
ties broken by task ID. The full allowance is 11,916 model calls; the fallback
allowance is 4,062. If even the fallback cannot fit, the branch stops before
collection rather than dropping a domain or extending the budget.

## Preparation and qualification commands

The shared scheduler records attempts, 30-second heartbeats, terminal status,
GPU duration and independent completion hooks. Concurrent workers receive
distinct explicit `MASTER_PORT` values from the frozen 18800–18805 pool; the
actual GPU/port mapping is retained in qualification evidence.

```bash
source ~/cd_vlaplan && python scripts/run_expanded_study.py launch --ledger outputs/expanded-study/v1/budget.json --job configs/experiments/expanded-study/successor-prepare-job.json
source ~/cd_vlaplan && python scripts/qualify_expanded_successor.py prepare
source ~/cd_vlaplan && python scripts/run_expanded_study.py launch --ledger outputs/expanded-study/v1/budget.json --job configs/experiments/expanded-study/successor-qualification-0-job.json
source ~/cd_vlaplan && python scripts/run_expanded_study.py launch --ledger outputs/expanded-study/v1/budget.json --job configs/experiments/expanded-study/successor-qualification-1-job.json
source ~/cd_vlaplan && python scripts/run_expanded_study.py launch --ledger outputs/expanded-study/v1/budget.json --job configs/experiments/expanded-study/successor-qualification-final-job.json
```

The probes generate unscored scalar and repeated batches at the full 512-token
allowance and perform one discarded in-memory optimizer step per modality.
Source checkpoints must remain unchanged. Qualification collects zero scientific
predictions and performs zero persistent updates; Goals 8 and 9 own those stages.
