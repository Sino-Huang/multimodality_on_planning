# Phase 3 CGAS Persisted Alignment Acceptance Binding

## Change

Todo 4 now accepts alignment rows only after Todo 3's persisted-output verifier
confirms the manifest and source-derived row bindings. The verifier rejects a
missing or malformed manifest, incorrect manifest source/alignment digest or
counts, malformed schema, missing/duplicate/unknown source transitions,
action/state/split/status/index divergence, unreadable PNG paths, and PNG hash
divergence. `render_manifest_digest` remains required as a structural SHA-256
value because Todo 4 has no render-manifest input from which to recompute it.

Both `build_steps()` and `verify_steps()` invoke the gate before constructing
expected certificate records. Existing publication transactions and downstream
schema/certificate/counterfactual diagnostics are unchanged.

## Verification

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_certificates_alignment_binding.py tests/phase3/test_cgas_certificates_publication.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_alignment.py scripts/phase3/cgas_certificates.py tests/phase3/test_cgas_certificates_alignment_binding.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_alignment.py scripts/phase3/cgas_certificates.py tests/phase3/test_cgas_certificates_alignment_binding.py
git diff --check
```

The focused suite reports `55 passed`. Basedpyright reports zero errors,
warnings, and notes. A fresh CLI build and verification of the retained fixture
accept 12 rows with all counters zero. A copied alignment fixture with only a
tampered `alignment_digest` fails verify with zero accepted rows and
`alignment_manifest_mismatch`. Receipts are in
`.omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-7/`.
