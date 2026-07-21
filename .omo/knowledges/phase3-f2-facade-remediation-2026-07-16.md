# Phase 3 F2 Facade Remediation

- Legacy import paths now expose compact compatibility facades for Phase 1, curriculum rendering, and Phase 3 pairing.
- The public renderer, provider, manifest, render, record, schema, verifier, and private provenance hooks remain importable from their prior paths.
- The pairing validation facade forwards the legacy monkeypatchable JSONL snapshot seams into the implementation before validation.
- Verification: 90 focused tests passed; basedpyright reported zero findings; compileall and `verify_planimation_vlm.py --mode release` succeeded for the fixture surface.
