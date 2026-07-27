# Output-Layout Filesystem-Security Repair Lessons

- Metadata checks do not make later path opens safe. Reopen untrusted regular
  files with `O_NOFOLLOW | O_NONBLOCK`, then validate the opened descriptor.
- Every recursive filesystem operation needs both a depth limit and a
  per-directory-entry limit. Scan and fsync walkers must share the limits.
- Immutable construction state must retain ownership after each successful
  mutation. When construction fails, pass that partial ledger to cleanup and
  preserve the original exception.
- Quarantine is evidence, not a deletion authorization. Revalidate identity at
  the terminal removal seam; on mismatch, retain the quarantine name.
- A failed post-publish identity check must be a normalized operation failure.
  Never clean a final name that could belong to a racer.
- Recovery sidecars are trusted protocol state only at exact mode `0600`; mode
  enforcement belongs in the common sidecar read path so recovery and cleanup
  cannot bypass it.
