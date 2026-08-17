# Phase 3 CGAS Characterization Verifier

## Scope

Added one strictly read-only verifier for characterization checkpoint and final roots. It does not assemble, publish, repair, delete, lock, or create production artifacts.

## Contract

- A checkpoint root has exactly `run-contract.json` and `checkpoints/`. It accepts a current root with zero checkpoints as valid but incomplete.
- A final root has exactly `run-contract.json`, `characterization.jsonl`, and `characterization_manifest.json`; it requires 481 canonical ordered rows, current source/PDDL/implementation contract bytes, literal `owner_approved=false`, and successful replay of every persisted BFS/IW plan using the current PDDL parser and grounding implementation.
- Final manifest values are recomputed from JSONL and current implementation files. Planner policy, replay evidence, trace eligibility, schema, partition absence, source identities, and all counts/identities must agree exactly.
- Final roots intentionally have no checkpoint directory. The verifier derives every expected row from the current run contract and unchanged `_characterize()` kernel, then requires exact canonical JSONL row bytes. Checkpoint verification separately recomputes canonical row identity before accepting an envelope identity.
- Planner validation does not reject authoritative resource-limited or failure rows merely because they do not reach a goal. It rejects any non-exact record with a plan or replay-success claim, while exact-solution records must satisfy replay and trace eligibility requirements.
- All verification roots are descriptor-opened only after current-user mode-`0700` checks. Contract, final, and checkpoint leaves require mode `0600`, current ownership, and a single hardlink. Checkpoint parser/linkage errors are terminal invalid reports rather than uncaught exceptions.
- Every inspected entry uses descriptor-relative no-follow reads. Symlinks, FIFO/socket/device entries, directories where leaves are required, extra names, noncanonical JSON bytes, stale contracts, malformed checkpoint names, and invalid manifest fields fail closed.
- The run contract merges the discoverable verifier module into caller-provided roots when it exists, coupling verifier byte drift to checkpoint validity.

## Commands

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 pytest -q tests/phase3/test_cgas_characterization_verifier.py tests/phase3/test_cgas_characterization_contract.py tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_checkpoint_publication.py tests/phase3/test_cgas_characterization_types.py tests/phase3/test_cgas_serialization.py tests/phase3/test_cgas_partition_characterization.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_verifier.py scripts/phase3/cgas_characterization_contract.py tests/phase3/test_cgas_characterization_verifier.py
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m compileall -q scripts/phase3/cgas_characterization_verifier.py scripts/phase3/cgas_characterization_contract.py
```
