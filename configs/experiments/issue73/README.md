# Visual-state corpus release (#73)

This successor releases the approved #72 selection as complete process traces:
**238 task groups, 302 algorithm episodes, 49,274 states and 76,217 decisions**.
It includes a matched text-state baseline and visual-state training views.
All three modality projections are qualified together; #74 owns the separate
multimodal-state release. No training, evaluation, or GPU throughput result is
claimed here.

The three BFWS hard Visitall exclusions remain exactly those recorded in
`configs/experiments/issue72/views-panel-32k-v2.json`. Every retained task keeps
its source train/dev assignment, complete trace, teacher operations, candidate
membership, and bounded Search Memory. Both additive settings remain paired.
The common capacity is 16 accepted deltas with the source compaction policy;
the larger 32,768-token context accommodates readable pages. Every complete
input must leave the same 384-token output allowance.

## Completed release

Materialization and the independent read-only check both passed all 238 tasks
and 76,217 decisions. The global audit reports zero semantic/input split overlaps
and zero conflicting identical-input targets. Shards occupy 11,126,647 bytes.
Maximum input tokens are 8,659 text / 16,812 visual / 23,379 multimodal; the
maximum target is 307 tokens. The full repository suite passed: 970 passed,
13 skipped. Both review axes passed; changed-file formatting/lint and typechecking
passed. Evidence: `docs/experiments/issue73/release-summary.json`.

The commands below document the completed attempt. Use `--check` to verify it;
materialization intentionally refuses to overwrite it.

## Authorization and execution

`contract.json`, `gate.json`, and `authorization.json` bind this exact successor,
its #71 parent gate, approved #72 views, and `release-001` output. The user
requested implementation and execution of #73. These receipts authorize corpus
work only. They do not activate the original 8K training configurations at 32K.

```bash
source ~/cd_vlaplan
python scripts/release_visual_corpus.py --dry-run
python scripts/release_visual_corpus.py --materialize --workers 4
python scripts/release_visual_corpus.py --check --workers 4
```

The release is at
`outputs/modality_corpus/issue73-visual-32k-v1/release-001/report.json`.
`--check` is read-only. A completed attempt cannot be overwritten. After an
interruption without a final report, use the same command with `--resume`;
completed task shards are replay-checked and reused. A changed setting or output
requires a successor contract and matching receipts. `--limit-tasks N` is a
bounded development option and always ends in incomplete `VALID_STOP`.

Every stage prints completed/total, elapsed time, ETA, and heartbeats. Missing
or mismatched authorization is `INVALID`; a resource or incomplete-coverage stop
is `VALID_STOP`; a stopped predecessor is `ANCESTOR_STOP`. Both governed stops
retain a `gated-not-run` receipt. `INVALID` never means scientific completion.

## Stored records and model inputs

Each compressed task shard retains one authoritative family input and teacher
target per decision, plus the source process row/trace paths, task/split/decision
identity, #72 view manifest, ordered input page bindings, and a separate
`after_operation` result/successor binding. Task manifests link the source PDDL,
source-goal expression, scene catalogs, supplied Action Sequences, VFG paths,
state recipes and reusable context/goal pages through the #72 provenance chain.
Paths in corpus records are repository-relative.

The shard is an authoritative record store. It is not a chat dataset to feed
directly to a trainer: use `VisualCorpus.training_example` to obtain model-facing
messages and PIL images. That boundary excludes result metadata, applies the
shared family chat builder, and attaches the complete ordered page set on every
call. Visual-state has scene-plus-relation pages and partial-goal pages; matching
state/goal facts are additionally supplied as text in text-state. Common
instructions, Search Memory, candidate facts and the relation legend are shared.

```python
from pathlib import Path
from examples.planning_benchmark_slice.modality_corpus import VisualCorpus

root = Path.cwd()
corpus = VisualCorpus(
    root,
    root / "outputs/modality_corpus/issue73-visual-32k-v1/release-001/report.json",
)
record = next(corpus.records(algorithm="bfs", split="train"))
visual = corpus.training_example(record)  # messages, images, ordered page_roles
text = corpus.training_example(record, modality="text-state")
```

Iteration follows the staged curriculum: easy/medium/hard, domain, whole task,
then decision order. Algorithms and train/dev splits are requested explicitly.
Existing 128×128 scenes and reusable PNGs are referenced, without copies.
Current-state pages are composed on demand with the #72 64 MiB per-process cache.
`after_operation` never enters the model input; its successor state resolves to
the corresponding recipes only after the producing operation.

## Validation and handoff

The release checks every task and decision through the trusted family runtime:
FIFO BFS, unpruned BFWS with exact novelty/pruning facts, and both additive
settings. Reconstructed live inputs and parsed/applied teacher targets must
match the source records. PDDL replay also checks current/successor/frame
bindings. Every state's page recipe exposes complete facts and source-goal
constraints. All three complete templated inputs and every teacher target are
measured with the frozen Qwen processor/tokenizer.

The global audit checks whole-task semantic and model-input split isolation and
conflicting targets for identical model-visible inputs. Its keys contain actual
semantics, without hashes. Later #71 guidance supersedes the old byte-identical
regeneration wording: validation uses semantic replay, parity, provenance and
resource limits, without file-integrity or regeneration comparisons.

#74 can reuse these authoritative rows, the shared projection, and the approved
assets for its matched multimodal-state release. #75/#76 still require a combined
corpus-stage receipt under the matching successor settings and actual hardware
qualification before their governed model runs. Corpus completion establishes
usable supervised records, not structural/process competence or an advantage
against the oracle-assisted random-valid control.
