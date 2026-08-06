# Production P0 trace-v2 persistence contract

## Frozen predecessor

The infrastructure fixture is archived byte-for-byte at `data/planning_cgas_fixture_v1`. Both roots bind the 34-file inventory digest `fb7012d6c340e7339b922f84e0db7d170af680132df37e7f810932850e27ff7a`, and both `release_manifest.json` files retain SHA-256 `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`. Trace-v1 modules and verifier fixtures were not edited.

## Trace-v2 encoding

`cgas_trace_contract_v2` changes persistence only. Each event is one UTF-8, uncompressed, sorted-key compact JSON line with a zero-based contiguous sequence, previous hash, current hash, and event payload. The current hash covers the same canonical record without `current_event_sha256`. The stream digest is incrementally updated from event lines, so writer memory is independent of event count.

One canonical trailer follows all events and binds record count, final event hash, event-stream SHA-256, contract digest, planner, completion status, and successful-plan digest. The writer validates expected cardinality, enforces planner bounds including the trailer, fsyncs complete bytes, verifies the temporary stream, and only then installs it without replacing a different output.

Policy SHA-256 is `559c3a7cc4fd4833726ca3a5dcbd09149b83915e0a77871e4d350c489bd76c1e`. Limits remain expansions 10,000, plan length 128, grounded actions/atoms 100,000, IW width/max width 1, IW novelty expansions 10,000, local applicable actions 2,000, and recovery disabled. Total stream bounds are BFS 1,000,010,002 records and IW 40,000,003 records.

## Approval boundary

The exact migration packet SHA-256 is `f7b93250c8302e30e8c9e15b163f2f1d3b69a57d2e7de4c58fe02e4ec67e289b`; its contract digest is `5649fc7b7b4955a8879c3d997342a3d74594c9faa7458e5dc177bf3e977a0b9d`. It and the owner template are immutable and unapproved.

The validator never creates owner identity or approval bytes. An external canonical owner artifact must independently bind exact persisted packet bytes, contract digest, policy digest, persistence-only scope, owner identity, and approval time. Until supplied, approval validation exits nonzero and creates no approved contract.

## Verification commands

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_fixture_archive.py tests/phase3/test_cgas_trace_contract_v2.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_fixture_archive.py scripts/phase3/cgas_trace_contract_v2.py scripts/phase3/cgas_trace_stream_v2.py scripts/phase3/cgas_trace_contract_approval.py scripts/phase3/cgas_trace_v2_json.py tests/phase3/test_cgas_fixture_archive.py tests/phase3/test_cgas_trace_contract_v2.py
source ~/cd_vlaplan && ruff check scripts/phase3/cgas_fixture_archive.py scripts/phase3/cgas_trace_contract_v2.py scripts/phase3/cgas_trace_stream_v2.py scripts/phase3/cgas_trace_contract_approval.py scripts/phase3/cgas_trace_v2_json.py tests/phase3/test_cgas_fixture_archive.py tests/phase3/test_cgas_trace_contract_v2.py
```

## Post-link durability remediation

`_install_stream` holds an exclusive advisory lock on the destination parent directory from collision inspection through no-replace hard-link installation, directory fsync, and any rollback. If directory fsync rejects a link created by that invocation, rollback unlinks it and fsyncs the directory again while the lock remains held. Link failure leaves `installed` false, so a competing or pre-existing immutable output is never removed. This avoids the race in checking destination inode identity and then unlinking by pathname.
