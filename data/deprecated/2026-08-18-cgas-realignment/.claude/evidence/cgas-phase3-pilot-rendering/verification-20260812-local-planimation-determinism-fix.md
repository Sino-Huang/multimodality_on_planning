# Verification — 2026-08-12 Local Planimation Determinism Fix

## Scope

- Investigated the pinned local Planimation backend at commit `94d82afb5ee122ce579dd11ca1953b7c85ca5824` without editing the GPL clone.
- Confirmed that the supplied profile's exact `(color RANDOMCOLOR)` sentinel reaches the backend's process-global `random.choice`, causing replay-request color drift.
- Added an outside-clone, in-memory materialization to `(color GREY)` after source hash verification. The on-disk profile, expected hash, backend process, and raw VFG byte-equality hard stop remain unchanged.
- Added focused project-owned regression coverage.
- Hosted requests: `0`. Production: not started. No fallback was attempted.

## Final Verification Sequence

The sequence was required to stop at the first nonzero command without remediation or rerun.

### Command 1 — output parent preflight

Command:

```text
ls -ld outputs/image_frames
```

Exit: `0`

Actual output, verbatim:

```text
drwxr-sr-x 13 sukaih punim0478 4096 Aug 12 01:14 outputs/image_frames
```

### Command 2 — fresh output target preflight

Command:

```text
test ! -e outputs/image_frames/cgas-local-planimation-proof-deterministic-20260812
```

Exit: `0`

Actual output: empty.

### Command 3 — focused regression gate

Command:

```text
source ~/cd_vlaplan && python -m pytest tests/phase3/test_planimation_profile_regressions.py -q
```

Exit: `0`

Actual output, verbatim:

```text
Conda environment 'ada_vla' is already activated.
.............                                                            [100%]
13 passed in 0.56s
```

### Command 4 — scoped Ruff gate

Command:

```text
source ~/cd_vlaplan && python -m ruff check .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_backend_proof.py tests/phase3/test_planimation_profile_regressions.py
```

Exit: `1`

Full actual stdout/stderr, verbatim:

```text
Conda environment 'ada_vla' is already activated.
RUF100 [*] Unused `noqa` directive (non-enabled: `BLE001`)
   --> .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_backend_proof.py:764:31
    |
762 |         report["exception"] = {"type": type(exc).__name__, "detail": exc.detail}
763 |         return _emit_hard_stop(output_root, report, exc.reason, exception=report["exception"])
764 |     except Exception as exc:  # noqa: BLE001 - capture exact unexpected failures.
    |                               ^^^^^^^^^^^^^^
765 |         detail = f"{type(exc).__name__}: {exc}"
766 |         report["exception"] = {"type": type(exc).__name__, "detail": str(exc)}
767 |         return _emit_hard_stop(output_root, report, "harness_exception", exception=report["exception"])
    |
help: Remove unused `noqa` directive
    |
763 |         return _emit_hard_stop(output_root, report, exc.reason, exception=report["exception"])
    -     except Exception as exc:  # noqa: BLE001 - capture exact unexpected failures.
764 +     except Exception as exc:
765 |         detail = f"{type(exc).__name__}: {exc}"
    |

F841 Local variable `detail` is assigned to but never used
   --> .claude/evidence/cgas-phase3-pilot-rendering/local_planimation_backend_proof.py:765:9
    |
763 |         return _emit_hard_stop(output_root, report, exc.reason, exception=report["exception"])
764 |     except Exception as exc:  # noqa: BLE001 - capture exact unexpected failures.
765 |         detail = f"{type(exc).__name__}: {exc}"
    |         ^^^^^^
766 |         report["exception"] = {"type": type(exc).__name__, "detail": str(exc)}
767 |         return _emit_hard_stop(output_root, report, "harness_exception", exception=report["exception"])
    |
help: Remove assignment to unused variable `detail`

I001 [*] Import block is un-sorted or un-formatted
  --> tests/phase3/test_planimation_profile_regressions.py:1:1
    |
  1 | / from __future__ import annotations
  2 | |
  3 | | import hashlib
  4 | | import importlib.util
  5 | | import json
  6 | | import re
  7 | | from pathlib import Path
  8 | |
  9 | | import pytest
 10 | |
 11 | | from scripts.phase3.render_semantics import _decode_png, _parse_stage_zero_sprites, _sprite_has_coverage, validate_render_artifacts
    | |___________________________________________________________________________________________________________________________________^
 12 |
 13 |   ROOT = Path(__file__).parents[2]
    |
help: Organize imports
    |
 10 |
    - from scripts.phase3.render_semantics import _decode_png, _parse_stage_zero_sprites, _sprite_has_coverage, validate_render_artifacts
 11 + from scripts.phase3.render_semantics import (
 12 +     _decode_png,
 13 +     _parse_stage_zero_sprites,
 14 +     _sprite_has_coverage,
 15 +     validate_render_artifacts,
 16 + )
 17 |
    |

E501 Line too long (131 > 121)
  --> tests/phase3/test_planimation_profile_regressions.py:11:122
    |
  9 | import pytest
 10 |
 11 | from scripts.phase3.render_semantics import _decode_png, _parse_stage_zero_sprites, _sprite_has_coverage, validate_render_artifacts
    |                                                                                                                          ^^^^^^^^^^
 12 |
 13 | ROOT = Path(__file__).parents[2]
    |

E501 Line too long (169 > 121)
  --> tests/phase3/test_planimation_profile_regressions.py:15:122
    |
 13 | …
 14 | …imation_backend_proof.py"
 15 | …ender-recovery/task-5-planimation-pilot-contract-and-render-recovery/ferry-failed-attempt"
    |                                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 16 | …nd-render-recovery/task-5-planimation-pilot-contract-and-render-recovery/elevators-failed-attempt"
    | …
    |

E501 Line too long (177 > 121)
  --> tests/phase3/test_planimation_profile_regressions.py:16:122
    |
 14 | …ion_backend_proof.py"
 15 | …r-recovery/task-5-planimation-pilot-contract-and-render-recovery/ferry-failed-attempt"
 16 | …ender-recovery/task-5-planimation-pilot-contract-and-render-recovery/elevators-failed-attempt"
    |                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 17 | …
 18 | …d834e823719b180eab95165d0ca53216c",
    |

E501 Line too long (122 > 121)
  --> tests/phase3/test_planimation_profile_regressions.py:20:122
    |
 18 |     "data/pddl_instances/gripper/gripper_AP.pddl": "9acbc33f9b0719cd4bb2e1f4e469a12d834e823719b180eab95165d0ca53216c",
 19 |     "data/pddl_instances/ferry/ap.pddl": "871681463f96a3bd8af434bccbf54b2d7f8cbf0bf4cf14e6117fbfddcdaea355",
 20 |     "data/pddl_instances/elevators/elevators_ap.pddl": "98eabfd7f6a20104385a146aee971c6331c00514a81254280fc7a1c1f8f39a19",
    |                                                                                                                          ^
 21 |     "data/pddl_instances/logistics/logistics_ap.pddl": "4d7044a096d5c3203214644fc3869e41c99cc1f417614cccc22f9e6873c29fb5",
    |                                                                                                                          ^
 22 | }
    |

Found 8 errors.
[*] 2 fixable with the `--fix` option (1 hidden fix can be enabled with the `--unsafe-fixes` option).
```

## Result

Final verification failed at Command 4 and stopped without remediation. The fresh local proof command was not run, so replay-3 determinism after the fix, PNG semantic validation, empty-plan behavior, and 12-object validation remain unverified. No proof output directory was created. Hosted requests remained `0`; production was not started.

The focused regression gate passed (`13 passed`). The Ruff output includes both pre-existing diagnostics in the harness/test file and import formatting affected by the newly added import, but no correction or rerun is applied in this session.
