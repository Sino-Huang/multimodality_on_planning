# Planimation State-Render Upload URL Contract

## Context

`render_state_with_planimation()` returns `used_pddl_url` on successful PDDL uploads. `_render_one_state()` merges that result into the persisted state-render manifest.

## Contract Rule

`used_pddl_url` is optional, nonempty string metadata for state-render records. It is absent from cache hits and failed render records, but must be accepted for fresh successful remote renders.

## Regression Coverage

`tests/phase3/test_planimation_pairing.py::test_render_replay_accepts_successful_pddl_upload_url` exercises the renderer-result to persisted-record validation path. It prevents strict validation from rejecting a successful Planimation state render with `state render unexpected used_pddl_url`.

## Verification

The bounded Blocksworld smoke CLI completed with one successful state render and `errors: []` after the contract update.
