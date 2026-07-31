# CGAS Replay Image Alignment

For CGAS P0 rows, image alignment cannot be proven by frame count. Verify the
authoritative source root with `verify_corpus(..., withdraw=False)`, then bind
each source `record_id` to exactly one Planimation-derived render receipt.

The required independent evidence is:

- the replay `state_before_id` matches the receipt and the derived PDDL init;
- the receipt PNG is decodable and its persisted digest matches the file;
- the semantic render receipt succeeds against the derived render VFG;
- the source VFG actions match replay actions through the selected step;
- `t=0` also has a decodable initial-state frame.

The alignment verifier must fail closed on any missing, duplicate, unreadable,
action-order, or state-linkage failure and must not replace a bad transition
with a later image.
