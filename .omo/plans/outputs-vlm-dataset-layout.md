# Outputs VLM Dataset Layout - Work Plan

## TL;DR (For humans)

Replace the rejected `outputs/datasets/...` symlink view and all flat live output roots with exactly three top-level directories: `outputs/reasoning_traces/`, `outputs/image_frames/`, and `outputs/deprecated/`.

The approved curriculum root moves into `reasoning_traces`; the approved pilot and frozen selection roots move into `image_frames`; the pilot's nine JSONL files are copied into a clearly structured, independently hashed `reasoning_traces/vlm_records/` tree. Twelve superseded runs move into `deprecated/phase3/`, and the two failed hidden receipt sidecars are preserved in `deprecated/receipts/failed-output-reorganization-20260726/`.

The migration must use a GPFS-compatible ordinary directory rename only while holding an exclusive organizer lock, with destination-absence checks, source/destination snapshots, and parent-directory fsyncs. New receipts use append-only `O_EXCL` journal files instead of the broken `renameat2` transaction protocol. It does not rewrite historical JSONLs, manifests, evidence, or hashes.

## Scope

- Every command executed by this work begins with `source ~/cd_vlaplan &&`.
- The only top-level `outputs/` entries after a successful run are `reasoning_traces/`, `image_frames/`, and `deprecated/`.
- Preserve all existing `outputs/deprecated/` content. Do not flatten, rewrite, or reclassify it.
- Do not delete any data. All removals from a source location are completed by verified same-filesystem rename, never `rm`.
- Do not leave `outputs/datasets/`, compatibility symlinks, hidden receipt sidecars, temporary roots, or organizer locks below `outputs/`.

## Verification strategy

- Use deterministic inventory snapshots for every moved root: directory count, file count, symlink count, total bytes, and tree SHA-256.
- Require the pre-move source snapshot to equal the post-move destination snapshot for all fifteen live roots.
- For the nine physical VLM-record copies, require SHA-256, byte length, JSONL line count, and parsed record count to match their canonical source files.
- Verify every active launcher, verifier, and path-contract test against the new locations; retain old path strings only inside immutable historical artifacts.
- Execute focused tests, compile checks, and one real `catalog`, `apply`, and `verify` run. All commands include `source ~/cd_vlaplan &&`.

## Execution strategy

- Replace the old layout contract instead of layering another view on it. The contract is an allow-list of the fifteen current flat roots and no other live root.
- Use a repository-scoped exclusive `flock` outside `outputs/`. Before mutation, reject active writers, malformed paths, cross-filesystem destinations, non-directory roots, source snapshot drift, existing destinations, and unexpected top-level roots.
- Use a short, documented ordinary `os.rename` fallback only for same-device directory moves on GPFS after the lock, final `lstat` checks, and snapshot validation. Fsync both parents, then verify source absence and destination equality. The migration must fail closed on any discrepancy; it must never overwrite a destination.
- Replace mutable final receipts with an append-only journal under `outputs/deprecated/receipts/output-reorganization-<run-id>/`. Each journal record is created mode `0600` with `O_CREAT|O_EXCL`, content-fsynced, and parent-fsynced. A `complete.json` is created only after every postcondition passes.

## Todos

- [x] 1. Replace the output layout contract with the three-root topology
  References: `scripts/phase3/output_layout_contracts.py`; `tests/phase3/test_output_layout_contracts.py`; the prior rejected `VIEW_ROOT` and `VIEW_LINKS` contract.
  Work: remove the `outputs/datasets/...` view model and encode these exact destinations:
  `outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round`;
  `outputs/reasoning_traces/vlm_records/stratified_pilot_20260725/{full_reasoning,step_vlm,search_traversal}/{train,dev,test}.jsonl`;
  `outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725`;
  `outputs/image_frames/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800`.
  Keep the nine canonical pilot JSONLs in the moved pilot run and define the new VLM-record tree as physical, immutable copies. Encode an explicit source-to-copy map and no new symlink behavior.
  Acceptance: the contract rejects paths outside the three roots, lists exactly fifteen input roots, and derives no `outputs/datasets` path.
  QA: `source ~/cd_vlaplan && pytest -q tests/phase3/test_output_layout_contracts.py`; add cases for the three category roots, each record family/split, collision rejection, and prohibition of symlinks.

- [x] 2. Classify and relocate all current flat roots
  References: current top-level inventory; `scripts/phase3/output_layout_contracts.py`; existing `outputs/deprecated/phase3/` conventions.
  Work: move the approved strict curriculum root and two approved frame roots to the destinations in Todo 1. Move the following twelve roots unchanged into `outputs/deprecated/phase3/curriculum_traces/` or `outputs/deprecated/phase3/planimation_runs/`, retaining each basename:
  `phase3_curriculum_traces_15puzzle_easy_20260709_002417`, `phase3_curriculum_traces_15puzzle_easy_strict_v1_1st_round`, `phase3_curriculum_traces_safe_no_visitall_20260708_122431`, `phase3_curriculum_traces_visitall_20260708_191916`, `phase3_curriculum_traces_visitall_strict_v1_1st_round`, `phase3_curriculum_traces_visitall_train_test_long_timeout_20260710_000503`, `phase3_planimation_bounded_repro_20260721_2130`, `phase3_planimation_elevators_profile_probe_20260722_100300`, `phase3_planimation_frames_15puzzle_easy_20260721_214258`, `phase3_planimation_frames_safe_no_visitall_20260721_044105`, `phase3_planimation_frames_visitall_20260721_213129`, and `phase3_planimation_smoke_blocksworld_20260722_001817`.
  Acceptance: every source has exactly one destination classification; unknown live roots abort the migration; existing deprecated roots are untouched.
  QA: `source ~/cd_vlaplan && pytest -q tests/phase3/test_organize_outputs_semantics.py tests/phase3/test_organize_outputs.py`.

- [x] 3. Replace GPFS-incompatible rename and receipt behavior
  References: `scripts/phase3/output_layout_rename.py`; `scripts/phase3/output_layout_receipt_transaction.py`; `scripts/phase3/output_layout_receipt_fs.py`; receipt recovery tests.
  Work: retain the existing hardened path validation and snapshot logic, but route data-root moves through a tested same-device ordinary-rename implementation after organizer lock acquisition and final no-destination checks. Do not use `RENAME_NOREPLACE` or `RENAME_EXCHANGE` for the new migration. Replace mutable receipt publication with append-only journal creation using exclusive file creation and fsync; make resume derive state from immutable journal records.
  Acceptance: a GPFS `EINVAL` from `renameat2` cannot prevent the new code path; destination collisions, source drift, cross-device moves, and journal-name collisions abort without clobbering data.
  QA: `source ~/cd_vlaplan && pytest -q tests/phase3/test_output_layout_rename.py tests/phase3/test_output_layout_receipt_transaction.py tests/phase3/test_output_layout_receipt_recovery_adversarial.py`; add focused ordinary-rename, interruption/resume, and append-only-journal tests.

- [x] 4. Preserve and quarantine the failed receipt sidecars
  References: `outputs/deprecated/phase3/.output_reorganization_20260726.json.txn`; `outputs/deprecated/phase3/.output_reorganization_20260726.json.swap`; `scripts/phase3/output_layout_receipt_transaction.py`.
  Work: before the new migration, validate that both sidecars are regular mode-`0600` files, that the transaction identifies `.swap`, and that the transaction canonical SHA-256/size equals the swap payload. Record the observed hashes, inode identities, state `prepared`, and absence of the final receipt. Under the exclusive organizer lock, ordinary-rename both files into `outputs/deprecated/receipts/failed-output-reorganization-20260726/` with their original basenames, then write a new append-only recovery receipt in that directory. No data root is moved during this recovery operation.
  Acceptance: sidecar recovery has a dedicated journal record; the old hidden paths are absent; the two quarantined files match their pre-move hashes and remain mode `0600`; final-receipt recovery is not attempted through GPFS `renameat2`.
  QA: `source ~/cd_vlaplan && pytest -q tests/phase3/test_output_layout_receipt_recovery_adversarial.py`; add real-layout read-only validation and synthetic quarantine tests, including hash mismatch and destination collision failures.

- [x] 5. Materialize and verify physical VLM-record copies
  References: `outputs/phase3_planimation_frames_stratified_pilot_20260725`; Planimation record consumers discovered in `scripts/phase3/` and `tests/phase3/`.
  Work: after the pilot root is verified at its image-frame destination, create the nine record-family/split files in `reasoning_traces/vlm_records/stratified_pilot_20260725/` by private temporary-file copy, content fsync, hash comparison, and no-clobber publication. Publish an immutable record manifest mapping each copy to its canonical pilot source and expected digest; preserve the copied JSONL bytes exactly.
  Acceptance: the copy set totals nine files and 14,473,377 bytes at current inventory; every copy has exactly matching SHA-256, length, line count, and decoded JSON records; source files remain unchanged.
  QA: `source ~/cd_vlaplan && pytest -q tests/phase3/test_output_layout_view.py tests/phase3/test_output_layout_protected_content_security.py`; replace obsolete symlink assertions with physical-copy integrity assertions.

- [x] 6. Update live consumers and preserve historical provenance
  References: `scripts/phase3/planimation_pairing_contracts.py`; `scripts/phase3/planimation_pairing_source.py`; `scripts/phase3/generate_planimation_vlm.py`; `temprun.sh`; `temp_fast_planimation_render.sh`; `tests/phase3/test_fast_planimation_launcher.py`.
  Work: update only active code, launchers, tests, and documentation to use the new curriculum/image-frame/record-copy locations. Keep historical paths inside frozen JSONL, manifests, reports, receipts, and archived evidence unchanged. Consumer validation must resolve canonical image files for frame access and the copied record set for text-only training inputs.
  Acceptance: every live path reference resolves after migration; no active consumer points to a flat root or `outputs/datasets`; immutable provenance content is byte-for-byte unchanged.
  QA: `source ~/cd_vlaplan && pytest -q tests/phase3/test_fast_planimation_launcher.py tests/phase3/test_planimation_pairing_contracts.py`; run the applicable real read-only release-verification commands from the updated operator documentation.

- [x] 7. Execute the guarded real migration and publish operator evidence
  References: `scripts/phase3/organize_outputs.py`; `scripts/phase3/organize_outputs_preflight.py`; `scripts/phase3/output_layout_snapshot.py`; `.omo/knowledges/` Phase 3 records.
  Work: capture a preflight inventory, fifteen pre-move snapshots, sidecar evidence, filesystem identities, free space, and active-writer check. Run the one-time `apply`, then `verify`, and store the journal, snapshot comparisons, root listing, and copy-manifest verification under `outputs/deprecated/receipts/`. Document the layout, copy policy, rollback/resume rules, exact commands, and the GPFS residual race boundary.
  Acceptance: `find outputs -maxdepth 1 -mindepth 1` reports only the three category directories; all fifteen source roots are absent; all destinations pass snapshot equality; the journal contains `complete.json`; no hidden sidecar or `outputs/datasets` entry remains.
  QA: `source ~/cd_vlaplan && python -m scripts.phase3.organize_outputs catalog --repo-root .`; `source ~/cd_vlaplan && python -m scripts.phase3.organize_outputs apply --repo-root .`; `source ~/cd_vlaplan && python -m scripts.phase3.organize_outputs verify --repo-root .`; repeat `verify` and require unchanged receipt identities and snapshot hashes.

## Final verification wave

- [x] F1. Run `source ~/cd_vlaplan && pytest -q tests/phase3/test_output_layout_contracts.py tests/phase3/test_organize_outputs.py tests/phase3/test_fast_planimation_launcher.py tests/phase3/test_planimation_compatibility_references.py` and require zero failures. The removed symlink-view tests are intentionally excluded because the approved layout forbids `outputs/datasets` and new symlink views.
- [x] F2. Run `source ~/cd_vlaplan && python -m compileall -q scripts/phase3 tests/phase3` and `source ~/cd_vlaplan && git diff --check`; require zero diagnostics and no whitespace errors.
- [x] F3. Run the real `catalog`, `apply`, and `verify` commands from Todo 7, then manually inspect the three-category top-level tree, sidecar quarantine receipt, all nine physical-copy hashes, and all fifteen move snapshots.
- [x] F4. Confirm the must-not-have list: no data deletion, no rewritten immutable artifacts, no `outputs/datasets`, no new symlink view, no flat live roots, no hidden receipt sidecars at the former path, and no unrelated output changes.

## Commit strategy

- Do not create a commit unless explicitly requested.
- If requested, exclude output data and receipts from the commit unless they are intentionally versioned; stage only source, tests, documentation, and the updated plan.

## Success criteria

- `outputs/` has exactly the three requested top-level categories.
- Textual curriculum data and physical VLM JSONL copies are discoverable under `reasoning_traces/`.
- Canonical image/state caches are discoverable under `image_frames/`, with each VLM-record copy hash-matched to its canonical source.
- The twelve obsolete roots and two failed receipt sidecars are preserved under `deprecated/` with immutable recovery/migration evidence.
- The GPFS-compatible migration completes without relying on `renameat2(..., RENAME_NOREPLACE)`, and verification proves no data root changed content.
