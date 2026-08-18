# Phase 3 CGAS Single-Writer Owner Review

## Contract

The supported path has one owner writer. A command-wide descriptor `flock` serializes `fresh`, `shard`, `resume`, and `finalize` per work root. Dynamic foreign-shard admission, the per-leaf pinned FD ledger, mutable shard reconciliation, and simultaneous shard publication are removed from the production contract.

Checkpoint publication uses an anonymous mode-0600 `O_TMPFILE` inode created in the external private directory. It is written, fsynced, descriptor-verified at link count zero, then installed once by proc-fd `linkat` into the pinned checkpoint directory and followed by destination-directory fsync. There is no named staging leaf, rename, unlink, or link-count-two state. Progress is emitted only after this durable single-link transition.

## Verification

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_characterization_checkpoint_publication.py tests/phase3/test_cgas_characterization_checkpoint_linkat.py tests/phase3/test_cgas_characterization_runner.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_command_lock.py scripts/phase3/cgas_characterization_checkpoint_publication.py scripts/phase3/cgas_characterization_runner.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_characterization_command_lock.py scripts/phase3/cgas_characterization_checkpoint_publication.py scripts/phase3/cgas_characterization_runner.py
```

Historical multi-shard evidence is synthetic-only and does not establish support for the owner-review contract. The production campaign is `fresh --shard-count 1`, blocking `resume --shard-count 1`, work verify, finalize, and final verify; expected duration is 8-10 minutes.
