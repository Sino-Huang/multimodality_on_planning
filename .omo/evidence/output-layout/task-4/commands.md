# Task 4 Synthetic Command Evidence

All Task 4 organizer and hardening validation used synthetic pytest repositories or temporary synthetic CLI repositories. No command inspected, moved, rewrote, or verified a real output tree. No production migration occurred.

## Latest Todo 4 hardening validation

The required `ada_vla` environment command ran the eight focused organizer, catalog, inventory, and writer paths:

```bash
source ~/cd_vlaplan && PYTHONPATH="$PWD/tests/phase3" python -m pytest -q \
  tests/phase3/organize_outputs_support.py \
  tests/phase3/test_organize_outputs.py \
  tests/phase3/test_organize_outputs_semantics.py \
  tests/phase3/test_organize_outputs_adversarial.py \
  tests/phase3/test_organize_outputs_catalog.py \
  tests/phase3/test_organize_outputs_inventory.py \
  tests/phase3/test_organize_outputs_hardening.py \
  tests/phase3/test_output_layout_writer_detection.py
```

Final remediated result: `81 passed in 13.29s`.

Latest static validation results:

- Basedpyright: `0 errors, 0 warnings, 0 notes`.
- Compileall: exit 0.
- No-excuse checker: `no violations in 11 file(s)`.

Manual synthetic CLI QA produced successful JSON envelopes for apply and external-receipt verification:

```json
{"command": "apply", "ok": true}
{"command": "verify", "ok": true}
```

The same synthetic QA asserted all of the following:

- `catalog` without `--output` wrote exactly the serialized catalog to stdout and wrote nothing to stderr.
- `catalog --output` published the exact catalog bytes as a regular file with mode `0600`, without stdout or stderr output.
- `verify --receipt <external-receipt>` accepted a complete external receipt with mode `0600`, emitted the successful verify envelope, and did not rewrite the receipt.
- The final synthetic fake-`/proc` probe used `python -- scripts/phase3/generate_planimation_vlm.py` with a PID-relative output target; it was recognized as the direct Planimation script, resolved against that process's `cwd`, and detected as overlapping the relocation source without module reinterpretation.

Final Oracle remediation review reported no blocking findings after proof of catalog temporary-substitution prevention, final inventory validation for a fresh prepared receipt, and Python `--` direct-script recognition without module reinterpretation.

Writer-lock integration test collection was attempted separately in the required environment:

```bash
source ~/cd_vlaplan && PYTHONPATH="$PWD/tests/phase3" python -m pytest -q tests/phase3/test_phase3_writer_output_layout_lock.py
```

Collection could not complete because required `ada_vla` uses Python 3.10, while the pre-existing support modules import `typing.assert_never`, which is a Python 3.11 or newer standard-library symbol. No lock implementation, lock test, product writer, or support file was changed to bypass this environment-only limitation.

## Earlier Task 4 evidence, not rerun by the latest hardening pass

The earlier focused organizer run was:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_organize_outputs.py tests/phase3/test_organize_outputs_semantics.py tests/phase3/test_organize_outputs_adversarial.py
```

Historical result: `27 passed in 8.35s`.

The earlier accepted synthetic regression run was:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_contracts.py tests/phase3/test_output_layout_inventory.py tests/phase3/test_output_layout_lock.py tests/phase3/test_output_layout_view.py -k 'not real_repository'
```

Historical result: `72 passed, 1 deselected in 8.26s`.

The earlier static results were Basedpyright `0 errors, 0 warnings, 0 notes`, compileall exit 0, no-excuse `no violations in 9 file(s)`, and `git diff --check` exit 0. These figures remain historical evidence and are not presented as part of the latest rerun.

Earlier manual CLI QA used `/tmp/organize-outputs-manual.ZnEPAf/synthetic-repository`. Apply emitted `{"command": "apply", "ok": true}`, verify emitted `{"command": "verify", "ok": true}`, and the asserted receipt state was `complete` with 12 relocations and 15 links.
