# Matched multimodal-state corpus (#74)

This release adds the multimodal-state projection to the approved #73 corpus.
It references the same authoritative records and #72 assets, retaining all
**238 task groups / 302 algorithm episodes / 49,274 states / 76,217 decisions**.
Each of text-state, visual-state and multimodal-state covers the same decisions,
for 228,651 released decision projections across 12 algorithm/modality cells.

## Contract and representation

`contract.json`, `gate.json`, and `authorization.json` bind the exact successor,
its output, the #71 parent gate, the #72 approved pages, and the completed #73
source release. The user explicitly requested implementation and execution of
#74. These receipts authorize corpus work only.

The source whole-task train/dev assignments, the three approved BFWS hard
Visitall exclusions, both paired additive settings, teacher targets, candidate
facts, and Search Memory remain identical. All three arms use the same source
compaction policy and capacity of 16 accepted deltas. Inputs use the approved
32,768-token context with 384 output tokens reserved; no fields or pages are
truncated to fit.

A multimodal example pairs the text-state semantic blocks with the same ordered
visual-state pages: task context, current state, then partial-goal constraints.
All pages accompany every call. The source-goal expression, including negation
and quantified variable scope, is shared by text and drawing instructions.
Search Memory and candidate information use the same family builder in all arms.
Runtime-result and successor bindings remain outside the producing model input.

The new release manifest references #73's compressed task shards. It does not
copy records, 128×128 scenes, reusable PNGs, or state drawing recipes. The
record schema keeps its historical #73 name because its authoritative content
has not changed. The release contract determines which projections are exposed.
Current-state pages are composed on demand with the same 64 MiB per-process cache.

## Commands

```bash
source ~/cd_vlaplan
python scripts/release_multimodal_corpus.py --dry-run
python scripts/release_multimodal_corpus.py --materialize --workers 4
python scripts/release_multimodal_corpus.py --check --workers 4
```

Output: `outputs/modality_corpus/issue74-matched-32k-v1/release-001/report.json`.
After completion, use `--check`; materialization refuses to overwrite a finished
attempt. `--resume` is for an interrupted attempt without a final report. It
rechecks referenced source shards without rewriting them. Every stage reports
completed/total, elapsed time, ETA, and heartbeats. A bounded `--limit-tasks`
run cannot claim complete coverage.

The shared runner requires matching successor authorization and gate receipts
before corpus processing. Missing/incomplete predecessors yield `VALID_STOP`,
stopped predecessors yield `ANCESTOR_STOP`, and malformed or mismatched inputs
yield `INVALID`. Governed stops retain `gated-not-run`; `INVALID` is never
scientific completion. A PASS requires all selected decisions and the global
isolation audit, followed by the independent read-only check for closeout.

## Load training examples

```python
from pathlib import Path
from examples.planning_benchmark_slice.modality_corpus import ModalityCorpus

root = Path.cwd()
corpus = ModalityCorpus(
    root,
    root / "outputs/modality_corpus/issue74-matched-32k-v1/release-001/report.json",
)
record = next(corpus.records(algorithm="best_first_width", split="train"))
paired = corpus.training_example(record, modality="multimodal-state")
# paired contains messages, PIL images, and their ordered page_roles.
text = corpus.training_example(record, modality="text-state")
visual = corpus.training_example(record, modality="visual-state")
```

The loader validates completion receipts, required checks, complete task coverage,
released modalities and exact source-shard bindings. It preserves the old
`VisualCorpus` import for #73 consumers; an original #73 report still refuses
multimodal-state access. Iterate with an explicit algorithm and train/dev split;
staged ordering follows difficulty, domain, whole task, then decision index.
Do not feed authoritative record metadata directly into a model. The loader
builds the model-facing projection through the shared adapter.

## Validation and downstream handoff

Every referenced shard is independently replay-checked through FIFO BFS,
unpruned BFWS, or the corresponding additive runtime before release. All source
inputs, strictly parsed/applied targets, state/successor/page associations,
complete text/image token counts and target limits are checked. The global
audit rejects semantic/input split overlaps and conflicting identical inputs.
Because every modality projects the same complete authoritative record and
shared page semantics, their Search Memory and task/decision position agree.

The #71 semantic-validation clarification supersedes historical byte-identical
regeneration wording. No hashes, integrity machinery, or regeneration comparisons
are added; semantic replay and provenance remain required.

This report is the combined matched corpus handoff for #75/#76: all three
modalities, four algorithm settings, the approved 32K panel, and shared memory.
Those tickets still need matching model-run successor settings/authorization and
actual GPU throughput qualification. The original #71 8K phase is not silently
reactivated at 32K. This corpus PASS establishes usable supervised records, not
learned structural/process competence, training success, or evaluation results.
