# F4 Scope-Fidelity Audit

## Verdict

APPROVE for the current worktree snapshot. This approval covers scope fidelity only. It does not approve active-corpus rollout: all four frozen roots remain legacy strict-v1-ineligible sources.

## Source-Root Integrity

The only top-level `outputs/` directories are `deprecated/` and these four frozen curriculum roots:

| Root | Files | Generated-file digest verification | File-list digest |
| --- | ---: | --- | --- |
| `outputs/phase3_curriculum_traces_15puzzle_easy_20260709_002417` | 1,393 | OK | `732f3df7c5f7a9974bd617862dfafc9ada8b560831f220b0c1766a64a482aa36` |
| `outputs/phase3_curriculum_traces_safe_no_visitall_20260708_122431` | 10,885 | OK | `2081d02b5d09af55affdaadb02edd8666fa26101051adc9b46a6de1e176c0ed1` |
| `outputs/phase3_curriculum_traces_visitall_20260708_191916` | 167 | OK | `c1f27e4cf17035488296b7ebf3b98ae91654f262fa626924b89a49614f641160` |
| `outputs/phase3_curriculum_traces_visitall_train_test_long_timeout_20260710_000503` | 1,255 | OK | `724d0c60c192405d0e775111bba09d827f37bc433638c95f7ee061bde820cfb4` |

`generation_manifest.json` in each root declares hashes for every generated JSONL and diagnostic artifact; all declared hashes recomputed exactly. `git diff --name-status HEAD -- outputs`, `git diff --cached --name-status HEAD -- outputs`, and porcelain status filtered to `outputs/` were empty. The roots are ignored by `.gitignore`, so Git cannot independently establish a historical content baseline; the persisted manifest digests and current file-list digests are the integrity evidence for this audit snapshot.

The four former `outputs/phase3_planimation_vlm_*_20260715` roots are absent, consistent with the recorded relocation to `tmp/`; no additional output root exists.

## Git-History and Tracking Boundary

- `HEAD` is `1f172e799d28a9d9cc767446e201b279ab32f6a7` (`collecting reasoning traces with certain domains`, 2026-07-08).
- `git ls-files --stage outputs | wc -l` returned `0`; `git ls-tree -r --name-only HEAD -- outputs` was empty.
- No output path is modified or staged. No Git operation was performed by this audit.
- Historical commits `31dfbef` and `e0ddccb` respectively added and then removed earlier generated output paths. They predate `HEAD`; this audit neither rewrites nor approves that historical provenance. The current committed tree contains no output artifact.

## Planner Semantic Boundary

The only diff in tracked planner implementations is trace serialization metadata:

- FF, GBFS, and IW add `trace_contract_version` plus explicit event labels.
- Graphplan adds only `trace_contract_version`.
- GBFS/IW/FF search ordering, goal checks, resource checks, action selection, and state transitions are unchanged in the diff.

Focused regression command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_gbfs.py tests/phase3/test_phase3_local_trace_safety.py tests/phase3/test_phase3_pipeline_regressions.py tests/phase3/test_traversal_trace_contracts.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_planimation_search_traversal.py -q
```

Result: `59 passed in 1.42s`.

## Graphplan Nonvisual Boundary

Call path:

```text
trace_contracts._graphplan_events
  -> traversal_states.project_traversal_state_candidates
  -> graphplan_replay.project_graphplan_replay
  -> graphplan_render_transitions.graphplan_render_transitions
  -> planimation_pairing_implementation._render_transitions
  -> render_replay_states
```

`_graphplan_events` produces semantic proposition/action/extraction events with no concrete state source or hash and rejects injected visual fields. `project_graphplan_replay` excludes every non-extraction event as `graphplan_nonvisual_event:*`. It derives candidates only after normalized extracted actions exist in grounded PDDL, apply to every predecessor state, and leave the final state satisfying the PDDL goal. Those generated candidates alone use `event_kind` and `state_source` equal to `extracted_plan_replay`. `graphplan_render_transitions` rejects any other source before a rendering transition is built, while Graphplan returns no search-traversal transitions.

Adverse probes passed: forged layer `state_atoms`, forged extraction parent linkage, malformed extraction plans, unknown extraction actions, and inapplicable extraction actions yield controlled rejection/no candidate. Graphplan semantic layers yield no `search_traversal` record.

## Structural Checks

`lsp_diagnostics` reported no diagnostics for `gbfs.py`, `local_graphplan.py`, `local_iw.py`, `local_planners.py`, `traversal_states.py`, `graphplan_replay.py`, and `graphplan_render_transitions.py`. `git diff --check` was clean.

## DoneClaim

```json
{"gate":"F4","verdict":"APPROVE","output_root_integrity":"verified_current_snapshot","tracked_output_artifacts":0,"staged_output_artifacts":0,"planner_algorithm_change":"none_found","graphplan_layers_renderable":false,"active_corpus_rollout":"not_approved"}
```

## AdversarialVerify

```json
{"manifest_digest_recompute":"4/4 OK","output_layout":"only deprecated plus four frozen roots","forbidden_planimation_output_roots":"absent","historical_output_commits":"pre-HEAD add/remove observed; none in current tree","focused_regressions":"59 passed","graphplan_forged_visual_or_replay_inputs":"rejected","lsp":"clean"}
```
