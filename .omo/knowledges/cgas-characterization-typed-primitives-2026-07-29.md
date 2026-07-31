# CGAS Characterization Typed Primitives

Date: 2026-07-29

- `scripts.phase3.cgas_characterization_types` owns distinct `NewType` brands for canonical row indices, source-manifest digests, and characterization-artifact digests. Frozen run/report dataclasses and the `Characterizer` protocol keep later checkpoint consumers from accepting plain strings interchangeably.
- `scripts.phase3.cgas_serialization.canonical()` remains the legacy general serializer for existing provenance consumers. New `canonical_json_object()` and `canonical_json_line()` are strict, UTF-8 byte boundaries: recursively sorted compact object JSON only, with stable typed rejection for floats (including non-finite values), arrays, bytes, and non-object roots.
- `tests/phase3/cgas_characterization_support.py` is explicitly test-only synthetic data. It generates no PDDL, reads no corpus, and has the exact required population shape: 481 rows, splits train/dev/test 402/39/40, object counts 4/8/12 190/198/93.

## Verification

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_serialization.py tests/phase3/test_cgas_characterization_types.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_provenance.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_types.py scripts/phase3/cgas_serialization.py tests/phase3/cgas_characterization_support.py tests/phase3/test_cgas_characterization_types.py tests/phase3/test_cgas_serialization.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_characterization_types.py scripts/phase3/cgas_serialization.py tests/phase3/cgas_characterization_support.py tests/phase3/test_cgas_characterization_types.py tests/phase3/test_cgas_serialization.py
```
