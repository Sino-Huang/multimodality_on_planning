# Handoff — 2026-08-12 CGAS Local Adapter Integration Ruff Failure

## Completed
- Implemented optional supplied-plan plumbing across client → RenderConfig → StateRenderer → CGAS adapter, default-inert for hosted/absent-plan behavior.
- Added a loopback-only 4-object integrated validation harness and hermetic regression tests.
- Exact local WIP commit: `2b2c6146b39d46344433ef929804b0019fe42734` (`wip: add local Planimation adapter seam`). Not pushed.
- First pytest formal run: 62 passed, 1 failed; classified EASY because the test matched the stable reason code against the human-readable exception detail in one test file. Bounded fix applied.
- One retest: `63 passed in 0.55s`.
- No backend process, HTTP request, integration harness, 8-object/12-object smoke, production command, or 16,822-state render ran. Attempt output root was never created.

## Failures

Failure 1 command:
```
source ~/cd_vlaplan && python -m pytest tests/test_planimation_phase1.py tests/phase3/test_cgas_pilot_planimation_adapter.py tests/phase3/test_local_planimation_adapter_integration.py -q
```
Output exactly:
```
Conda environment 'ada_vla' is already activated.
..........................................................F....          [100%]
=================================== FAILURES ===================================
____________________ test_harness_refuses_non_loopback_urls ____________________

    def test_harness_refuses_non_loopback_urls() -> None:
        harness = _load_harness()
        with pytest.raises(harness.ProofError, match="refusing_non_loopback_url"):
>           harness._assert_loopback_url("https://example.com/upload/pddl")

tests/phase3/test_local_planimation_adapter_integration.py:34: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

url = 'https://example.com/upload/pddl'

    def _assert_loopback_url(url: str) -> None:
        """Refuse any server URL that is not an HTTP loopback URL."""
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme != "http" or host is None or host.lower() not in LOOPBACK_HOSTS:
>           raise ProofError("refusing_non_loopback_url", f"refusing non-loopback URL: {url}")
E           local_planimation_adapter_integration.ProofError: refusing non-loopback URL: https://example.com/upload/pddl

.claude/evidence/cgas-phase3-pilot-rendering/local_planimation_adapter_integration.py:136: ProofError

During handling of the above exception, another exception occurred:

    def test_harness_refuses_non_loopback_urls() -> None:
        harness = _load_harness()
        with pytest.raises(harness.ProofError, match="refusing_non_loopback_url"):
>       with pytest.raises(harness.ProofError, match="refusing_non_loopback_url"):
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'refusing_non_loopback_url'
E         Actual message: 'refusing non-loopback URL: https://example.com/upload/pddl'

tests/phase3/test_local_planimation_adapter_integration.py:33: AssertionError
=========================== short test summary info ============================
FAILED tests/phase3/test_local_planimation_adapter_integration.py::test_harness_refuses_non_loopback_urls
1 failed, 62 passed in 0.78s
```

EASY verdict: the single failure was a test-side mismatch — the assertion matched the stable reason code against the human-readable exception detail (`refusing non-loopback URL: ...`) instead of the structured `reason` attribute, in exactly one test file. The bounded test-only fix was applied (loop over the three invalid URLs, capture `excinfo`, assert `excinfo.value.reason == "refusing_non_loopback_url"`). The single retest passed 63.

Failure 2 command:
```
source ~/cd_vlaplan && ruff check scripts/planimation_phase1_client.py scripts/phase3/planimation_pairing_contracts.py scripts/phase3/planimation_pairing_rendering.py scripts/phase3/cgas_pilot_planimation_adapter.py .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_adapter_integration.py tests/test_planimation_phase1.py tests/phase3/test_cgas_pilot_planimation_adapter.py tests/phase3/test_local_planimation_adapter_integration.py
```
Output exactly:
```
Conda environment 'ada_vla' is already activated.
E501 Line too long (128 > 121)
  --> scripts/phase3/planimation_pairing_contracts.py:22:122
   |
20 | )
21 | CURRENT_IMAGE_FRAME_ROOT = Path("outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725")
22 | CURRENT_SELECTION_CACHE_ROOT = Path("outputs/image_frames/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800")
   |                                                                                                                          ^^^^^^^
23 | CURRENT_TEXT_RECORD_ROOT = Path("outputs/reasoning_traces/vlm_records/stratified_pilot_20260725")
24 | PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
   |

I001 [*] Import block is un-sorted or un-formatted
  --> tests/test_planimation_phase1.py:1:1
   |
 1 | / from __future__ import annotations
 2 | |
 3 | | import io
 4 | | import importlib
 5 | | import json
 6 | | import types
 7 | | import zipfile
 8 | | from io import BytesIO
 9 | | from pathlib import Path
10 | | from typing import Any
11 | |
12 | | import pytest
13 | | import requests
14 | | from PIL import Image
15 | |
16 | | from scripts.planimation_phase1 import (
17 | |     derive_endpoint_candidates,
18 | |     extract_png_archive,
19 | |     load_manifest,
20 | |     post_pddl_for_vfg,
21 | |     preflight_host,
22 | |     render_vfg_to_local_png_frames,
23 | |     select_entries,
24 | |     unique_asset_downloads,
25 | |     validate_entry_assets,
26 | | )
   | |_^
help: Organize imports
   |
2  |
3  + import importlib
4  | import io
   - import importlib
5  | import json
--------------------------------------------------------------------------------
26 | )
   -
27 |
   |

Found 2 errors.
[*] 1 fixable with the `--fix` option.
```

HARD verdict: the formal failure spans two files (`tests/test_planimation_phase1.py` and `scripts/phase3/planimation_pairing_contracts.py`), so it does not meet the EASY one-file criterion; per policy no second remediation/retest cycle was attempted. Black, basedpyright, real loopback integration validation, evidence assertions, and final Git/clone checks were not run.

## Suspected Root Cause
- High confidence: I001 is a new test import-order issue (`importlib` should precede `io`).
- High confidence: E501 is a pre-existing 128-character constant in `scripts/phase3/planimation_pairing_contracts.py:22`, unrelated to the appended RenderConfig field, but included in the formal Ruff scope and therefore keeps the command red.
- Neither diagnosis is a backend failure; localhost behavior remains untested.

## Next Session Options
- A: Continue the plan at the next dependency-ready item — real 4-object localhost adapter/StateRenderer validation. This is NOT dependency-ready while formal Ruff is red and therefore should not be chosen first.
- B: Fix the recorded Ruff issues first (fast-fail, no-fallback): reorder imports in `tests/test_planimation_phase1.py`; wrap the pre-existing long constant in `scripts/phase3/planimation_pairing_contracts.py`; rerun the exact Ruff command once, then resume remaining Black/basedpyright/one real 4-object loopback validation only if green.
- Recommend B with one-line reason: it clears the exact recorded formal blocker before any backend/network action.
- Hard boundaries: no 8/12-object smokes, no production render/operator command, no hosted request/fallback, no clone edit, no push until a later success session completes verification.
- Smallest first inspection: read this handoff and inspect only the two Ruff diagnostic lines before editing.

Coverage remains `0/16,822`, operator command remains NOT EXECUTABLE, `.slim/clonedeps/` remains untracked/untouched.
