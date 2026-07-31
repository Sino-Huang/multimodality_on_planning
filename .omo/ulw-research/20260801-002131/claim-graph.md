# Claim Graph

## Verified Claims
- C1: The CGAS dataloader milestone produced an authorized 12-row release with strict Qwen preflight and native loader evidence. Status: supported by O4, O7, O8.
- C2: The release is a pipeline/infrastructure proof, not evidence that the calibration gate or CGAS method gate has passed. Status: supported by O1, O2, O4.
- C3: The next research-critical dependency is a valid calibration-ready corpus with sufficient structural diversity and a direct baseline failure matrix. Status: supported by O1, O2, O5, O6.
- C6: Bounded memory is technically implementable against the 12-row fixture release but is not a substitute for the production partition/calibration gate. Status: supported; safe only as parallel fixture-scoped contract work.
- C7: The release gate's accepted status is corpus-integrity approval, not proof of a policy-compliant production partition. Status: supported by O9, O10, and the expansion approval audit.
- C8: Frozen blocker evidence no longer binds the current draft bytes; the content is scientifically identical except for `implementation_sha256`. Status: supported by O11 and the expansion hash audit.

## Unresolved
- C4: Whether the active structural-OOD policy should be changed or a new/diversified characterization should be generated. Recommendation: preserve the policy and generate diversified inputs unless the owner explicitly authorizes a scientific policy revision.
- C5: Whether a direct VLA baseline can be trained with the released 12 rows. Not justified for the intended calibration gate because the plan requires held-out calibration and recurrent failures; no calibration execution receipt was found in the inspected sources.
