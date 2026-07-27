# Stale Live Output Roots Fix Evidence

## Failing-first coverage

Scenario: stale curriculum generator default, writer-registry default, missing Visitall and 15-puzzle launcher roots, and absent launcher argument guard.

Invocation:
`source ~/cd_vlaplan && pytest -q tests/phase3/test_output_layout_writer_detection.py tests/phase3/test_planimation_compatibility_references.py -k 'writer_registry_uses_writer_parser_defaults or strict_shell_trace_roots or temprun_argument_guard'`

Observable: four focused assertions failed against the stale consumers; the direct generator-default assertion also failed against `outputs/phase3_curriculum_traces`.

Captured artifacts:
`.omo/evidence/stale-live-output-roots-red.txt`

## Focused regression suite

Scenario: structured default and all launcher trace locations are required, and help/unknown arguments terminate before the workflow.

Invocation:
`source ~/cd_vlaplan && pytest -q tests/phase3/test_output_layout_writer_detection.py tests/phase3/test_planimation_compatibility_references.py`

Observable: `22 passed in 0.24s`.

Captured artifact:
`.omo/evidence/stale-live-output-roots-focused-pytest.txt`

## Shell and manual QA

Scenario: launcher syntax is valid.

Invocation:
`source ~/cd_vlaplan && bash -n temprun.sh`

Observable: exit 0 with `PASS bash -n temprun.sh`.

Captured artifact:
`.omo/evidence/stale-live-output-roots-bash-n.txt`

Scenario: required non-rendering help path.

Invocation:
`source ~/cd_vlaplan && bash temprun.sh --help`

Observable: exit 0 and only `Usage: temprun.sh`; it returns before source activation, generation, rendering, or sleep commands.

Captured artifact:
`.omo/evidence/stale-live-output-roots-manual-help.txt`

Scenario: malformed launcher input.

Invocation:
`source ~/cd_vlaplan && bash temprun.sh --unknown`

Observable: `Usage: temprun.sh` and exit 2.

Captured artifact:
`.omo/evidence/stale-live-output-roots-unknown-argument.txt`

## Resolved paths

Scenario: all active curriculum locations resolve and no named active consumer retains a stale flat or nonexistent reasoning root.

Invocation:
`source ~/cd_vlaplan && for path in outputs/reasoning_traces/curriculum outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_visitall_strict_v1_1st_round outputs/deprecated/phase3/curriculum_traces/phase3_curriculum_traces_15puzzle_easy_strict_v1_1st_round; do test -d "$path" && printf 'RESOLVED %s\\n' "$path"; done && ! rg -n 'outputs/phase3_curriculum_traces|outputs/reasoning_traces/curriculum/phase3_curriculum_traces_(visitall_strict_v1_1st_round|15puzzle_easy_strict_v1_1st_round)' scripts/phase3/generate_curriculum_trace_dataset.py scripts/phase3/output_layout_writer_registry.py temprun.sh`

Observable: all four directories printed as `RESOLVED`; the stale-reference search was empty and reported `NO_ACTIVE_STALE_ROOTS`.

Captured artifact:
`.omo/evidence/stale-live-output-roots-resolved-paths.txt`

## Final worktree check

Scenario: scoped patch and evidence artifacts are ready for handoff.

Invocation:
`source ~/cd_vlaplan && git diff --check -- scripts/phase3/generate_curriculum_trace_dataset.py temprun.sh tests/phase3/test_output_layout_writer_detection.py`

Observable: `PASS scoped git diff --check`; all listed evidence artifacts are non-empty.

Captured artifact:
`.omo/evidence/stale-live-output-roots-worktree-check.txt`
