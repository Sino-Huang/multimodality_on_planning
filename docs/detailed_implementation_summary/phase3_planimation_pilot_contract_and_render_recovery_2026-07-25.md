# Phase 3 Planimation Pilot Contract and Render Recovery

## Scope and Result

This work closed the seven-part Planimation pilot recovery plan without changing
the frozen selection, the approved pilot data, the cache, or the temporary
recovery roots during Todo 7. The final `stratified-pilot` receipt approves the
existing 52-pair, 2,568-state pilot. It does not approve the incomplete full
production corpus of 2,328 pairs and 537,696 expected render states.

The approved receipt is
`outputs/phase3_planimation_frames_stratified_pilot_20260725/diagnostics/rollout_promotion_receipt.json`.

## Todo 1: Graphplan Extraction

Graphplan reasoning now attaches to an `extracted_plan_replay` transition through
its nonempty extraction event, integer step index, and exact normalized equality
with `extraction.selected_plan[step_index]`. Matching action-layer data is
optional enrichment after that attachment. It isn't an alternate source of truth.
Forged source, event, Boolean step, and action mismatches remain fail-closed as
`trace_event_not_bound_to_replay_transition`.

Five retained action-layer-mismatched cases now report
`context_status="extraction_bound"`. Their truthful mandatory provenance payloads
are 267 to 268 characters, so the mandatory fields are preserved even when the
requested budget is 256 characters. The focused pairing and traversal suite
passed twice with 69 tests.

## Todo 2: Profile Contracts and Semantic Repair

The initial profile contract fixes were narrow:

1. Gripper geometry changed from zero size to 30 by 60.
2. Ferry cars changed to 100 by 70 while locations remained 150 by 150.
3. Elevators stopped redistributing passenger x during `served` handling.
4. Logistics adopted the current `%p`, `%t`, `%a`, `%l`, and `%c` selectors.

The strict semantic validator stayed unchanged during these profile repairs.
Later runtime canaries exposed two additional layout faults. Elevators needed
stable global passenger lanes. Ferry needed a concrete location y anchor plus
vertical car distribution for two cars at one location. The final Ferry profile
identity was recorded after the repair.
Its final authorized canary passed semantic validation with 6 of 6 expected
sprites.

## Todo 3: Fresh and Resume Launcher Contract

`temp_fast_planimation_render.sh` gained strict argument parsing, active-writer
checks, resume prerequisites, and selection-bound manifest, render, and release
verification. Fresh mode refuses an existing output root. Resume mode requires
the existing pilot root and its frozen selection.

Conda activation also required a narrow shell fix. The launcher disables
`nounset` only while sourcing `~/cd_vlaplan` and `.venv/bin/activate`, then
restores it before selection, rendering, and verification. The focused launcher
suite passed twice with 8 tests. Todo 7 did not rerun this launcher.

The operator commands are:

```bash
bash temp_fast_planimation_render.sh
PILOT_OUTPUT_ROOT=outputs/phase3_planimation_frames_stratified_pilot_20260725 bash temp_fast_planimation_render.sh --resume
```

The first command is for a fresh output root. The second resumes the named pilot
in place and reuses only cache entries that still pass identity and semantic
validation.

## Todo 4: Frozen Selection Verification

The frozen selection preserves the identity of the full source pairing
manifest, recorded as the source provenance. That identity is provenance for
the source from which selection occurred, not the identity of the 52-pair
output subset. The unchanged frozen selection file and the actual subset
pairing manifest each retain their recorded identities.

Selection-bound release verification checks exact pair-set equality and frozen
per-pair provenance. The source root identity is recorded with the selection.
Independent review added checks for `source_root_id`, `example_id`,
`active_planner_id`, and `instance_id`. The real 52-pair manifest verification
completed successfully.

## Todo 5: Runtime Canaries

Fresh canaries proved the repaired Gripper, Ferry, Elevators, and Logistics
profiles against the unchanged semantic validator. Historical failed attempts
remain preserved. These include Ferry expected-object coverage failure,
Elevators coincident bounds, and the first Ferry shared-location repair that
placed both cars at `(false, false)` because the location y origin was absent.

The final y-anchored Ferry canary completed on its first actual attempt. Cars
`c0` and `c1` occupied distinct, in-canvas vertical lanes within `l2`.

## Todo 6: Pilot Resume and Recovery History

The first exact resume was interrupted by the execution surface after 120
seconds. It had reached `state_render_started`, but no launcher exit receipt was
written. A later persistent run reached 200 states and stopped at five Ferry
semantic failures. The final Ferry profile repaired the concrete failing state.

The first green run then completed all 2,568 states with 2,058 cache hits. The
second green run completed all 2,568 as cache hits. Their generated telemetry was
not byte-identical because cache-hit counts changed, and the first snapshot did
not include the root VLM JSONL identities.

A direct third-run attempt first met a wrapper false positive in the raw
`pgrep -f` guard. A detached setup then failed while Conda deactivation ran under
`nounset`. The real third run later reached 2,568 successful cache hits, but the
host interrupted it before the verifier loop and exit receipt. That interruption
left the hybrid manifest non-production-complete.

One explicitly authorized replacement resume restored the complete output. It
exited 0, ran all three verifier modes, made zero remote render attempts, and
matched the complete second-green warm baseline across all 15 canonical paths,
all canonical identities, and all 5,324 cache paths.

## Todo 7: Minimal Rollout Contract Fix

The rollout gate previously treated the source manifest identity as though the
output had to be the full source manifest. That rejected a valid selected subset.
The minimal fix keeps the input pairing-manifest identity unchanged as source
provenance, while exact equality of the full frozen selected-pair record multiset
permits the output pairing manifest to be that selected subset.

That subset fallback is available only after the frozen selection supplies a
valid source-provenance value. Missing, uppercase, wrong-length, or otherwise
malformed values reject as `invalid_frozen_selection` before exact
selected-record equality can authorize the subset. The negative regression
recomputes the selection identity after removing or replacing the provenance
field, proving rejection comes from the provenance contract rather than a stale
selection identity.

The equality is over complete frozen records and multiplicity, not only pair
IDs. The gate therefore remains fail-closed for missing, extra, mutated, and
duplicate pair records. An isolated mutation probe changed the source-record
identity; selection-bound release verification rejected the drift,
and promotion retained both pairing identity and pair-identity mismatch reasons.

The regression was first run red and failed as expected because the source
manifest identity differed from the selected subset manifest. After the fix, the
regression and focused gate/verifier suite passed with 21 tests. Basedpyright
reported 0 errors, 0 warnings, and 0 notes. Compileall and `git diff --check`
both exited 0. Ruff wasn't available in the activated environment and wasn't
installed.

## Recovery Promotion Chain

The original failed temporary fixture attempt is preserved. It made one remote
request because `request_delay_seconds=1.0` was part of the renderer config
identity, which selected a different cache key instead of the pilot cache entry.

Recovery used the exact pilot renderer config: base URL
`https://planimation.planning.domains`, timeout 90 seconds, request delay 0.0,
and maximum attempts 3. Its config identity was recorded, and the fixture cache
key was recorded.

The clean recovery root ran a cache-only fixture first, then a cache-only
changed-canary. The fixture covered 1 state. Its receipt file-byte identity and
embedded receipt identity were both recorded.
The changed-canary covered 39 states across 18 cache directories and produced
a receipt with a recorded identity.
Both stages passed manifest, render, and release verification without an
external network connection.

Two later fixture setup attempts are retained as nonfatal history. One timed out
in the shell before generator output, with no connect syscall. The other omitted
`--dataset-root`, exited because the selected pairing record was absent, created
no state manifest, and made no network connection.

The actual pilot promotion used the changed-canary receipt as its prior receipt.
It ran once, exited 0, and produced the approved receipt.

## Final Approved Counts and Identities

The approved pilot has:

- 52 pair records.
- 2,568 state-render records, all successful cache hits.
- Full records, train/dev/test: 19/19/14.
- Step records, train/dev/test: 68/130/133.
- Search-traversal records, train/dev/test: 329/1160/696.
- Six domains: Blocksworld, Elevators, Ferry, Gripper, Logistics, and Towers of Hanoi.
- `output_mode="production"`, `partial=false`, `production_complete=true`, and `skipped={}`.

The frozen output identities are:

- State manifest.
- Hybrid manifest.
- Pairing manifest.

## Preservation Proof

Before promotion, the pilot contained 5,343 files, including 5,324 cache paths.
After promotion, every original file and cache path remained byte-identical.
Only `diagnostics/rollout_promotion_receipt.json` was added, bringing the file
count to 5,344. The original frozen selection was used directly and remained
unchanged. No pilot-bound replacement selection was created.

## Verification Commands

The Python commands use the required environment prefix:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_rollout_gates.py::test_promotion_accepts_exact_frozen_subset_from_larger_source_manifest
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_rollout_gates.py tests/phase3/test_verify_planimation_vlm.py
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/rollout_gate_selection.py scripts/phase3/rollout_gate_promotion.py tests/phase3/test_rollout_gates.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_planimation_vlm --output-root outputs/phase3_planimation_frames_stratified_pilot_20260725 --mode manifest --selection-file outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800/diagnostics/rollout_selection.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_planimation_vlm --output-root outputs/phase3_planimation_frames_stratified_pilot_20260725 --mode render --selection-file outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800/diagnostics/rollout_selection.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_planimation_vlm --output-root outputs/phase3_planimation_frames_stratified_pilot_20260725 --mode release --selection-file outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800/diagnostics/rollout_selection.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.rollout_gates assess --output-root outputs/phase3_planimation_frames_stratified_pilot_20260725 --stage stratified-pilot --selection-file outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800/diagnostics/rollout_selection.json --prior-receipt tmp/phase3_planimation_todo7_promotion_chain_20260726/recovery/changed-canary/diagnostics/rollout_promotion_receipt.json
git diff --check
```

The expected verifier success is manifest verification of 52 pairs; render
verification of 52 pairs and 2,568 states; and release verification of full
records 19/19/14, step records 68/130/133, search-traversal records
329/1160/696, and production complete. The three real pilot verifier commands
previously exited 0 with those results. All four operator commands use the
original frozen selection. The promotion command also requires the approved
changed-canary prior receipt at the exact path shown above. Its expected success
is `approved=true`, empty `reasons`, 52 pairs, and 2,568 states.

The three verifier commands are read-only checks of the pilot artifacts. The
`assess` command is different: it writes or refreshes only the actual pilot
`diagnostics/rollout_promotion_receipt.json`. It is an operator action, not a
read-only audit command. This documentation-only independent-review remediation
did not rerun the pilot verifiers, assessment, launcher, generator, or renderer.

## Limitation

This receipt approves only the frozen 52-pair stratified pilot. The full
2,328-pair, 537,696-state production corpus remains incomplete and must not be
described as promoted or complete.
