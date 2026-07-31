# CGAS Partition Selection

- `scripts/phase3/cgas_partition_selection.py` consumes only `parse_bundle()` final-member bytes and does not re-read the source manifest or rerun planners.
- Paired-exact eligibility requires complete source traces, exact replay, and goal satisfaction for both BFS and IW.
- The verified 481-row bundle fingerprint `0856e76571643362abb70551ff9d4e02e2d585f7384fc3ac0adb64df240d893a` has only 24 paired-exact rows, all with four objects. It cannot meet the mandatory all-12-object structural OOD rule.
- The selector therefore writes a deterministic, unapproved `draft_for_owner_review` feasibility artifact with empty records, full exclusion IDs, `failure=structural_ood_ineligible`, digest bindings, and no approval digest.
- Successful future selection retains complete threshold ties and whole composition groups, uses deterministic Gower farthest-point ordering for exact 39-row calibration, and fails instead of weakening any minimum.
