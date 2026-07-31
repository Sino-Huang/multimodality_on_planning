# CGAS Characterization Private Candidate Assembly

Date: 2026-07-29

- `assemble_characterization_candidate()` in `scripts.phase3.cgas_characterization_assembly` never creates or publishes a final root. It accepts a `VerificationRequest` plus an owner-controlled private root under `<repository>/tmp` and returns only a verifier-clean private candidate path.
- Assembly rejects work unless the read-only verifier reports a current valid checkpoint root with exactly 481 canonical leaves. The checkpoint envelopes are authentication bindings only; rows and manifest are recomputed from the current contract and kernel rather than copied from persisted state.
- Candidate roots are random private mode-0700 directories, strictly external to the checkpoint tree. They contain exactly `run-contract.json`, `characterization.jsonl`, and `characterization_manifest.json`; every leaf is mode 0600.
- Candidate I/O uses `O_EXCL|O_NOFOLLOW`, completes short writes, fsyncs each file, and fsyncs the candidate directory. Failed writes or final verification retain the private candidate and report its path through `CharacterizationAssemblyError`.
- The final verifier is invoked after candidate construction and must report `valid=true`, `complete=true`, and `publishable=true`. The recomputed manifest has literal `owner_approved=false` and binds artifact digest, source digests, implementation digests, counts, schema, and policy limits.

## Verification

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 pytest -q tests/phase3/test_cgas_characterization_assembly.py tests/phase3/test_cgas_characterization_verifier.py tests/phase3/test_cgas_characterization_contract.py tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_checkpoint_publication.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_serialization.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_assembly.py scripts/phase3/cgas_characterization_assembly_fs.py tests/phase3/cgas_characterization_assembly_support.py tests/phase3/test_cgas_characterization_assembly.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_characterization_assembly.py scripts/phase3/cgas_characterization_assembly_fs.py tests/phase3/cgas_characterization_assembly_support.py tests/phase3/test_cgas_characterization_assembly.py
```
