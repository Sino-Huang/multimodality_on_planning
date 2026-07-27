# DoneClaim: output-layout final review repair

Result: DONE

## Changed files

- `scripts/phase3/organize_outputs.py`
- `scripts/phase3/organize_outputs_preflight.py`
- `tests/phase3/test_organize_outputs.py`
- `tests/phase3/test_organize_outputs_adversarial.py`
- `tests/phase3/test_output_layout_rename.py`
- `.omo/knowledges/output-layout-completed-apply-and-copy-publication-2026-07-27.md`

## Exact results

| Criterion | Scenario and invocation | Binary observable | Captured artifact |
|---|---|---|---|
| Pre-edit characterization | `source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/phase3/test_organize_outputs.py::test_apply_and_verify_create_exact_three_category_layout` | Exit 0; `1 passed in 0.18s` | `01-baseline-completed-layout-characterization.txt` |
| Failing-first completed apply | Run the bounded completed second-apply regression before the fix | `subprocess.TimeoutExpired` after 2 seconds | `03-red-lock-and-copy-regressions.txt` |
| Failing-first publication collision | Claim destination immediately before old `os.rename()` publication | `Failed: DID NOT RAISE OrganizerError`; racer was overwritten | `03-red-lock-and-copy-regressions.txt` |
| Green focused regressions | Run the completed-apply and competing-publication tests after the fix | Exit 0; `2 passed in 0.48s` | `04-green-lock-and-copy-regressions.txt` |
| Organizer collection | Collect the two focused organizer modules | Exit 0; `11 tests collected in 0.08s` | `05-green-organizer-collection.txt` |
| Focused output-layout tests | `source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/phase3/test_organize_outputs.py tests/phase3/test_organize_outputs_adversarial.py tests/phase3/test_output_layout_rename.py` | Exit 0; `21 passed in 1.91s` | `14-final-focused-review-modules.txt` |
| Manual completed apply | `source ~/cd_vlaplan && timeout 30s python -m scripts.phase3.organize_outputs apply --repo-root .` | Exit 0; `{"command": "apply", "ok": true}` | `15-manual-completed-apply-pass.txt` |
| Manual no-mutation audit | Compare all output entry path/type/inode/mode/size/mtime and all migration-receipt SHA-256 values before/after apply | Tree fingerprint `ad17393a...dfcf` unchanged; receipt fingerprint `bb5266d...1057` unchanged | `12a-manual-pre-state.txt`, `16-manual-post-state.txt`, `17-manual-mutation-audit-pass.txt` |
| Compile | `source ~/cd_vlaplan && python -m compileall -q scripts/phase3 tests/phase3` | Exit 0; no diagnostics | `18-final-compileall.txt` |
| Whitespace | `source ~/cd_vlaplan && git diff --check` | Exit 0; no diagnostics | `19-final-git-diff-check.txt` |
| Cleanup | Scan for organizer, focused pytest, output fingerprint, and wait processes | `matching_processes=0` | `20-process-cleanup.txt` |
| Synthetic fixture cleanup | Remove the two validated pytest roots created by this repair | Both paths absent; `synthetic_pytest_roots_removed=true` | `22-synthetic-root-cleanup.txt` |

The publication regression asserts the competing destination bytes remain `{"competitor":true}\n`, the canonical source SHA-256 is unchanged, and no temporary copy remains. Existing malformed journal-name and destination-collision tests are retained in the passing focused run.
