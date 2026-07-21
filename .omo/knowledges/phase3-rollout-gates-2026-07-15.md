# Phase 3 Rollout Gates

`rollout_gates.py prepare` freezes deterministic eligible pair IDs and immutable source provenance from a fresh pairing manifest. Pass its `rollout_selection.json` to `generate_planimation_vlm.py --selection-file` so the rendered root cannot include unselected pairs. `rollout_gates.py assess` writes a promotion receipt, fails closed on selection integrity/preparation failures, and otherwise requires `verify_planimation_vlm.py` release success.

The rollout order is fixture, changed-canary, stratified-pilot, complete-domain, then frozen-full. The active frozen source roots may be blocked legitimately: legacy rows without `phase3_traversal_trace_v1` are excluded rather than backfilled. Do not promote or render around that block.
