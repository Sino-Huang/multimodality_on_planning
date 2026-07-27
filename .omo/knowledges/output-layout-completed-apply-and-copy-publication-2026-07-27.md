# Output-layout completed apply and copy publication

- A repository `flock` is not reentrant across separately opened descriptors. Code already holding `exclusive_output_layout_lock()` must call a lock-free internal verifier, never the public lock-owning `verify()` entry point.
- Completed `apply` is an idempotent resume surface, not the explicit deep-audit surface. It should validate the immutable completion journal, topology, physical-record hashes, and exact root inventory; explicit `verify` retains recursive tree hashing.
- Publishing a private temporary copy with ordinary `os.rename()` is unsafe because a competing destination can be replaced after an absence check. A same-directory descriptor-relative `os.link()` publishes atomically with no replacement; `EEXIST` is the collision result, after which the temporary inode is removed.
- Real completed-layout QA must be bounded and paired with pre/post output and receipt fingerprints because success JSON alone does not prove idempotence.
