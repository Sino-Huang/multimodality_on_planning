# Phase 3 F4 Scope-Fidelity Relocation Evidence

Date: 2026-07-16

## Authorized Moves

- `outputs/phase3_planimation_vlm_blocksworld_smoke_20260715` to `tmp/phase3_planimation_vlm_blocksworld_smoke_20260715`
- `outputs/phase3_planimation_vlm_manifest_audit_20260715` to `tmp/phase3_planimation_vlm_manifest_audit_20260715`
- `outputs/phase3_planimation_vlm_manifest_safe_audit_20260715` to `tmp/phase3_planimation_vlm_manifest_safe_audit_20260715`
- `outputs/phase3_planimation_vlm_manifest_smoke_20260715` to `tmp/phase3_planimation_vlm_manifest_smoke_20260715`

The operation used `mv` for every root. Nothing was deleted.

## Preservation Check

| Relocated root | Files before | Files after | Size before | Size after |
| --- | ---: | ---: | ---: | ---: |
| `phase3_planimation_vlm_blocksworld_smoke_20260715` | 9 | 9 | 11M | 11M |
| `phase3_planimation_vlm_manifest_audit_20260715` | 3 | 3 | 13M | 13M |
| `phase3_planimation_vlm_manifest_safe_audit_20260715` | 3 | 3 | 9.6M | 9.6M |
| `phase3_planimation_vlm_manifest_smoke_20260715` | 3 | 3 | 1.2M | 1.2M |

## Scope Verification

- No `outputs/phase3_planimation_vlm_*_20260715` root remains.
- `outputs/deprecated/` was ignored.
- The four frozen `outputs/phase3_curriculum_traces_*` roots remain in their original locations.
- No plan checkbox was edited.
- Documentation references to the relocated generated roots now use `tmp/`.

## Artifact Availability

All four roots are available under `tmp/`. Current verifier replay isn't claimed for the two historically documented artifacts. Both `tmp/phase3_planimation_vlm_blocksworld_smoke_20260715` and `tmp/phase3_planimation_vlm_manifest_audit_20260715` currently fail verification with `source_snapshot_mismatch: malformed_provenance: source_root_id`, which reflects their legacy manifest provenance rather than relocation loss.
