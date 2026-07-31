# CGAS Single-Writer Owner Review

- One command-wide descriptor `flock` serializes every mutating lifecycle command for one work root. Concurrent blocking callers wait; `--no-wait` exits 75 as `work_locked` before verifier, characterizer, or progress effects.
- Production uses `fresh --shard-count 1`, blocking `resume --shard-count 1`, finalization, and final verification. Concurrent shard publication and dynamic foreign admission are unsupported.
- Checkpoints are anonymous mode-0600 `O_TMPFILE` inodes published exactly once via proc-fd `linkat`, then destination-directory fsynced. No named staging or temporary link-count-two state exists.
- The cooperative advisory lock coordinates participating processes but does not authorize hostile writers; pinned run-contract and no-follow protections remain integrity boundaries.

## Verification

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_characterization_runner.py tests/phase3/test_cgas_characterization_runner_resume.py tests/phase3/test_cgas_characterization_runner_checkpoint_fds.py
```

Repository-local GPFS synthetic two-process shard QA completed 12 checkpoints with both shard exit statuses zero. The private root needed `chmod g-s` because the repository GPFS parent applies setgid, while the checkpoint publication contract requires exact mode `0700`.
