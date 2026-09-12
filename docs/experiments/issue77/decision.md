# Development synthesis and deadline decision (#77)

**NO_GO for final evaluation. Continue with #100 → #108 only.** All #76 execution
and replay work completed, but none of its four adapters passes the already
specified readiness thresholds. No additional GPU experiment or automatic retraining
is justified within this deadline study. This is an evidence-based stop after a
complete negative pilot, not a claim that the remaining experiments were performed.

## Evidence considered

#75 v5 trained four visual adapters on 43,876 records for two epochs and evaluated
864 episodes across 42 task groups. Its selected coverage is complete and independently
replayed. Learned success is 100% for BFS and both additive settings, and 66.7% for
BFWS. The frozen gate remains VALID_STOP because BFWS falls below 80%. BFS has a
positive saved whole-instance lower bound on gain over its best control. Additive
random-valid references saturate at 100%, so additive success does not establish
an advantage over that reference on this panel.

#76 trained each multimodal adapter on 512 records for one epoch (16 updates),
seed 17, then completed and independently replayed all 48 declared episodes on
storage, blocksworld and ferry. Exact references succeed in all 12 cases; random-valid
succeeds in 9/12. Base succeeds in 0/12, and SFT in 2/12: 0/3 BFS, 0/3 BFWS and
1/3 for each additive setting. Every SFT setting fails both 80% success and 5%
maximum invalid-operation-rate thresholds. Failed SFT episodes end on deterministic
invalid operations, including malformed operation schemas or invalid state/update
choices. These are model outputs retained by the trusted runtime, with no silent
repair. The evidence does not show a runtime, context-overflow, OOM or timeout failure.

The full visual and short multimodal training schedules differ substantially.
A direct score difference cannot identify a modality effect. #67's text/curriculum
results use another corpus/input and training contract, and cannot fill the missing
matched text baseline. Its historical results remain separate, including its
saturated random-valid control and stopped original heuristic-representation claim.

## Decision and remaining claims

The completed pilot did not produce ready multimodal adapters for the proposed
final comparison. A single optional DAgger cell would leave three other readiness
failures and the training-design mismatch unresolved; no cell is selected. Do not
use the unused budget for repeat-until-positive training or further test-set calls.
Under-training is a possible explanation for the short pilot's result, not an
identified causal conclusion. No inference of intrinsic multimodal inferiority is
supported by this unmatched comparison.

The selected route is a **development feasibility and limitations report**, followed
by an evidence/artifact release. #90–#95, #97 and #109 are not selected; #78–#84 are
skipped optional work. Previously deferred end-to-end, broad robustness, replication
and transfer remain unmeasured. Their absence must be explicit in #100 and #108.
No held-out, DAgger, training-seed-variance, architecture-generalization or transfer
claim is permitted. Completing those claims would require a new prospective plan.

The core runs used one training seed each; five visual rollout seeds are not five
training replicates. The visual run took 76.23 hours; the multimodal pilot took
64.92 minutes within its four-hour cap. These are wall-clock durations, not
GPU-hours, and earlier attempts must be listed separately in compute accounting.

All inputs to this decision are linked in `decision.json`. No model calls were
made for this synthesis, and all original performance outcomes remain unchanged.
