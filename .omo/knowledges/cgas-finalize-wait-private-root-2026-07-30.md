# CGAS Finalize-Wait Private Root Diagnosis

The isolated finalize-wait fixture must pass the nested fixture repository as
`--repository-root`; it must not pass `.` while its current working directory
is the fixture's outer workspace. With the latter combination, an absolute
private root below the nested repository resolves outside the state directory
derived from the outer workspace and correctly returns
`private_root_outside_state`.

For subprocess QA launched from the workspace, use the nested repository's
absolute root and the repository-relative private root
`tmp/.cgas-characterization/private-candidates`. The CLI normalizes that form
before all lifecycle modes, and the synthetic helper's state directory has no
symlink or canonical-path drift.

The completed real-subprocess gate used a fresh synthetic work root with 481
prewritten checkpoints. Resume held the command lock while finalize remained
blocked and no final leaf existed. Once resume returned its zero-work success
report, finalize published the bundle and final verification returned a valid,
complete, publishable report.
