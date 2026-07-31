# CGAS F2 Remediation: Import Boundary and Static Typing

Date: 2026-07-31

F2 basedpyright must be run with:

```bash
source ~/cd_vlaplan && PYTHONNOUSERSITE=1 basedpyright scripts/phase3/local_iw.py scripts/phase3/local_planner_types.py scripts/phase3/local_serial.py scripts/phase3/pipeline.py scripts/phase3/schema.py scripts/phase3/cgas_alignment.py scripts/phase3/cgas_bfs.py scripts/phase3/cgas_certificate_contracts.py scripts/phase3/cgas_certificate_publication.py scripts/phase3/cgas_certificates.py scripts/phase3/cgas_provenance.py scripts/phase3/cgas_qwenvl.py scripts/phase3/cgas_qwenvl_contracts.py scripts/phase3/cgas_qwenvl_preflight.py scripts/phase3/cgas_qwenvl_publication.py scripts/phase3/cgas_release_gate.py scripts/phase3/cgas_serialization.py
```

Remediation points:

- `pyrightconfig.json` is Pyright config only. Do not leave VS Code web/remote settings such as `remote.downloadExtensionsLocally` or `workbench.web.useServiceWorkers` in it.
- `pipeline.py` reads JSON rows through `read_jsonl()`, so values like `frame_paths` must be narrowed before iteration.
- `LocalPlannerRequest.planner` requires the `PlannerName` literal union. Use a typed lookup for local planners instead of passing an arbitrary `str`.
- `stable_hash()` accepts `JSONValue`; build a typed `list[JSONValue]` for plan hashes instead of relying on `list[str]` invariance.
- `_loader_module()` may use fake transformers modules only for the known transformers/huggingface-hub import boundary. Internal loader `ImportError`s, even if their message mentions `huggingface-hub`, must propagate without retry.

Regression coverage lives in `tests/phase3/test_cgas_qwenvl_preflight.py::test_loader_module_preserves_internal_import_error_when_message_mentions_huggingface_hub`.
