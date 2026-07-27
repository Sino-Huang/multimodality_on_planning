# Output Layout Runtime Audit

Verdict: FAIL

The independent layout, receipt, sidecar, and VLM copy checks passed. The required
verification command did not exit 0: both exact invocations blocked on the shared
organizer lock and were interrupted with exit 130. PASS is therefore disallowed by
the task gate.

## Hypotheses

| ID | Hypothesis | Distinguishing observed check | Conclusion |
|---|---|---|---|
| H1 | Migration is incomplete or stale roots remain. | `find outputs -mindepth 1 -maxdepth 1` returned exactly `deprecated`, `image_frames`, `reasoning_traces`; the four known flat paths were absent; all 15 prepared source paths were absent and their destinations were real directories. | Rejected by independent runtime tree checks. |
| H2 | VLM copies or referenced frame artifacts are corrupt or missing. | The receipt listed 9 records. Every source and destination existed; both sides matched receipt SHA-256, byte length, JSONL line count, and parsed-record count. | Rejected by independent hash and parse checks. |
| H3 | Receipt/journal verification masks an inconsistency. | `prepared.json` was `prepared` with 15 relocations; 15 `move-*.json` records had indexes 0..14 and state `moved`; `records.json` listed 9 present destinations totaling 14,473,377 bytes; `complete.json` was `complete`; independent checks agreed. | Rejected by journal-to-tree cross-check. The CLI gate still failed to complete because of lock contention. |

## manualQa

### surfaceEvidence

| scenario id | criterion reference | surface | exact invocation | verdict | artifactRefs |
|---|---|---|---|---|---|
| CLI-VERIFY-RETRY | Required verify must exit 0 and report migrated layout/receipts valid | Terminal CLI | `source ~/cd_vlaplan && python -m scripts.phase3.organize_outputs verify --repo-root .` | FAIL: process blocked at `fcntl.flock` in `exclusive_output_layout_lock`; interrupted exit `130`; no success output or exit `0` observed | A1, A7 |
| ROOT-THREE-ROOTS | Outputs has exactly three top-level roots and no stale flat lookup | Terminal CLI | `source ~/cd_vlaplan && find outputs -mindepth 1 -maxdepth 1 -printf '%f\\n' | sort` plus explicit `test -e`/`test -L` checks for `outputs/datasets` and the three former flat roots | PASS | A2, A4 |
| RELOCATIONS-15 | Fifteen source roots are absent and destinations are real non-symlink directories | Terminal CLI | `source ~/cd_vlaplan && python - <<'PY' ... prepared.json relocation postcondition checks ... PY` | PASS | A2 |
| VLM-COPY-INTEGRITY-9 | Nine physical VLM copies match canonical sources and receipt metadata | Terminal CLI | `source ~/cd_vlaplan && python - <<'PY' ... SHA-256, bytes, JSONL lines, and parsed JSON records for every source/destination pair ... PY` | PASS: `VLM_SOURCE_DESTINATION_INTEGRITY= PASS` | A3, A5, A6 |
| JOURNAL-CROSSCHECK | Journal state and records agree with the current tree | Terminal CLI | `source ~/cd_vlaplan && python - <<'PY' ... prepared/move/records/complete cross-check ... PY` | PASS: `JOURNAL_CROSS_CHECK= PASS` | A2, A3, A4 |
| SIDECAR-QUARANTINE | Failed receipt sidecars are preserved, mode 0600, old paths absent, and hashes match recovery receipt | Terminal CLI | `source ~/cd_vlaplan && python - <<'PY' ... sidecar presence/mode/old-path/hash checks ... PY` | PASS: `SIDECAR_QUARANTINE= PASS` | A7 |
| DIRTY-WORKTREE | Audit preserves pre-existing user changes | Terminal CLI | `source ~/cd_vlaplan && git status --short` before and after the audit; no product/source edits were issued | PASS: worktree remained intentionally dirty; only the mandated QA evidence file was created | A1 |

### adversarialCases

| scenario id | criterion reference | adversarial class | expected behavior | verdict | artifactRefs |
|---|---|---|---|---|---|
| ADV-STALE-STATE | ULTRAQA stale-state probe | stale state / repeat verification | A repeat of the exact verifier must exit 0 and validate the current tree | FAIL: repeat remained blocked on the shared organizer lock and was interrupted with exit 130 | A1, A7 |
| ADV-VLM-DATA | ULTRAQA independent artifact check | corrupt or missing immutable VLM copy | Hash, length, line count, and parsed records must match for all 9 copies | PASS | A3, A5, A6 |
| ADV-MISLEADING-SUCCESS | ULTRAQA misleading-success-output | receipt success must agree with independently observed artifacts | `complete.json` and move/record journals must agree with current paths and hashes | PASS | A2, A3, A4 |
| ADV-DIRTY-WORKTREE | ULTRAQA dirty-worktree check | pre-existing dirty state | Audit must not rewrite or revert user changes | PASS | A1 |
| ADV-PROMPT-INJECTION | Scope exclusion | prompt injection | Not applicable: no prompt/content processing surface is exercised by this filesystem CLI audit | NOT_APPLICABLE | A1 |
| ADV-HTTP-BROWSER | Scope exclusion | HTTP/browser UI | Not applicable: the audited surface is terminal CLI only | NOT_APPLICABLE | A1 |
| ADV-CANCEL-RESUME | Scope exclusion | cancellation/resume | Not applicable: no apply/resume operation was invoked; only read-only verify was attempted | NOT_APPLICABLE | A1 |
| ADV-NETWORK | Scope exclusion | network operation | Not applicable: all checks read the local repository and outputs tree | NOT_APPLICABLE | A1 |

### artifactRefs

| id | kind | description | path |
|---|---|---|---|
| A1 | qa-report | This report containing exact invocations, observed results, and the interrupted verifier traceback | `.omo/evidence/output-layout/outputs-vlm-dataset-layout-manual-qa.md` |
| A2 | receipt | Prepared migration journal with 15 relocation entries and snapshots | `outputs/deprecated/receipts/output-reorganization-20260727/prepared.json` |
| A3 | receipt | VLM source-to-destination record manifest with 9 expected hashes, sizes, and line counts | `outputs/deprecated/receipts/output-reorganization-20260727/records.json` |
| A4 | receipt | Migration completion marker observed as `state=complete` | `outputs/deprecated/receipts/output-reorganization-20260727/complete.json` |
| A5 | data | Canonical pilot JSONL source tree used by the VLM copy comparison | `outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725` |
| A6 | data | Physical VLM record destination tree; all 9 files were hashed and parsed | `outputs/reasoning_traces/vlm_records/stratified_pilot_20260725` |
| A7 | receipt | Failed-sidecar quarantine receipt with recorded swap and transaction hashes | `outputs/deprecated/receipts/failed-output-reorganization-20260726/recovery.json` |

Cleanup: none created. The temporary QA tmux session was removed; no product data, source, ports, or temporary roots were created or changed.
