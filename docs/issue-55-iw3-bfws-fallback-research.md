# Research note: IW(3) qualification and a complete BFWS fallback

**Issue context:** [#55](https://github.com/Sino-Huang/multimodality_on_planning/issues/55), with the proposed corpus qualification before the IW phase is frozen in #56.

**Scope:** Establish what full Best-First Width Search (BFWS) guarantees relative to fixed-width IW, what `BFWS-public` actually implements, and the smallest compatible fallback seam if capped IW through width 3 does not solve the governed train/test corpus.

**Status:** Implemented as the independent project-native `full_bfws_goal_count` variant described below. `BFWS-public` was inspected at commit [`d241392`](https://github.com/nirlipo/BFWS-public/tree/d2413924289c2eef4a14d57f7bbc3b275044d54f); none of its GPL source was copied or vendored.

---

## Decision summary

1. Qualify the corpus first with independent passes `IW(1)`, `IW(2)`, and `IW(3)`, resetting OPEN/CLOSED and the novelty table between widths. This is a capped IW portfolio, not complete IW: the original definition continues until the number of problem variables is exceeded, while a fixed `IW(k)` prunes novelty greater than `k` ([original IW paper, Definitions 7–8](https://nirlipo.github.io/publication/lipovetzky-2012-width/width-ecai-12.pdf); [DOI](https://doi.org/10.3233/978-1-61499-098-7-540)).
2. If a governed instance genuinely exhausts `IW(3)` without a solution, migrate the algorithm arm to **full, unpruned BFWS**, not `k-BFWS`. A timeout or expansion-budget stop is not proof that width 3 failed; record it separately and rerun under the qualification budget before changing algorithms.
3. The user's description—states above the novelty cap receive lower priority rather than being discarded—is correct for full BFWS. It is **not** correct for the `1-BFWS` and `k-BFWS` modes in the public repository, which explicitly prune above the bound ([mode list](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/README.md#L41-L60); [ICAPS 2017](https://ojs.aaai.org/index.php/ICAPS/article/view/13822)).
4. Do not vendor `BFWS-public` into this MIT repository. It is GPL-3.0-or-later C++ code and depends on LAPKT plus an FF or Fast Downward parser ([license header](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/new_node_comparer.hxx#L1-L19); [build instructions](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/README.md#L4-L27)). Prefer an independent project-native implementation from the papers if BFWS becomes a governed trace-producing arm.

## Implemented decision and qualification result

The migration criterion was met. At 500 expansions per width, the exact capped `IW(1..3)` pass covered all 4,678 train/test rows and produced 124 genuine `width_cap_exhausted` outcomes, so the arm cannot remain capped IW(3).

The replacement is `full_bfws_goal_count`, an independently written complete graph-search variant with:

```text
novelty categories = 1, 2, >2
partition = unachieved top-level goal count
OPEN priority = (novelty category, unachieved goals, path depth, generation serial)
high-novelty policy = enqueue
novelty-pruned states = 0
```

It is intentionally not called `f5`: it does not implement the relaxed-plan `#r` partition from canonical `BFWS(f5)`. Completeness comes from exhaustive successor generation, duplicate detection, and retaining the residual `>2` bucket; it does not depend on that additional partition.

The 500-expansion/5-second BFWS triage pass tested all 4,678 rows. A bounded 5,000-expansion retry recovered additional solutions before the cost boundary was reached. The resulting source-order-preserving `solved-manifest.jsonl` contains 3,186 replay-proven rows (2,905 train, 281 test). Sixteen rows (15 Snake, one VisitAll) exhaust the complete reachable frontier and are unsolvable under the parsed transition system; 1,476 remain resource-inconclusive and are excluded rather than mislabeled. Because this process inspected the former test split, it is qualification data, not a held-out efficacy split.

## 1. IW and BFWS are different uses of novelty

### Fixed-width and iterated width

For a newly generated state, ordinary IW novelty is the size of the smallest tuple of state atoms made true for the first time in the search. `IW(k)` is breadth-first graph search that rejects a generated state when this novelty is greater than `k` ([Lipovetzky and Geffner 2012, Definitions 6–7](https://nirlipo.github.io/publication/lipovetzky-2012-width/width-ecai-12.pdf)). Consequently, `IW(1)`, `IW(2)`, or `IW(3)` alone can be incomplete. The original paper proves completeness only for the unbounded iterated procedure that can reach the number of problem variables; `IW(n)` then prunes only duplicate states ([same paper, pp. 541–542](https://nirlipo.github.io/publication/lipovetzky-2012-width/width-ecai-12.pdf)).

The proposed `k_max = 3` policy should therefore be described precisely as:

```text
IW(1) -> reset -> IW(2) -> reset -> IW(3) -> solved | width_cap_exhausted
```

The terminal reason matters. `width_cap_exhausted` means OPEN became empty after novelty pruning. `expansion_limit`, `timeout`, and `memory_limit` mean qualification is inconclusive under that resource budget.

### Partitioned novelty and BFWS ordering

BFWS changes both the novelty definition and its role. Given partition functions `h1, ..., hm`, partitioned novelty `w_{h1,...,hm}(s)` is the smallest tuple true in `s` but unseen in earlier generated states having the same values of every `h_j` ([AAAI 2017, Definition 1](https://cdn.aaai.org/ojs/11027/11027-13-14555-1-2-20201228.pdf)). BFWS then orders OPEN lexicographically instead of using novelty as an acceptance test.

The paper's principal `BFWS(f5)` configuration is:

```text
priority(s) = < w_{#g,#r}(s), #g(s) >
```

Here `#g` is the number of unachieved top-level goals. `#r` counts atoms associated with the most recently computed relaxed plan that have been achieved along the path since that plan was computed. The relaxed plan is recomputed initially and when `#g` improves ([AAAI 2017, BFWS(f5)](https://cdn.aaai.org/ojs/11027/11027-13-14555-1-2-20201228.pdf)). The inspected two-heuristic implementation adds unit path depth as the final tie-breaker: novelty, goal/landmark count, then depth ([OPEN comparator](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/new_node_comparer.hxx#L77-L90)). A stable generation serial should be the project's final deterministic tie-breaker.

The public code partitions its novelty tables using goal count and relevant-fluent count ([partition calculation](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/bfws_2h.hxx#L490-L505)). If no tuple through the configured arity is new, it assigns `arity + 1` as a residual novelty bucket ([novelty computation](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/novelty_partition_1.hxx#L188-L220)).

## 2. Does BFWS retain states with novelty greater than k?

**Full BFWS does; `k-BFWS` does not.**

The distinction is explicit in both the paper and implementation:

| Mode | Treatment of high-novelty states | Completeness |
|---|---|---|
| Full `BFWS(f5)` | Enqueue in the residual bucket; novelty affects priority | Complete under the conditions in §3 |
| `k-BFWS(f)` / `1-BFWS` | Delete states with novelty greater than the bound | Incomplete; polynomial under the paper's stated bounded-partition assumptions |
| `DUAL-BFWS` | Try pruned `1-BFWS`, then run an unpruned BFWS back-end if needed | Complete because of the back-end, absent resource cutoffs |

The ICAPS 2017 paper calls `BFWS(f5)` complete but not polynomial and calls the novelty-pruned versions incomplete but polynomial ([official paper](https://ojs.aaai.org/index.php/ICAPS/article/download/13822/13671)). In code, `BFWS_2H` defaults `m_use_novelty_pruning` to false ([constructor](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/bfws_2h.hxx#L209-L214)); excessive novelty causes deletion only inside the optional pruning branch, after which all retained nodes are inserted into OPEN ([successor processing](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/bfws_2h.hxx#L610-L630)). Direct `BFWS-f5` does not enable that branch, whereas `k-BFWS` does ([mode setup](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/fd-version/src/bfws.cxx#L266-L304)).

This also prevents a configuration trap: the FD wrapper named `bfws.py` selects the DUAL portfolio, while `bfws_f5.py` selects direct f5 ([DUAL wrapper](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/fd-version/bfws.py#L24-L36); [f5 wrapper](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/fd-version/bfws_f5.py#L24-L36)). A governed implementation must name and freeze the exact mode rather than record only `bfws`.

### Novelty precision is not an IW pruning width

`BFWS-public` computes only tuples of sizes 1 and 2. Both included novelty-table types terminate the process when configured with arity above 2 ([first table](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/novelty_partition_1.hxx#L91-L99); [second table](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/novelty_partition_2.hxx#L91-L99)). Its usual three values are therefore `1`, `2`, and `>2`, not exact novelty 3. It can also silently downgrade arity 2 to 1 when its estimated table exceeds the built-in memory allowance ([memory branch](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/novelty_partition_1.hxx#L102-L109)).

Completeness does not require exact triple novelty: the residual `>2` states remain in OPEN. If this project wants continuity with the governed IW cap, a clean implementation may freeze precision 3 and assign no-new-triple states to bucket 4 (`>3`), but that is a project BFWS configuration—not behavior supplied by `BFWS-public`.

## 3. Completeness in this project's planning model

The papers work with a finite state model and deterministic actions ([original IW planning model](https://nirlipo.github.io/publication/lipovetzky-2012-width/width-ecai-12.pdf)). In that setting, full BFWS is a standard best-first graph search. Its completeness claim requires:

- a finite reachable state space and finite applicable-action set;
- deterministic, total successor application for every applicable action;
- generation of **all** applicable successors (helpful actions may affect priority but cannot be an exclusive filter);
- sound duplicate detection, with at least one representative of each reachable state;
- no novelty rejection, including for the residual `>k` bucket;
- no unsound heuristic dead-end filter; and
- enough time and memory, with no binding depth, cost, or expansion cutoff.

Under these conditions, a finite OPEN list cannot starve a retained reachable state forever: BFWS either selects a reachable goal or exhausts every reachable state. This is a satisficing completeness guarantee, not an optimality guarantee. The public search loop pops OPEN through goal discovery or exhaustion and uses CLOSED duplicate handling ([search loop](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/bfws_2h.hxx#L637-L672)).

An experimental run with a timeout or expansion cap remains resource-bounded and may fail to find an existing plan. The evidence must therefore say `resource_limit`, not `unsolvable`, and must not claim that operational BFWS is complete under the frozen budget.

## 4. Implementation, dependency, and license implications

`BFWS-public` is not a drop-in Python package. Its documented build requires LAPKT, `LAPKT_PATH`, SCons, C++, and either the FF or Fast Downward parser ([README](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/README.md#L4-L27)). The FD build script deletes and recopies its parser directory from the selected LAPKT checkout before invoking SCons ([build script](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/fd-version/build.py#L5-L27)). The public repository does not pin the required LAPKT revision, so compatibility with current LAPKT must be demonstrated rather than assumed.

The BFWS source is GPL-3.0-or-later ([source header](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/src/bfws_2h.hxx#L1-L19); [repository license](https://github.com/nirlipo/BFWS-public/blob/d2413924289c2eef4a14d57f7bbc3b275044d54f/LICENSE)). This project is MIT. MIT is GPL-compatible, but copying or linking the BFWS implementation into a conveyed combined program would bring GPL conditions for the combined work; the GPL separately recognizes mere aggregates ([GPLv3 §5](https://www.gnu.org/licenses/gpl-3.0.en.html#section5); [GNU GPL FAQ on combining code](https://www.gnu.org/licenses/gpl-faq.en.html)). This is a provenance warning, not legal advice.

Two integration paths are materially different:

- **Qualification oracle:** invoke a separately installed, pinned GPL executable via PDDL/plan files and independently replay its returned plan. This keeps source out of the repository, but it does not provide the typed decision trace needed for process supervision or independent BFWS-invariant replay.
- **Governed algorithm arm:** implement BFWS independently from the published definitions using the existing PDDL authority and typed search-memory operations. Do not translate, copy, or adapt the GPL source. This is the recommended path if BFWS replaces IW in training and evaluation.

## 5. Minimal governed adapter if IW(3) qualification fails

The smallest project-native migration should preserve the Search Episode Harness boundary and replace only policy/search semantics:

1. Add an exact algorithm identifier and frozen configuration: `best_first_width` with `variant = full_bfws_goal_count`, `novelty_precision = 2`, `high_novelty_policy = enqueue`, `recovery_policy = prohibited`, and the exact priority/tie-break rule.
2. Reuse `PDDLStateAuthority` for canonical states, applicable actions, and deterministic transition previews. Reuse `SearchTransitionRequest`, `SearchRetireRequest`, and `SearchMemory` for typed mutations and provenance.
3. Add BFWS-owned search state for novelty tables partitioned by `#g`, path depth, and a monotonic generation serial. The existing single `StateEvaluation(novelty, heuristic)` carries novelty and `#g`.
4. Maintain OPEN in ascending deterministic order:

   ```text
   (novelty_bucket, unachieved_goal_count, path_depth, generation_serial)
   ```

   Novelty is computed within the `#g` partition. A state with no new tuple of size 1 or 2 receives bucket 3 (`>2`) and is still enqueued. CLOSED-state duplicates may be rejected; novelty alone may never reject a state.
5. Emit model-facing evidence for the selected OPEN head, every applicable successor, its partition, first novel tuple or residual bucket, full priority key, duplicate/dead-end verdict, insertion position, and `enqueued = true` for every nonduplicate high-novelty state.
6. Independently replay each episode from PDDL, recomputing partitioned novelty, all priority keys, OPEN order, transitions, duplicate handling, and the invariant `high_novelty => not novelty_pruned`. Do not trust the executor's stored verdicts.
7. Add a finite solvable regression fixture whose only solution passes through a residual-bucket state. The test must prove that IW(3) exhausts after pruning it while BFWS retains, eventually expands, and reaches the goal. Also test full-corpus classification into solved, width-cap-exhausted, and resource-limit outcomes.

The external executable can be useful as a cross-check during development, but plan replay alone cannot certify that the project implementation followed BFWS ordering or retained every high-novelty state.

## 6. Qualification gate before migration

The corpus report should contain one row per immutable instance and split, with at least:

- instance/source hash and split;
- width sequence attempted and per-width reset evidence;
- per-width generated, expanded, novelty-pruned, duplicate, and peak-frontier counts;
- solving width and replay-valid plan, when solved;
- exact terminal reason (`goal`, `width_cap_exhausted`, `expansion_limit`, `timeout`, `memory_limit`, or invalid evidence);
- fixed implementation/config/environment hashes; and
- an aggregate table by split and difficulty stratum.

Migration is justified by at least one replay-valid finite instance that reaches `width_cap_exhausted` at width 3 under the frozen exact IW implementation. A resource stop justifies revisiting the qualification budget; it does not by itself establish the need for BFWS. If BFWS is adopted, re-run the same immutable instance panel and require replay-valid plans plus the non-pruning invariant before freezing the replacement arm.

## Primary sources

- Lipovetzky and Geffner, “Width and Serialization of Classical Planning Problems,” ECAI 2012: [author PDF](https://nirlipo.github.io/publication/lipovetzky-2012-width/width-ecai-12.pdf), [DOI](https://doi.org/10.3233/978-1-61499-098-7-540).
- Lipovetzky and Geffner, “Best-First Width Search: Exploration and Exploitation in Classical Planning,” AAAI 2017: [official PDF](https://cdn.aaai.org/ojs/11027/11027-13-14555-1-2-20201228.pdf), [DOI](https://doi.org/10.1609/aaai.v31i1.11027).
- Lipovetzky and Geffner, “A Polynomial Planning Algorithm That Beats LAMA and FF,” ICAPS 2017: [official page](https://ojs.aaai.org/index.php/ICAPS/article/view/13822), [DOI](https://doi.org/10.1609/icaps.v27i1.13822).
- Lipovetzky and Geffner, [`BFWS-public` at inspected commit](https://github.com/nirlipo/BFWS-public/tree/d2413924289c2eef4a14d57f7bbc3b275044d54f).
