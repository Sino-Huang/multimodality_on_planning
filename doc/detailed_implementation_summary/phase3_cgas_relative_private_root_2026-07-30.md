# Phase 3 CGAS relative private-root normalization

## Change

The characterization CLI now resolves `--private-root` relative to the
resolved repository root. This makes the documented command form work:

```bash
source ~/cd_vlaplan && python -m scripts.phase3.cgas_partition_characterization fresh \
  --repository-root . \
  --private-root tmp/.cgas-characterization/private
```

The normalizer preserves valid absolute paths and rejects traversal,
normalization drift, lexical escape from the repository, paths outside the
trusted state root, and any existing symlink component. Invalid CLI inputs use
the existing `private_root_not_directory` error contract.

## Tests

The state-directory suite includes a subprocess regression test that creates
an isolated repository below the workspace GPFS-backed `tmp` directory and
runs the documented relative command. It confirms private-root preflight
succeeds before the intentionally empty source manifest rejects contract
construction. It also covers traversal and NFC-drifting relative inputs.

Command used:

```bash
source ~/cd_vlaplan && pytest -q \
  tests/phase3/test_cgas_characterization_state_directory.py \
  tests/phase3/test_cgas_characterization_cli.py \
  tests/phase3/test_cgas_characterization_command_lock.py \
  tests/phase3/test_cgas_characterization_work.py \
  tests/phase3/test_cgas_characterization_runner.py \
  tests/phase3/test_cgas_characterization_runner_resume.py \
  tests/phase3/test_cgas_characterization_final_publication.py
```

Expected result: `85 passed`.

Static validation commands:

```bash
source ~/cd_vlaplan && basedpyright \
  scripts/phase3/cgas_characterization_cli.py \
  tests/phase3/test_cgas_characterization_state_directory.py \
  tests/phase3/test_cgas_characterization_cli.py \
  tests/phase3/test_cgas_characterization_command_lock.py
source ~/cd_vlaplan && python -m compileall -q \
  scripts/phase3/cgas_characterization_cli.py \
  tests/phase3/test_cgas_characterization_state_directory.py \
  tests/phase3/test_cgas_characterization_cli.py \
  tests/phase3/test_cgas_characterization_command_lock.py
git diff --check
```

Expected results: `0 errors, 0 warnings, 0 notes`, no compile output, and no
diff-check output.
