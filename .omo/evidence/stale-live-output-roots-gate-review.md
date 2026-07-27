# Stale Live Output Roots Gate Review

## Decision

- recommendation: APPROVE
- verificationResult: confirmed
- blockers: []

## Original Intent

Repair the active curriculum-trace output consumers so new/current traces use the structured outputs layout, retained Visitall and 15-puzzle traces use their existing deprecated structured locations, and `temprun.sh` can expose help or reject malformed arguments without starting the workflow or touching an absent flat root.

## Desired Outcome

- Generator and writer-registry defaults agree on `outputs/reasoning_traces/curriculum`.
- Every active `temprun.sh` trace root points to an existing structured location.
- No scoped active consumer retains the forbidden flat root or nonexistent Visitall/15-puzzle reasoning roots.
- Focused tests and shell syntax pass.
- Help exits 0 promptly and unknown input exits nonzero before workflow execution.
- Verification creates no outputs, processes, ports, sessions, or temporary roots and does not alter the dirty worktree.

## User Outcome Review

The shipped artifact satisfies the requested user-visible outcome. The generator and registry independently resolve the same existing structured default. The launcher help path prints only its usage and exits 0 within the five-second bound. The unknown-argument path prints usage and exits 2. Every configured trace directory exists, and a scoped forbidden-root scan is empty.

## Independent Evidence

1. Focused suite

   Command: `source ~/cd_vlaplan && pytest -q tests/phase3/test_output_layout_writer_detection.py tests/phase3/test_planimation_compatibility_references.py`

   Result: exit 0; 22 progress marks completed. The executor artifact independently reports `22 passed in 0.24s`.

2. Shell syntax

   Command: `source ~/cd_vlaplan && bash -n temprun.sh && printf 'BASH_N_EXIT=0\n'`

   Result: `BASH_N_EXIT=0`.

3. Manual-QA help channel, bounded

   Command: `source ~/cd_vlaplan && timeout 5s bash temprun.sh --help; rc=$?; printf 'HELP_EXIT=%s\n' "$rc"; test "$rc" -eq 0`

   Result: `Usage: temprun.sh` and `HELP_EXIT=0`; no generation, rendering, sleep, or absent-root diagnostic appeared.

4. Malformed input

   Command: `source ~/cd_vlaplan && set +e; output=$(timeout 5s bash temprun.sh --unknown 2>&1); rc=$?; set -e; printf '%s\nUNKNOWN_EXIT=%s\n' "$output" "$rc"; test "$rc" -ne 0`

   Result: `Usage: temprun.sh` and `UNKNOWN_EXIT=2`.

5. Stale-state and misleading-success checks

   Command: `source ~/cd_vlaplan && for path in outputs/reasoning_traces/curriculum outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_visitall_strict_v1_1st_round outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_15puzzle_easy_strict_v1_1st_round; do test -d "$path" || exit 1; printf 'EXISTS %s\n' "$path"; done`

   Result: all four paths printed with `EXISTS`.

6. Default agreement and forbidden roots

   Command: scoped `rg` for `outputs/phase3_curriculum_traces` and the forbidden Visitall/15-puzzle reasoning-root forms, followed by Python assertions over `DEFAULT_OUTPUT_ROOT`, `writer_targets(...)`, and `DEFAULT_OUTPUT_ROOT.is_dir()`.

   Result: `NO_ACTIVE_FORBIDDEN_FLAT_ROOT`, `GENERATOR_DEFAULT=outputs/reasoning_traces/curriculum`, and `REGISTRY_DEFAULT=outputs/reasoning_traces/curriculum`.

7. Dirty-worktree preservation

   Before/after SHA-256 values for the five reviewed source/test files remained unchanged during verification. No command created an output, long-lived process, port, tmux session, or temporary root. This report is the only gate artifact written as required by the reviewer contract.

## Direct Slop and Programming Pass

- Production diff is minimal: one generator constant, one registry default, launcher path substitutions, and an early CLI argument guard. No unnecessary production extraction, parsing, normalization, new dependency, broad exception, dead helper, or speculative abstraction was introduced by this repair.
- The failing-first evidence proves the tests distinguish stale defaults and missing launcher guards.
- `test_curriculum_generator_default_uses_structured_reasoning_root` and `test_writer_registry_uses_writer_parser_defaults` pin machine-consumed defaults and are relevant.
- `test_temprun_argument_guard_does_not_start_the_render_workflow` drives the real shell surface with a timeout and distinct expected exit codes; it is not tautological.
- `test_strict_shell_trace_roots_use_canonical_reasoning_locations` parses exact shell assignments and therefore mirrors implementation structure. This is a maintenance/false-confidence NOTE, not a blocker: the stated criteria are independently proven by direct path existence, runtime help/error behavior, default assertions, and the forbidden-root scan.
- No deletion-only test, requested-removal-only test, tautological expected value, output-derived expectation, or unnecessary production abstraction blocks the stated repair criteria.

## Report-Coverage Check

No repair-specific code-review report was referenced by `.omo/evidence/stale-live-output-roots-final.md`, and no `stale-live-output-roots-code-review.md` exists. `.omo/evidence/outputs-vlm-dataset-layout-code-review.md` explicitly records `remove-ai-slops`, `programming`, overfit/implementation-mirroring concerns, but it belongs to the broader output-layout work rather than this narrow repair. Exact gap: no separate report artifact documents a skill-perspective pass for these five scoped files. This is not a blocker because the requested success criteria do not require that artifact and this gate performed the direct pass.

## Checked Artifacts

- `.omo/evidence/stale-live-output-roots-final.md`
- `.omo/evidence/stale-live-output-roots-red.txt`
- `.omo/evidence/stale-live-output-roots-focused-pytest.txt`
- `.omo/evidence/stale-live-output-roots-bash-n.txt`
- `.omo/evidence/stale-live-output-roots-manual-help.txt`
- `.omo/evidence/stale-live-output-roots-unknown-argument.txt`
- `.omo/evidence/stale-live-output-roots-resolved-paths.txt`
- `.omo/evidence/stale-live-output-roots-worktree-check.txt`
- `.omo/evidence/outputs-vlm-dataset-layout-code-review.md`
- `.omo/knowledges/phase3-live-output-root-consumers.md`
- `scripts/phase3/generate_curriculum_trace_dataset.py`
- `scripts/phase3/output_layout_writer_registry.py`
- `temprun.sh`
- `tests/phase3/test_output_layout_writer_detection.py`
- `tests/phase3/test_planimation_compatibility_references.py`

## Evidence Gaps

- No repair-specific code-review report exists.
- The focused pytest rerun emitted progress marks and exit 0 in the current terminal capture; the exact `22 passed in 0.24s` summary is preserved in the checked executor artifact rather than repeated by this terminal renderer.
- Prompt injection, HTTP/browser UI, cancellation/resume, and network operations are not applicable to this shell/path repair.
