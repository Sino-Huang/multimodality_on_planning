# Phase 3 Planimation Pilot Contract and Render Recovery

## Durable Contract

`input_pairing_manifest_sha256` identifies the full source pairing manifest
used when a rollout selection was frozen. It is provenance, not a requirement
that a selected output reproduce the full source manifest.

Promotion requires that provenance before considering selected-subset equality.
The value must be a string of exactly 64 lowercase hexadecimal characters;
missing, uppercase, wrong-length, and other non-hexadecimal values fail as
`invalid_frozen_selection`. This check is independent of the selection
self-hash: negative tests recompute `selection_sha256` after provenance mutation.

Promotion accepts an output subset only when the output pairing manifest is
exactly equal to the complete frozen selected-pair record multiset. Record
multiplicity matters. Missing, extra, mutated, and duplicate records remain
fail-closed. A probe that changed `source_record_sha256` was rejected by the
selection-bound release verifier and by promotion identity checks.

## Approved Pilot Identity

- Source pairing manifest SHA-256: `de298099d2b3456322f6ebf692b4fd1307a3b146a7e27aff48848794da1cd9d8`.
- Frozen selection file SHA-256: `fbd09063a56685dfb12367d17fd8d1909bbbaeac8dd6299b068280ae11af9f6d`.
- Source root SHA-256: `a8c1fe317f5f3909aea4af28c519aa4af9c4eefb406667c644b46cd15aba3214`.
- Pilot subset pairing SHA-256: `6f78c69ded1c6e765888bce5415e306157aa3b756d996a6de32b2d9d486e2b52`.
- State manifest SHA-256: `73c6c5519b20c531f7a8902438e0e8177ebc2202f67a9579bb2c44e219d9b22e`.
- Hybrid manifest SHA-256: `3083610ddc17f3950641d1c17023d8fff32ffc8aa71a73bbfc284e2c622b7bc7`.
- Semantic validator SHA-256: `89738283d69ea51e2885eff3f421528d3940d05e7848b61595d1816528b3a8ae`.
- Final Ferry profile SHA-256: `9295ea8b1ed5f60a05a98fcd5c2eac6c7cccef156c4572d59e5668300d4351b4`.

## Promotion Chain

The preserved historical fixture attempt used the default 1.0-second request
delay. That produced renderer config SHA-256
`cb01219d76039a088d453a46b67ca1a316d94f0cf486438c85947812e9a469d6`,
cache key `ad347eb66b12107b3630f86ae399c411`, and one remote request.

The recovered config matched the pilot: base URL
`https://planimation.planning.domains`, timeout 90, request delay 0.0, and three
maximum attempts. Its SHA-256 is
`6c51ad1a5be2f0e5ca73f562f9392439520b01e4c5d4a8e0e8f08c2b7c78f5af`.
The fixture reused cache key `45e2c4e6959e5c6b317384d94317d7b6`.

The clean root promoted a 1-state cache-only fixture. The receipt file-byte
SHA-256 is
`d59677121f0b40b23df01b25e7802a7ccc1b30c3693ff5fbaf45b92ac92eed38`,
and its embedded `receipt_sha256` self-hash is
`0df245b600361967bb5c1e24f0cdf8912956356337df329b99e1fec79d153941`.
It then promoted a 39-state changed-canary spanning 18 cache directories,
receipt
`f82b4585eff12a14d38e2f018d77e49a5d14a5aba66701c6f9cf84eac06fdab9`.
Both had no external network connection. One later fixture setup timed out
before generator output. Another omitted `--dataset-root` and stopped because
the selected pair was absent. Neither connected to the network.

The real `stratified-pilot` assessment used the changed-canary receipt and
produced approved receipt
`1bef38d5571cd3e8276f4d925e13553475914fe0e51f3d459ec83a16c25694e7`.

## Final Counts

- 52 pairs and 2,568 successful cache-hit states.
- Full train/dev/test records: 19/19/14.
- Step train/dev/test records: 68/130/133.
- Search-traversal train/dev/test records: 329/1160/696.
- Six domains, production mode, `partial=false`, `production_complete=true`, `skipped={}`.

All 5,343 original pilot files and all 5,324 cache paths remained unchanged.
Only `diagnostics/rollout_promotion_receipt.json` was added. The original frozen
selection was used directly and wasn't modified.

## Operating Boundary

The launcher has separate fresh and resume commands:

```bash
bash temp_fast_planimation_render.sh
PILOT_OUTPUT_ROOT=outputs/phase3_planimation_frames_stratified_pilot_20260725 bash temp_fast_planimation_render.sh --resume
```

Todo 7 didn't rerun either launcher command. It verified and promoted the
already recovered pilot through direct selection-bound verifier and rollout
gate commands.

The complete operator commands are:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_planimation_vlm --output-root outputs/phase3_planimation_frames_stratified_pilot_20260725 --mode manifest --selection-file outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800/diagnostics/rollout_selection.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_planimation_vlm --output-root outputs/phase3_planimation_frames_stratified_pilot_20260725 --mode render --selection-file outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800/diagnostics/rollout_selection.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_planimation_vlm --output-root outputs/phase3_planimation_frames_stratified_pilot_20260725 --mode release --selection-file outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800/diagnostics/rollout_selection.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.rollout_gates assess --output-root outputs/phase3_planimation_frames_stratified_pilot_20260725 --stage stratified-pilot --selection-file outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800/diagnostics/rollout_selection.json --prior-receipt tmp/phase3_planimation_todo7_promotion_chain_20260726/recovery/changed-canary/diagnostics/rollout_promotion_receipt.json
```

Expected success is manifest verification of 52 pairs; render verification of
52 pairs and 2,568 states; release verification of full records 19/19/14, step
records 68/130/133, search-traversal records 329/1160/696, and production
complete; then promotion with `approved=true`, empty `reasons`, 52 pairs, and
2,568 states. Every command uses the original frozen selection. Promotion uses
the approved changed-canary receipt at the exact `--prior-receipt` path above.

The verifier commands are read-only checks. The `assess` command writes or
refreshes only the actual pilot
`diagnostics/rollout_promotion_receipt.json`, so it is an operator action rather
than a read-only audit. This independent-review remediation didn't rerun any
pilot command, including verification or assessment.

The full 2,328-pair, 537,696-state corpus remains incomplete. The approved
receipt applies only to the 52-pair pilot.

## Final Oracle Hardening

The final Oracle review identified and resolved one Medium provenance-format
gap. Exact selected-record subset equality never bypasses source-provenance
validation. The focused gate/verifier suite remains at 21 passing tests;
basedpyright remains clean, compileall and `git diff --check` exit 0, and Ruff
remains unavailable without being installed.

## F2 Quality Remediation

Selection consumers share strict lowercase SHA-256 and ordered selection-ID
validation: `selected_pair_ids` must be nonempty, unique, and exactly ordered
with the IDs in `selected_pairs`, while `Counter`-based full-record multiset
equality remains the downstream identity guard. The launcher identifies active
generators through literal `/proc` argv parsing rather than a `pgrep -f` regex.
Ignored profile review evidence is under
`.omo/evidence/planimation-pilot-contract-and-render-recovery/f2-remediation/`;
it records whole-file and image-section hashes plus a no-index normalized
contract diff without staging or editing profiles. The F2 focused suite passed
55 tests with clean Basedpyright, compileall, Bash syntax, JSON/hash, index, and
diff checks. No pilot-facing command ran during the remediation.
