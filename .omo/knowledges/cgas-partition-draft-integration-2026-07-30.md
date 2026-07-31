# CGAS Partition Draft Integration

- The authoritative accepted manifest digest is `9a9817058e36f72468682c8b43a46c04591995bcb8fe28ee37819313f9376217`; it supplies exactly 481 Blocksworld identities to the final bundle.
- The final bundle SHA-256 is `942d7be93ad0eb0ec6580bfe380fb8f09141662140ffc3d3c98e7f09a10ddaf4` with fingerprint `0856e76571643362abb70551ff9d4e02e2d585f7384fc3ac0adb64df240d893a`.
- Independent parsing shows 190 four-object, 198 eight-object, and 93 twelve-object rows. Only 24 identities are paired-exact, all four-object; all 93 twelve-object rows are ineligible.
- The deterministic selector output SHA-256 is `409f712797f8f02d49fe6d6b5a5b4e7a444f38c54e2cdefcbd4e0e9e7214630d`: 457 exclusions, no role records, `failure=structural_ood_ineligible`, `owner_approved=false`, and no approval digest.
- `tests/phase3/test_cgas_partition_selection_real_bundle.py` is the local regression for the real immutable inputs. It derives a fresh draft, asserts byte equality, validates all 24 eligible IDs and all 457 exclusion IDs by set difference, and checks the 12-object failure condition.
- Treat this as a fail-closed feasibility result. Do not claim any P0 partition, release, rendering, conversion, loader QA, promotion, or approval until a successor characterization makes every 12-object row paired-exact and the selector yields role-bearing output satisfying all group/count constraints.
