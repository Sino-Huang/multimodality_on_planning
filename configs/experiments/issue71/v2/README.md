# Issue 71: matched modality development freeze v2

This completes the **design freeze and conditional authorization**, not bulk
rendering, corpus release, training, hardware qualification or model evaluation.
The earlier v1 candidate/VALID_STOP is retained unchanged. v2 uses a new phase
ID, authorization, gate receipt and `outputs/modality_phase/issue71-v2` root.

```bash
source ~/cd_vlaplan
python scripts/prepare_modality_issue71.py --dry-run
```

The command prints stage progress and coverage and makes no writes, HTTP or
model calls. `outcome: PASS, phase_authorized: true` confirms the recorded
freeze. `start_permitted: false` states that this dry-run is **not** a
per-attempt launch receipt. No long experiment is needed to finish #71.

## How images map to the reasoning trace

Every decision keeps its task, algorithm, decision position, textual rationale,
Typed Search Operation and trusted runtime result. The image binding is:

```text
observation at decision k -> current state image + task partial-goal image
                         -> textual Typed Search Operation k
accepted runtime result  -> successor state image (available only after k)
```

Collect every distinct replayed observation/result state in the **complete
selected search trace**, including off-solution branches. Include any additional
state explicitly exposed by the observation adapter. Do not render only the
winning plan. Repeated states reuse a first-occurrence image within that task
through semantic atoms/fluents, without hashes. Different decisions can share
the same image but have different Search Memory and targets.

Root-to-node paths from the actual search parent links are supplied to the
localhost backend. Planimation need not solve them or reach the goal. Shared
prefixes can supply multiple frames. Initial frames come from a non-empty
supplied path; tasks without any such path explicitly stop under the current
renderer contract. No silent solver call or arbitrary replacement task is allowed.

The model sees the current observation, not the entire image history or the
future successor/answer image. Frontier/visited/candidate information remains in
the bounded typed Search Memory. We do not render a fresh picture of every
frontier entry for every operation. The goal image contains partial constraints,
not a secretly completed goal-state solution. Invalid operations get a charged
failure result, not an invented successor image.

State images retain domain scenes plus complete labelled relation panels.
The same goal image is reusable across the task. Text-state omits the images;
visual-state omits direct state/goal relational text fields; multimodal-state
has both. Instructions and Search Memory remain shared text in all conditions.
This is annotated visual search, not an unannotated-scene perception claim.

## Frozen sources and coverage

`panel.json` names every selected task, source trace, split, exact decision and
expansion cost, plus all 18 new complete-group exclusions. Selection reads no
model outcomes. The 11 additive pairs already excluded by #64 remain outside
this source release; they are not counted again among these 18 exclusions.

| Setting | Train episodes | Dev episodes | Reference decisions, train + dev |
| --- | ---: | ---: | ---: |
| BFS | 44 | 45 | 24,026 |
| Full BFWS | 58 | 30 | 22,673 |
| Weighted h_add, w=3 | 41 | 23 | 16,493 |
| Greedy h_add | 41 | 23 | 15,038 |

Total: 241 task groups, 305 algorithm episodes, 78,230 decision positions per
modality, hence 915 episode projections and 234,690 decision projections over
three modalities if all later render/corpus checks pass. This is **planned
coverage**, not a produced corpus. Counts of unique frames are determined by
semantic replay in #72, not equated with decisions or expansions.

Complete episodes have at most 1,024 reference decisions and at most 2,048
model calls. Additive pairs are retained/excluded together. No segmentation or
image/input truncation is permitted. Source whole-instance splits remain fixed;
the corpus release must prove isolation and parity under its actual projection.

`render.json` binds all 15 existing domain profiles by repository-relative path.
Their presence was inspected; it does not imply generated-task compatibility.
No profile/task transformation is authorized by default. The #72 preflight
must prove compatibility and supplied-path bindings before collection.

The frozen processor is Qwen3-VL-8B-Instruct at the recorded model revision.
The 8,192-token context reserves 384 output tokens and 7,808 input tokens
including images/chat template; input bins end at 7,808. Image dimensions are
1,024 × 1,536 with size-18 DejaVuSans; memory is 32,768 bytes and 16 accepted
deltas, identical across modalities. Observations that cannot fit stop rather
than silently losing facts. Profile/font/input feasibility is not assumed from
the tiny #70 result.

One independent seed-17 adapter is trained per algorithm/modality cell, 12 runs
total, using two epochs (the existing additive development schedule, standardized
across these new matched cells). Historical text adapters are not substituted
for newly matched text inputs. Only final checkpoints enter rollouts; five
evaluation seeds do not create five training replicates. See `checkpoint.json`
for the frozen optimizer/LoRA settings and `matrix.json` for thresholds and
whole-instance paired uncertainty. Competence is separate from superiority
over the oracle-assisted random-valid control.

## Required downstream gate

Every #72–#77 runner must call `load_modality_phase().permission(...)` before
any task/HTTP/model work. Its run binding must use the phase ID and the exact
output `outputs/modality_phase/issue71-v2/{stage}/{attempt_id}`. Both matching
per-attempt gate/authorization receipts **and** this phase authorization are
required. An attempt cannot be reused for a different stage. Completed attempt
outputs must be preserved; retries use new attempt identities.

The stage graph is:

```text
render_preflight -> render -> corpus -> training -> qualification -> evaluation -> synthesis
```

Corpus and training are also explicit prerequisites of qualification/evaluation.
Complete phase-scoped predecessor reports must carry all frozen cells and the
required scientific check verdicts listed in `matrix.json`. Missing evidence
stops work; a fabricated/inconsistent PASS is INVALID. VALID_STOP/ANCESTOR_STOP
produce gated-not-run receipts. Permission to start never claims completion.

#72 owns profile/trace mapping preflight and complete render collection; #73/#74
own all-family observation adapters, matched corpus materialization and semantic
release checks. Those checks are required **before training**, not before the
configuration freeze itself. #75/#76 own model and actual hardware work.

Hardware qualification must measure float32 inference, scalar/batch and repeated
batch semantic agreement, adapter isolation and all occupied input bins; no
assumed bf16 equivalence. Try full selected development coverage first, then
the frozen cost-only domain panel, shared across modalities and conditions.
One clock includes qualification: certify rollout by 15 hours, stop new calls
at 18 hours, finish/adjudicate within 20 hours. Partial selected coverage never
passes. No precision fallback or deadline reset on resume is authorized.
Long runners must flush progress/ETA and heartbeat within 30 seconds; concurrent
torch launches require distinct recorded MASTER_PORT values.

No hashes, checksums, artifact-integrity or regeneration comparisons are active
requirements. Existing model revisions and historical source identifiers are
references, not new integrity mechanisms. All retained checks concern scientific
semantics, scope, coverage or bounded resource use.
