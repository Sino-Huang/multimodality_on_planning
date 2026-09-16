# Successor interaction dataset: release-001

Goal 8 collected all 512 frozen successor queries in each of text, visual and
multimodal form: 1,536 interactions from the same 25 BFS training tasks. The
membership, observations, output allowance and starting adapters remain those
qualified in Goal 7. Selection did not depend on these model outcomes.

The versioned local release is
`outputs/expanded-study/v1/successor/dataset/release-001/report.json`.
[successor-data.json](successor-data.json) publishes its exact artifact paths,
hashes, cell membership and compute evidence. Output artifacts follow this
repository's existing local corpus-release convention; they are not Git assets.

Each modality has separate `interactions.json.gz` and `labels.json.gz` files.
Interactions preserve the returned prediction text, strict parse/verifier result,
complete trusted target, exact source state, full producing-action path, original
decision/trace links, Search Memory, view binding and model/runtime identity.
Labels contain the authoritative input and complete teacher target, with no raw
prediction or prediction verdict. All 1,536 labels independently pass strict
authority validation. Gzip payloads regenerate byte-identically; a conflicting
existing release file is rejected rather than overwritten.

| Starting-adapter modality | Exact successor | Schema failure | State-identity failure | Effect failure |
| --- | ---: | ---: | ---: | ---: |
| Text | 43 | 404 | 34 | 31 |
| Visual | 52 | 412 | 23 | 25 |
| Multimodal | 24 | 458 | 18 | 12 |
| Total | 119 | 1,274 | 75 | 68 |

These are fixed-query results from the original process-SFT adapters under the
new successor contract. The 1,417 rejected predictions remain outcomes; no state
was applied or silently repaired, and no trusted state replaced a prediction.
Operational failures remain in scheduler attempt records. Downstream search is
explicitly `not_evaluated`: Goal 9 owns successor training and final search
comparisons. These counts do not establish downstream planning performance.

Collection uses the fixed retained decision inputs required by #86, with one
prediction per record in batches of two. It does not collect an on-policy search
trajectory: the training source/action membership and last-valid Search Memory
are replayed from the retained incremental BFS traces. Source paths link each
noninitial scene to its producing actions; rejected outputs cannot advance them.
Accepted-delta history remains bounded to 16. Live execution and future training
materialization share `expanded_successor_protocol.training_example`.

[successor-data-provenance.json](successor-data-provenance.json) publishes all 25
task-level exact-reference decision/expansion costs, source trace paths/hashes,
PDDL hashes and the source report identity. These supplement the immutable
release's trace links. The independent audit compares complete canonical task
contexts against the source corpus's held-out partitions and both current final
panels, preserving the original source semantic-split contract. It does not claim
a new corpus-wide object-renaming split proof.

Both first GPU attempts failed after their first returned batch because the view
binding retained the source prompt's token count after successor projection.
Commit `beee360` binds the projected prompt to the already-frozen measurement.
All four first-attempt outputs were recovered through the retained journals,
without another model call. A subsequent CPU chain attempt referenced retry
configs at the wrong path; it admitted no GPU job. Its terminal evidence is also
retained. Scientific membership and decoding did not change during recovery.

Successful workers used ports 18800 and 18801 and consumed 9.225523 GPU-hours.
Including the failed collection attempts, Goal 8 consumed 9.294947 GPU-hours;
the successor branch's cumulative spend including Goal 7 is 9.515907 / 64,
leaving 54.484093 GPU-hours. Chain completion was recorded at
2026-09-16 12:21:23 UTC (22:21:23 Australia/Melbourne), about 6 hours 23 minutes
after the successful retry chain started. No persistent training update ran.

Verification:

```bash
source ~/cd_vlaplan
EXPANDED_TERMINAL_PATH=outputs/expanded-study/v1/jobs/successor-collection-final/1/terminal.json \
  python scripts/run_expanded_successor_collection.py audit-final
python scripts/audit_expanded_successor_data.py
```

The scheduled worker/final replay hooks and standalone release replay pass.
[successor-data-independent-audit.json](successor-data-independent-audit.json)
records the separate teacher/split/reference-cost/provenance audit. The affected
test suite passed 77 tests; Ruff passes. Goal 9 consumes the verified release's
teacher labels and preserves these original prediction outcomes separately.
