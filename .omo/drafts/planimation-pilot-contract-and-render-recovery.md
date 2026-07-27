---
slug: planimation-pilot-contract-and-render-recovery
status: planned
intent: clear
review_required: false
pending-action: user chooses start-work or high-accuracy review
approach: Bind Graphplan replay reasoning to validated extraction steps, repair four domain animation profiles without weakening semantic validation, preserve valid state caches, rerender only cache-invalidated states, rebuild VLM records, and pass strict release verification.
---

# Draft: planimation-pilot-contract-and-render-recovery

## Components (topology ledger)

| id | outcome | status | evidence path |
|---|---|---|---|
| C1 | Every validated Graphplan replay step has deterministic reasoning provenance and no valid extraction falls back to plan-level context. | active | `scripts/phase3/graphplan_replay.py`, `scripts/phase3/planimation_pairing_reasoning.py`, `scripts/phase3/planimation_pairing_records.py` |
| C2 | Gripper, Elevators, Ferry, and Logistics profiles produce nondegenerate, noncoincident, covered sprites under the unchanged strict semantic gate. | active | `data/pddl_instances/{gripper,elevators,ferry,logistics}`, `scripts/phase3/render_semantics.py`, retained failed VFGs under the pilot output root |
| C3 | Recovery preserves valid cache entries, retries profile-invalidated/failed states, and reconstructs all VLM records without deleting the pilot output root. | active | `scripts/phase3/planimation_pairing_rendering.py`, `scripts/phase3/generate_planimation_vlm.py`, `temp_fast_planimation_render.sh` |
| C4 | Focused tests, real domain probes, full pilot rerender, and release verification prove 52-pair/2,568-state completeness. | active | `tests/phase3`, `scripts/phase3/verify_planimation_vlm.py`, `scripts/phase3/rollout_gates.py` |

## Open assumptions (announced defaults)

| assumption | adopted default | rationale | reversible? |
|---|---|---|---|
| Test strategy | TDD with focused unit/contract tests before product edits, followed by real Planimation probes and release verification. | Project rules prefer TDD; runtime failures require red-to-green evidence. | yes |
| Source data treatment | Do not hand-edit `outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round/*.jsonl`. | These are immutable source snapshots bound by hashes/provenance. | yes |
| Graphplan fix boundary | Bind reasoning to the validated extraction event and selected-plan step; retain action-layer metadata only as optional enrichment. | Replay is sourced from `extraction.selected_plan`; action layers are planner semantics and need not contain every serial replay action. | yes |
| Semantic validation | Keep nonnumeric, out-of-canvas, coincident, degenerate, and uncovered sprite checks strict. | The retained VFGs prove profile defects, not validator false positives. | yes |
| Cache policy | Preserve `state_cache`; profile SHA changes invalidate only affected domains, failed entries retry, and unchanged valid states remain hits. | `_cache_identity()` and `_validated_cache()` already implement this contract. | yes |

## Findings (cited - path:lines)

- `scripts/phase3/planimation_pairing_reasoning.py:36-44` binds Graphplan context only by searching `action_layers`, despite replay provenance coming from extraction.
- `scripts/phase3/graphplan_replay.py:47-66` validates `extraction.selected_plan` action-by-action against PDDL and goal satisfaction.
- `scripts/phase3/graphplan_replay.py:69-113` gives every replay candidate an extraction event ID and deterministic extraction step index.
- `scripts/phase3/planimation_pairing_records.py:61-67` correctly rejects only the remaining `plan_level` fallback.
- Retained pilot evidence identifies five valid Graphplan replay actions that are absent from `action_layers`; the first is pair `1334a50e2463fde7e6e711149eace78f`, step 6.
- `data/pddl_instances/gripper/gripper_AP.pddl:107-118` assigns both gripper sprites width and height zero; the retained VFG confirms zero-area bounds.
- `data/pddl_instances/ferry/ap.pddl:35-79` gives locations and cars identical 150x150 dimensions; the retained VFG confirms a car/location exact-bound collision.
- `data/pddl_instances/elevators/elevators_ap.pddl:61-68` resets every served passenger's x position independently; the retained VFG confirms two passengers at identical bounds.
- `data/pddl_instances/logistics/logistics_ap.pddl:47-128` uses a default package visual and legacy hard-coded object names; the current generated problem uses `a0`, `c0`, `t0`, `l0-0`, and `p0`, and the retained VFG confirms most objects fall back to identical package bounds.
- `scripts/phase3/render_semantics.py:66-110` correctly rejects coincident and degenerate sprite geometry before coverage analysis.
- `scripts/phase3/planimation_pairing_rendering.py` binds cache identity to profile SHA and validates artifacts before cache reuse; successful cache entries can survive targeted profile changes.
- `scripts/phase3/planimation_release_verification.py:89-149` requires complete per-pair render coverage and reconciled VLM record counts.
- Mandatory gap analysis found that generic reconciliation alone can accept a smaller internally consistent subset; the final plan therefore binds verification to exact equality with the frozen selection and immutable per-pair source provenance while preserving generic verifier behavior when no selection is supplied.
- Frozen rollout selection facts: 52 unique pair IDs; `input_pairing_manifest_sha256=de298099d2b3456322f6ebf692b4fd1307a3b146a7e27aff48848794da1cd9d8`; authoritative source root `outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round`; `source_root_sha256=a8c1fe317f5f3909aea4af28c519aa4af9c4eefb406667c644b46cd15aba3214`.
- Dirty-worktree guard: pre-existing changes under `.omo/` and the untracked launcher must not be overwritten or reverted by the implementation worker.

## Decisions (with rationale)

- Keep `TraceContractError("trace_event_not_bound_to_replay_transition")` for genuinely unbound transitions; fix the Graphplan binding input rather than suppressing the error.
- Do not alter Graphplan source traces merely to force serial plan actions into planning-graph layers.
- Match Graphplan reasoning by validated `extraction.selected_plan[step_index]`, require action equality and extraction provenance, and attach action-layer/mutex context only when available.
- Repair animation profiles, not `render_semantics.py`: Gripper receives nonzero gripper dimensions; Ferry car bounds differ from location bounds; Elevators preserve distributed passenger x positions after service; Logistics uses generated-name selectors instead of a catch-all package visual and legacy object lists.
- Preserve the existing pilot root and cache. Rebuild manifests/records in place only through supported commands; never delete `state_cache`.
- Default launcher behavior remains fail-closed for an existing root; recovery must be explicit so accidental overwrites stay impossible.

## Scope IN

- Graphplan extraction-step reasoning binding and persisted reasoning context.
- Regression coverage for repeated/missing action-layer membership and true unbound failure.
- Four animation-profile corrections and real retained/remote semantic probes.
- Cache-preserving pilot recovery workflow, explicit launcher recovery path, VLM reconstruction, and strict release/promotion gates.
- Operational documentation and implementation summary required by repository rules.

## Scope OUT (Must NOT have)

- No weakening or removal of semantic image gates.
- No manual patching of immutable source JSONL records or generated VFG/PNG cache artifacts.
- No deletion of the existing pilot output root or valid cache entries.
- No broad planner rewrite, trace schema migration unrelated to extraction-step provenance, or new rendering dependency.
- No acceptance of partial/bounded-smoke output as a release.

## Open questions

None. The user approved `context_status="extraction_bound"` with extraction-step provenance and optional action-layer enrichment.

## Approval gate

status: approved
approved approach: Implement the four-component topology and the explicit `extraction_bound` output contract.
next workflow action: hand off `.omo/plans/planimation-pilot-contract-and-render-recovery.md`; the user chooses execution via `/start-work` or optional dual high-accuracy review.
