# Filesystem publication workflow review criteria (POSIX/Linux, Python)

Research snapshot: 2026-07-27.

- Atomic visibility is distinct from crash durability: POSIX rename keeps the destination name continuously bound to either old or new entry; Linux `rename(2)` describes atomic replacement. `os.replace()` maps to this on POSIX.
- For durable publication, flush Python buffering, `fsync()` the completed file, perform rename/replace, then `fsync()` the containing directory. Linux man-pages explicitly say file fsync does not ensure the directory entry is durable; POSIX Issue 8 notes directory fsync synchronizes entries and attributes.
- `close()` is not a durability primitive. Check close errors for delayed I/O diagnostics; on Linux do not retry close after failure/EINTR because the descriptor may already be released/reused. Python treats close as a special EINTR case and does not retry.
- Create temporary files atomically (`mkstemp`/O_EXCL), in the destination directory/filesystem; avoid check-then-create names. `renameat`/dirfds reduce path-component races.
- Review interruption paths: signals, exceptions, SIGKILL/power-loss assumptions, leftover temp names, and whether rerun can safely discover/replace/clean up. Python docs say SIGKILL cannot automatically delete NamedTemporaryFiles on POSIX.
- Idempotence is a workflow invariant, not promised by rename: second run should converge to the same valid published state, not fail on stale temp files or accidentally treat an existing target as success unless policy says so.
- Tests should assert observable namespace/content/cleanup invariants, exercise collisions and concurrency, inject failures around flush/fsync/rename/cleanup, and use subprocess interruption. Passing tests do not prove power-loss durability: POSIX says key fsync aspects are unreasonable for ordinary test suites and formal tests may require forced crash/power shutdown.
