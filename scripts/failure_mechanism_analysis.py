#!/usr/bin/env python3
"""Failure-mechanism calibration analysis from replayed episodes (#125).

CPU-only: no model calls and no CUDA. Mines only the existing, independently
replay-verified episode evidence named in #125 — the expanded matched baseline
matrix (#118), generalization-robustness v2 (#124), the DAgger comparison
(#84), successor prediction (#89/#99) and curriculum evaluation (#119) — and
publishes a first-failure matrix localizing where and how the learned and base
policies fail: by algorithm family, modality arm, horizon position
(first-failure step distribution), operation type, and frontier/branching
difficulty as recoverable from logged state features.

The analysis protocol (failure taxonomy, grouping keys, tiny-strata limits) is
frozen in configs/experiments/expanded-study/failure-mechanism-protocol.json
(committed before any outcome computation); this script loads that frozen
artifact and follows it exactly. Add `--check` for read-only regeneration and
byte-comparison of every published output.
"""

import argparse
import csv
import gzip
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/experiments/expanded-study"
V1 = ROOT / "outputs/expanded-study/v1"
V5_EVAL = ROOT / "outputs/matched_modalities/v5/evaluation"
PROTOCOL_PATH = ROOT / "configs/experiments/expanded-study/failure-mechanism-protocol.json"
PROTOCOL = json.loads(PROTOCOL_PATH.read_text())

MATRIX_SCHEMA = "expanded_failure_mechanism_matrix_v1"
MATRIX_PATH = DOCS / "failure-mechanism-matrix.json"
TABLES_DIR = DOCS / "failure-mechanism-tables"
DOC_PATH = DOCS / "failure-mechanism-analysis.md"

MODALITIES = ["text-state", "visual-state", "multimodal-state"]
DEV_TASKS = ["blocksworld-730060", "ferry-780004", "storage-760000"]
COMPARATOR_ARMS = ["process_sft", "random_valid", "exact_reference"]

BRANCH_ISSUES = {
    "expanded_baseline": "#118",
    "generalization_robustness_v2": "#124",
    "dagger": "#84",
    "successor_prediction": "#89/#99",
    "curriculum_modality": "#119",
}

HORIZON_BUCKETS = PROTOCOL["grouping_keys"]["horizon_buckets"]
FRONTIER_BUCKETS = PROTOCOL["grouping_keys"]["frontier_size_buckets"]
BRANCHING_BUCKETS = PROTOCOL["grouping_keys"]["branching_factor_buckets"]
TINY_LIMIT = PROTOCOL["tiny_strata_rule"]["min_stratum_episodes"]

ARM_CLASS = {}
for cls, arms in PROTOCOL["arm_classification"].items():
    if cls == "notes":
        continue
    for arm in arms:
        ARM_CLASS[arm] = cls

# ---------------------------------------------------------------------------
# Episode enumeration under the frozen fixed-input rules
# ---------------------------------------------------------------------------


def _is_view(path: Path) -> bool:
    s = str(path)
    return "-views" in s or "/views/" in s or s.endswith("/views")


def _glob_store(base: Path):
    return sorted(p for p in base.rglob("*.json.gz") if not _is_view(p))


def enumerate_episodes():
    """Yield (path, store_key, branches) honoring dedup by repository-relative path."""
    membership = defaultdict(set)
    store_of = {}

    def add(path: Path, store_key: str, branch: str):
        rel = path.relative_to(ROOT).as_posix()
        membership[rel].add(branch)
        store_of.setdefault(rel, store_key)

    for p in _glob_store(V1 / "baseline/episodes"):
        add(p, "baseline", "expanded_baseline")
        # DAgger unseen-panel comparators: bfs x the three non-base arms.
        parts = p.name[: -len(".json.gz")].split("-")
        arm = parts[-1]
        algo = "-".join(parts[:-1])
        if algo == "bfs" and arm in COMPARATOR_ARMS:
            membership[p.relative_to(ROOT).as_posix()].add("dagger")

    for p in _glob_store(V1 / "generalization-robustness/episodes"):
        add(p, "genrob", "generalization_robustness_v2")

    for p in _glob_store(V1 / "dagger/evaluation"):
        add(p, "dagger_new", "dagger")

    for p in _glob_store(V1 / "successor/evaluation/episodes"):
        add(p, "successor", "successor_prediction")

    for p in _glob_store(V1 / "curriculum/evaluation"):
        add(p, "curriculum_new", "curriculum_modality")

    # DAgger development-panel comparators: v5 bfs episodes for the 3 dev tasks.
    for modality in MODALITIES:
        for task in DEV_TASKS:
            for arm in COMPARATOR_ARMS:
                p = V5_EVAL / modality / f"matched-final__{task}" / f"bfs-{arm}.json.gz"
                if not p.exists():
                    raise FileNotFoundError(f"missing dagger development comparator: {p}")
                add(p, "v5", "dagger")

    # Curriculum comparators: the 324 provenance-listed bindings (288 baseline + 36 v5).
    cur_evidence = json.loads((DOCS / "curriculum-evaluation.json").read_text())
    for src in cur_evidence["comparator_provenance"]["sources"]:
        p = ROOT / src
        if not p.exists():
            raise FileNotFoundError(f"missing curriculum comparator: {p}")
        store_key = "baseline" if "/v1/baseline/" in src else "v5"
        add(p, store_key, "curriculum_modality")

    return sorted(membership), membership, store_of


# ---------------------------------------------------------------------------
# Per-event schema helpers and feature extraction
# ---------------------------------------------------------------------------


def _event_schema(event_input: dict) -> str:
    if "current" in event_input:
        return "best_first"
    obs = event_input.get("observation")
    if isinstance(obs, dict):
        if "state" in obs:
            return "width"
        if "state_id" in obs:
            return "bfs"
    return "unknown"


def _features(event_input: dict) -> dict:
    sm = event_input.get("search_memory", {})
    if "current" in event_input:
        return {
            "frontier_size": sm.get("frontier_count"),
            "branching_factor": len(event_input.get("successor_candidates", {}).get("rows", [])),
            "visited_count": sm.get("visited_count"),
            "current_g": event_input["current"].get("g"),
            "current_h": event_input["current"].get("h"),
        }
    obs = event_input.get("observation", {})
    if isinstance(obs, dict) and "state" in obs:
        return {
            "frontier_size": sm.get("open"),
            "branching_factor": len(obs.get("candidates", [])),
            "visited_count": sm.get("visited"),
            "current_g": None,
            "current_h": None,
        }
    return {
        "frontier_size": sm.get("frontier_size", obs.get("frontier_size")),
        "branching_factor": len(sm.get("successor_candidates", [])),
        "visited_count": sm.get("known_state_count"),
        "current_g": None,
        "current_h": None,
    }


def _episode_candidate_names(events, schema: str) -> set:
    names = set()
    for e in events:
        inp = e.get("input") or e.get("bfs_input") or {}
        if schema == "best_first":
            for row in inp.get("successor_candidates", {}).get("rows", []):
                if row and row[0]:
                    names.add(row[0][0])
        elif schema == "bfs":
            for cand in inp.get("search_memory", {}).get("successor_candidates", []):
                ga = cand.get("grounded_action", {})
                if isinstance(ga.get("name"), str):
                    names.add(ga["name"])
        elif schema == "width":
            for cand in (inp.get("observation") or {}).get("candidates", []):
                act = cand.get("action", {})
                if isinstance(act.get("name"), str):
                    names.add(act["name"])
    return names


def _failure_record(step, kind, operation_type, feats, raw_output):
    rec = {
        "first_failure_step": step,
        "failure_kind": kind,
        "operation_type": operation_type,
        "frontier_size": feats.get("frontier_size"),
        "branching_factor": feats.get("branching_factor"),
        "visited_count": feats.get("visited_count"),
        "current_g": feats.get("current_g"),
        "current_h": feats.get("current_h"),
        "raw_failing_output": raw_output,
    }
    return rec


def classify_search_episode(ep: dict) -> dict | None:
    """Return a failure record, or None when the episode reached the goal."""
    result = ep["result"]
    if result.get("termination_reason") == "goal_reached":
        return None
    events = ep["events"]
    fail = next((e for e in events if not e.get("accepted", True)), None)
    if fail is None:
        if result.get("termination_reason") == "expansion_budget_exhausted":
            feats = _features(events[-1]["input"]) if events else {}
            return _failure_record(
                result.get("decision_count"), "expansion_budget_exhausted", None, feats, None
            )
        return _failure_record(None, "unclassified", None, {}, None)

    step = fail["index"]
    inp = fail["input"]
    feats = _features(inp)
    raw = fail.get("raw_output")
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("not an object")
    except Exception:
        return _failure_record(step, "malformed_output", None, feats, raw)

    schema = _event_schema(inp)
    if schema == "best_first":
        act = obj.get("action")
        src = obj.get("source_state_id")
        if not isinstance(act, dict) or not isinstance(act.get("name"), str) or src is None:
            return _failure_record(step, "malformed_output", None, feats, raw)
        name, args = act["name"], act.get("args", [])
        if src != inp["current"]["state_id"]:
            return _failure_record(step, "source_state_mismatch", name, feats, raw)
        cand = {tuple(r[0]) for r in inp["successor_candidates"]["rows"] if r and r[0]}
        if name not in _episode_candidate_names(events, "best_first"):
            return _failure_record(step, "unknown_operator", name, feats, raw)
        if (name, *args) not in cand:
            return _failure_record(step, "inapplicable_grounded_action", name, feats, raw)
        return _failure_record(step, "other_invariant_violation", name, feats, raw)

    if schema in ("bfs", "width"):
        t = obj.get("typed_operation")
        if not isinstance(t, dict):
            return _failure_record(step, "malformed_output", None, feats, raw)
        if "action" not in t:
            ot = t.get("operation_type")
            if isinstance(ot, str) and "state_id" in t:
                return _failure_record(
                    step, "invalid_frontier_operation", f"frontier:{ot}", feats, raw
                )
            return _failure_record(step, "malformed_output", None, feats, raw)
        act = t["action"]
        required = ("source_state_id", "frontier_intent", "visit_target", "evaluate_target")
        if (
            not isinstance(act, dict)
            or not isinstance(act.get("name"), str)
            or any(k not in t for k in required)
        ):
            return _failure_record(step, "malformed_output", None, feats, raw)
        name, args = act["name"], act.get("args", [])
        if schema == "bfs":
            current_id = inp["observation"]["state_id"]
            cand = {
                (
                    c.get("grounded_action", {}).get("name"),
                    *c.get("grounded_action", {}).get("args", []),
                )
                for c in inp["search_memory"].get("successor_candidates", [])
            }
        else:
            current_id = inp["observation"]["state"]["state_id"]
            objects = inp.get("task_context", {}).get("objects", [])
            cand = set()
            for c in inp["observation"].get("candidates", []):
                ca = c.get("action", {})
                decoded = tuple(
                    objects[a] if isinstance(a, int) and 0 <= a < len(objects) else a
                    for a in ca.get("args", [])
                )
                if isinstance(ca.get("name"), str):
                    cand.add((ca["name"], *decoded))
        if t.get("source_state_id") != current_id:
            return _failure_record(step, "source_state_mismatch", name, feats, raw)
        if name not in _episode_candidate_names(events, schema):
            return _failure_record(step, "unknown_operator", name, feats, raw)
        if (name, *args) not in cand:
            return _failure_record(step, "inapplicable_grounded_action", name, feats, raw)
        return _failure_record(step, "other_invariant_violation", name, feats, raw)

    return _failure_record(step, "unclassified", None, feats, raw)


def classify_successor_episode(ep: dict) -> dict | None:
    result = ep["result"]
    if result.get("termination_reason") == "goal_reached":
        return None
    events = ep["events"]
    fail = next((e for e in events if not e.get("accepted", True)), None)
    if fail is None:
        return _failure_record(None, "unclassified", None, {}, None)
    verification = fail.get("verification", {})
    kind = verification.get("failure_kind") or "unclassified"
    sm = fail.get("bfs_input", {}).get("search_memory", {})
    feats = {
        "frontier_size": sm.get("frontier_size"),
        "branching_factor": len(sm.get("successor_candidates", [])),
        "visited_count": sm.get("known_state_count"),
        "current_g": None,
        "current_h": None,
    }
    action = fail.get("action") or {}
    return _failure_record(
        fail.get("index"), kind, action.get("name"), feats, fail.get("raw_prediction")
    )


# ---------------------------------------------------------------------------
# Bucketing helpers (frozen bucket lists from the protocol)
# ---------------------------------------------------------------------------


def _bucket(value, buckets):
    if value is None:
        return "unknown"
    for b in buckets:
        if b.endswith("+"):
            if value >= int(b[:-1].split("-")[-1]):
                return b
        elif "-" in b:
            lo, hi = b.split("-")
            if int(lo) <= value <= int(hi):
                return b
        elif value == int(b):
            return b
    return "unknown"


def horizon_bucket(step):
    return _bucket(step, HORIZON_BUCKETS)


def frontier_bucket(size):
    return _bucket(size, FRONTIER_BUCKETS)


def branching_factor_bucket(n):
    return _bucket(n, BRANCHING_BUCKETS)


# ---------------------------------------------------------------------------
# Mining
# ---------------------------------------------------------------------------


def load_all_episodes():
    paths, membership, store_of = enumerate_episodes()
    episodes = []
    digests = defaultdict(list)
    for rel in paths:
        p = ROOT / rel
        raw = p.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        ep = json.loads(gzip.decompress(raw))
        store_key = store_of[rel]
        digests[store_key].append((rel, digest))
        episodes.append(
            {
                "path": rel,
                "store_key": store_key,
                "branches": sorted(membership[rel]),
                "data": ep,
            }
        )
    return episodes, digests


def mine():
    episodes, digests = load_all_episodes()

    # exact_reference decision counts per (store, task, algorithm, modality)
    ref_decisions = {}
    for rec in episodes:
        ep = rec["data"]
        if ep.get("arm") == "exact_reference":
            key = (rec["store_key"], ep["task_id"], ep["algorithm"], ep["modality"])
            ref_decisions[key] = ep["result"]["decision_count"]

    ref_store_for = {"baseline": "baseline", "v5": "v5", "genrob": "genrob"}

    failures = []
    coverage_counts = Counter()
    failure_counts = Counter()
    unclassified = 0
    missing_reference = 0
    for rec in episodes:
        ep = rec["data"]
        store_key = rec["store_key"]
        for branch in rec["branches"]:
            coverage_counts[branch] += 1
        is_successor = ep.get("schema_version") == "expanded_successor_evaluation_episode_v1"
        fail = (
            classify_successor_episode(ep)
            if is_successor
            else classify_search_episode(ep)
        )
        for branch in rec["branches"]:
            if fail is not None:
                failure_counts[branch] += 1
        if fail is None:
            continue
        if fail["failure_kind"] == "unclassified":
            unclassified += 1
        # reference decisions for the horizon ratio
        ref = None
        if is_successor:
            ref = ep.get("reference_decisions")
        else:
            if store_key in ("dagger_new", "curriculum_new"):
                panel = ep.get("panel")
                ref_store = "baseline" if panel == "unseen" else "v5"
            else:
                ref_store = ref_store_for.get(store_key)
            if ref_store:
                ref = ref_decisions.get(
                    (ref_store, ep["task_id"], ep["algorithm"], ep["modality"])
                )
        step = fail["first_failure_step"]
        if ref in (None, 0):
            missing_reference += 1
            ratio = None
        else:
            ratio = step / ref if step is not None else None
        arm = ep.get("arm")
        record = {
            "path": rec["path"],
            "store_key": store_key,
            "branches": rec["branches"],
            "task_id": ep.get("task_id"),
            "panel": ep.get("panel", ep.get("panel_id")),
            "family": ep.get("family"),
            "modality": ep.get("modality"),
            "algorithm": ep.get("algorithm"),
            "arm": arm,
            "arm_class": ARM_CLASS.get(arm, "unknown"),
            "curriculum_ordering": arm.split("__", 1)[1] if arm and "__" in arm else None,
            "seed": ep.get("seed"),
            "termination_reason": ep["result"].get("termination_reason"),
            "decision_count": ep["result"].get("decision_count"),
            "expansion_count": ep["result"].get("expansion_count"),
            "invalid_operation_count": ep["result"].get("invalid_operation_count"),
            "reference_decisions": ref,
            "horizon_ratio": ratio,
        }
        record.update(fail)
        failures.append(record)

    failures.sort(key=lambda r: r["path"])

    manifest = {}
    for store_key, items in sorted(digests.items()):
        h = hashlib.sha256()
        for rel, digest in sorted(items):
            h.update(rel.encode())
            h.update(digest.encode())
        manifest[store_key] = {"files": len(items), "sha256": h.hexdigest()}

    return {
        "episodes": episodes,
        "failures": failures,
        "manifest": manifest,
        "coverage_counts": coverage_counts,
        "failure_counts": failure_counts,
        "unclassified": unclassified,
        "missing_reference": missing_reference,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _arm_label(rec):
    return rec["arm"]


def _branch_panel(store_key: str, ep: dict, branch: str) -> str:
    if branch in ("expanded_baseline", "generalization_robustness_v2"):
        return "final"
    if store_key == "baseline":
        return "unseen"
    if store_key == "v5":
        return "development"
    return ep.get("panel", "unknown")


def aggregate(mined):
    episodes = mined["episodes"]
    failures = mined["failures"]

    # Denominators: episodes per (algorithm, modality, arm) and per (arm_class, algorithm)
    denom_cell = Counter()
    denom_algo = Counter()
    denom_mod_arm = Counter()
    denom_store_cell = Counter()
    panel_denom = Counter()
    for rec in episodes:
        ep = rec["data"]
        arm = ep.get("arm")
        denom_cell[(ep.get("algorithm"), ep.get("modality"), arm)] += 1
        denom_algo[(ARM_CLASS.get(arm, "unknown"), ep.get("algorithm"))] += 1
        denom_mod_arm[(ep.get("modality"), ARM_CLASS.get(arm, "unknown"))] += 1
        denom_store_cell[(rec["store_key"], ep.get("algorithm"), arm)] += 1
        for branch in rec["branches"]:
            panel_denom[
                (branch, _branch_panel(rec["store_key"], ep, branch), ep.get("modality"), arm)
            ] += 1

    cell_failures = Counter()
    store_cell_failures = Counter()
    panel_failures = Counter()
    for f in failures:
        cell_failures[(f["algorithm"], f["modality"], f["arm"], f["failure_kind"])] += 1
        for branch in f["branches"]:
            panel = _branch_panel(f["store_key"], {"panel": f["panel"]}, branch)
            panel_failures[(branch, panel, f["modality"], f["arm"])] += 1
        store_cell_failures[(f["store_key"], f["algorithm"], f["arm"])] += 1

    kind_by_armclass = Counter()
    horizon = Counter()
    horizon_ratio = defaultdict(list)
    op_type = Counter()
    difficulty = Counter()
    gh_at_failure = defaultdict(list)
    mod_arm_fail = Counter()
    for f in failures:
        ac = f["arm_class"]
        kind_by_armclass[(ac, f["failure_kind"])] += 1
        horizon[(ac, f["algorithm"], horizon_bucket(f["first_failure_step"]))] += 1
        if f["horizon_ratio"] is not None:
            horizon_ratio[(ac, f["algorithm"])].append(f["horizon_ratio"])
        if f["operation_type"] is not None:
            op_type[(ac, f["operation_type"])] += 1
        difficulty[(ac, frontier_bucket(f["frontier_size"]), branching_factor_bucket(f["branching_factor"]))] += 1
        mod_arm_fail[(f["modality"], ac)] += 1
        if f["current_g"] is not None and f["current_h"] is not None:
            gh_at_failure[ac].append((f["current_g"], f["current_h"]))

    return {
        "denom_cell": denom_cell,
        "denom_algo": denom_algo,
        "denom_mod_arm": denom_mod_arm,
        "denom_store_cell": denom_store_cell,
        "store_cell_failures": store_cell_failures,
        "panel_denom": panel_denom,
        "panel_failures": panel_failures,
        "cell_failures": cell_failures,
        "kind_by_armclass": kind_by_armclass,
        "horizon": horizon,
        "horizon_ratio": horizon_ratio,
        "op_type": op_type,
        "difficulty": difficulty,
        "gh_at_failure": gh_at_failure,
        "mod_arm_fail": mod_arm_fail,
    }



# ---------------------------------------------------------------------------
# Anchor verification (machine-checkable replay anchors)
# ---------------------------------------------------------------------------


def verify_anchors():
    checks = []

    def _load(path):
        return json.loads((ROOT / path).read_text())

    base = _load("docs/experiments/expanded-study/baseline-evaluation.json")
    checks.append(
        {
            "check": "baseline evaluation PASS with 1,152 bindings",
            "pass": base["outcome"] == "PASS" and base["logical_bindings"] == 1152,
        }
    )
    replay = _load("docs/experiments/expanded-study/baseline-independent-replay.json")
    checks.append(
        {
            "check": "baseline independent replay 1,152/1,152",
            "pass": replay["outcome"] == "PASS" and replay["episodes_replayed"] == 1152,
        }
    )
    genrob = _load("outputs/expanded-study/v1/generalization-robustness/evaluation.json")
    checks.append(
        {
            "check": "generalization v2 evaluation PASS with 1,200/1,200 replayed",
            "pass": genrob["outcome"] == "PASS" and genrob["episodes_replayed"] == 1200,
        }
    )
    dagger = _load("docs/experiments/expanded-study/dagger-comparison.json")
    checks.append(
        {
            "check": "dagger comparison PASS with 405 episodes replayed",
            "pass": dagger["outcome"] == "PASS"
            and dagger["coverage"]["episodes_replayed"] == 405
            and dagger["coverage"]["missing_episodes"] == 0,
        }
    )
    successor = _load("docs/experiments/expanded-study/successor-evaluation.json")
    checks.append(
        {
            "check": "successor evaluation PASS with 90/90 replayed",
            "pass": successor["outcome"] == "PASS" and successor["episodes_replayed"] == 90,
        }
    )
    curriculum = _load("docs/experiments/expanded-study/curriculum-evaluation.json")
    checks.append(
        {
            "check": "curriculum evaluation PASS with 243 model + 324 comparator bindings",
            "pass": curriculum["outcome"] == "PASS"
            and curriculum["coverage"]["model_episodes"] == 243
            and curriculum["coverage"]["comparator_bindings"] == 324
            and not curriculum["coverage"]["missing_bindings"],
        }
    )
    return checks


# ---------------------------------------------------------------------------
# Rendering: matrix JSON, CSV tables, analysis document
# ---------------------------------------------------------------------------


def render_matrix(mined, agg, anchors):
    failures = mined["failures"]
    coverage = []
    expected = {
        "expanded_baseline": 1152,
        "generalization_robustness_v2": 1200,
        "dagger": 405,
        "successor_prediction": 90,
        "curriculum_modality": 567,
    }
    for branch in [
        "expanded_baseline",
        "generalization_robustness_v2",
        "dagger",
        "successor_prediction",
        "curriculum_modality",
    ]:
        consumed = mined["coverage_counts"][branch]
        coverage.append(
            {
                "branch": branch,
                "issue": BRANCH_ISSUES[branch],
                "expected_episodes": expected[branch],
                "episodes_consumed": consumed,
                "missing_episodes": expected[branch] - consumed,
                "failed_episodes": mined["failure_counts"][branch],
                "succeeded_episodes": consumed - mined["failure_counts"][branch],
            }
        )

    cells = []
    for (algo, modality, arm, kind), n in sorted(agg["cell_failures"].items(), key=str):
        denom = agg["denom_cell"][(algo, modality, arm)]
        cells.append(
            {
                "algorithm_family": algo,
                "modality": modality,
                "arm": arm,
                "arm_class": ARM_CLASS.get(arm, "unknown"),
                "failure_kind": kind,
                "failures": n,
                "stratum_episodes": denom,
                "descriptive_only": denom < TINY_LIMIT,
            }
        )

    branch_panel = []
    for (branch, panel, modality, arm), denom in sorted(agg["panel_denom"].items(), key=str):
        branch_panel.append(
            {
                "branch": branch,
                "panel": panel,
                "modality": modality,
                "arm": arm,
                "arm_class": ARM_CLASS.get(arm, "unknown"),
                "episodes": denom,
                "failures": agg["panel_failures"].get((branch, panel, modality, arm), 0),
                "descriptive_only": denom < TINY_LIMIT,
            }
        )

    horizon = [
        {"arm_class": ac, "algorithm_family": algo, "horizon_bucket": b, "failures": n}
        for (ac, algo, b), n in sorted(agg["horizon"].items(), key=str)
    ]
    horizon_ratio_summary = []
    for (ac, algo), ratios in sorted(agg["horizon_ratio"].items(), key=str):
        horizon_ratio_summary.append(
            {
                "arm_class": ac,
                "algorithm_family": algo,
                "failures_with_reference": len(ratios),
                "horizon_ratio_mean": statistics.fmean(ratios),
                "horizon_ratio_median": statistics.median(ratios),
                "horizon_ratio_min": min(ratios),
                "horizon_ratio_max": max(ratios),
            }
        )
    op_types = [
        {"arm_class": ac, "operation_type": ot, "failures": n}
        for (ac, ot), n in sorted(agg["op_type"].items(), key=str)
    ]
    difficulty = [
        {"arm_class": ac, "frontier_size_bucket": fb, "branching_factor_bucket": bb, "failures": n}
        for (ac, fb, bb), n in sorted(agg["difficulty"].items(), key=str)
    ]

    return {
        "schema_version": MATRIX_SCHEMA,
        "protocol_id": PROTOCOL["protocol_id"],
        "issue": 125,
        "parent_issue": 38,
        "frozen_protocol": {
            "path": "configs/experiments/expanded-study/failure-mechanism-protocol.json",
            "sha256": hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest(),
        },
        "generated_by": "scripts/failure_mechanism_analysis.py",
        "input_manifest": mined["manifest"],
        "anchor_checks": anchors,
        "coverage": coverage,
        "episodes_consumed_unique": len(mined["episodes"]),
        "failures_total": len(failures),
        "unclassified_failures": mined["unclassified"],
        "failures_missing_reference": mined["missing_reference"],
        "tiny_strata_min_episodes": TINY_LIMIT,
        "cells": cells,
        "branch_panel": branch_panel,
        "horizon_distribution": horizon,
        "horizon_ratio_summary": horizon_ratio_summary,
        "operation_type_frequency": op_types,
        "difficulty_at_failure": difficulty,
        "failures": failures,
    }


def _write_csv(rows, fieldnames):
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def render_tables(matrix):
    tables = {}
    tables["coverage-by-branch.csv"] = _write_csv(
        matrix["coverage"],
        [
            "branch",
            "issue",
            "expected_episodes",
            "episodes_consumed",
            "missing_episodes",
            "failed_episodes",
            "succeeded_episodes",
        ],
    )
    tables["failures-by-cell.csv"] = _write_csv(
        matrix["cells"],
        [
            "algorithm_family",
            "modality",
            "arm",
            "arm_class",
            "failure_kind",
            "failures",
            "stratum_episodes",
            "descriptive_only",
        ],
    )
    tables["failures-by-branch-panel.csv"] = _write_csv(
        matrix["branch_panel"],
        [
            "branch",
            "panel",
            "modality",
            "arm",
            "arm_class",
            "episodes",
            "failures",
            "descriptive_only",
        ],
    )
    tables["horizon-distribution.csv"] = _write_csv(
        matrix["horizon_distribution"],
        ["arm_class", "algorithm_family", "horizon_bucket", "failures"],
    )
    tables["horizon-ratio-summary.csv"] = _write_csv(
        matrix["horizon_ratio_summary"],
        [
            "arm_class",
            "algorithm_family",
            "failures_with_reference",
            "horizon_ratio_mean",
            "horizon_ratio_median",
            "horizon_ratio_min",
            "horizon_ratio_max",
        ],
    )
    tables["operation-type-frequency.csv"] = _write_csv(
        matrix["operation_type_frequency"],
        ["arm_class", "operation_type", "failures"],
    )
    tables["difficulty-at-failure.csv"] = _write_csv(
        matrix["difficulty_at_failure"],
        ["arm_class", "frontier_size_bucket", "branching_factor_bucket", "failures"],
    )
    tiny = [
        {
            "stratum_scope": "algorithm_family x modality x arm",
            "branch": "",
            "panel": "",
            "algorithm_family": c["algorithm_family"],
            "modality": c["modality"],
            "arm": c["arm"],
            "failure_kind": c["failure_kind"],
            "failures": c["failures"],
            "stratum_episodes": c["stratum_episodes"],
        }
        for c in matrix["cells"]
        if c["descriptive_only"]
    ]
    tiny += [
        {
            "stratum_scope": "branch x panel x modality x arm",
            "branch": p["branch"],
            "panel": p["panel"],
            "algorithm_family": "",
            "modality": p["modality"],
            "arm": p["arm"],
            "failure_kind": "",
            "failures": p["failures"],
            "stratum_episodes": p["episodes"],
        }
        for p in matrix["branch_panel"]
        if p["descriptive_only"]
    ]
    tables["tiny-strata.csv"] = _write_csv(
        tiny,
        [
            "stratum_scope",
            "branch",
            "panel",
            "algorithm_family",
            "modality",
            "arm",
            "failure_kind",
            "failures",
            "stratum_episodes",
        ],
    )
    return tables


# ---------------------------------------------------------------------------
# Analysis document
# ---------------------------------------------------------------------------


def _md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def render_document(matrix, agg, mined):
    cov = matrix["coverage"]
    failures = matrix["failures"]
    by_arm_class = Counter(f["arm_class"] for f in failures)
    base_fail = [f for f in failures if f["arm_class"] == "base"]
    learned_fail = [f for f in failures if f["arm_class"] == "learned"]
    base_step0 = sum(1 for f in base_fail if f["first_failure_step"] == 0)
    base_malformed = sum(1 for f in base_fail if f["failure_kind"] == "malformed_output")
    learned_step0 = sum(1 for f in learned_fail if f["first_failure_step"] == 0)
    base_eps = sum(n for (ac, _a), n in agg["denom_algo"].items() if ac == "base")
    learned_eps = sum(n for (ac, _a), n in agg["denom_algo"].items() if ac == "learned")
    sft_bfs_width_eps = agg["denom_store_cell"].get(("baseline", "bfs", "process_sft"), 0) + agg[
        "denom_store_cell"
    ].get(("baseline", "best_first_width", "process_sft"), 0)
    sft_bfs_width_fail = agg["store_cell_failures"].get(
        ("baseline", "bfs", "process_sft"), 0
    ) + agg["store_cell_failures"].get(("baseline", "best_first_width", "process_sft"), 0)
    dagger_eps = sum(n for (s, _a, _r), n in agg["denom_store_cell"].items() if s == "dagger_new")
    dagger_fail = sum(
        n for (s, _a, _r), n in agg["store_cell_failures"].items() if s == "dagger_new"
    )
    additive_eps = sum(
        n
        for (ac, a), n in agg["denom_algo"].items()
        if ac == "learned" and a in ("best_first_add_greedy", "best_first_add_w3")
    )
    additive_fail = sum(
        1
        for f in learned_fail
        if f["algorithm"] in ("best_first_add_greedy", "best_first_add_w3")
    )


    kind_rows = []
    for ac in ["learned", "base", "oracle_control", "reference"]:
        total = by_arm_class.get(ac, 0)
        if not total:
            continue
        kinds = sorted(
            ((k, n) for (a, k), n in agg["kind_by_armclass"].items() if a == ac),
            key=lambda x: (-x[1], x[0]),
        )
        for k, n in kinds:
            kind_rows.append([ac, k, n, f"{n / total:.1%}"])

    cov_rows = [
        [
            c["branch"],
            c["issue"],
            c["expected_episodes"],
            c["episodes_consumed"],
            c["missing_episodes"],
            c["failed_episodes"],
            c["succeeded_episodes"],
        ]
        for c in cov
    ]

    horizon_rows = []
    for ac in ["learned", "base", "oracle_control"]:
        for b in HORIZON_BUCKETS:
            n = sum(
                x["failures"]
                for x in matrix["horizon_distribution"]
                if x["arm_class"] == ac and x["horizon_bucket"] == b
            )
            if n:
                horizon_rows.append([ac, b, n])

    ratio_rows = [
        [
            r["arm_class"],
            r["algorithm_family"],
            r["failures_with_reference"],
            f"{r['horizon_ratio_mean']:.3f}",
            f"{r['horizon_ratio_median']:.3f}",
            f"{r['horizon_ratio_min']:.3f}",
            f"{r['horizon_ratio_max']:.3f}",
        ]
        for r in matrix["horizon_ratio_summary"]
    ]

    top_ops = sorted(
        matrix["operation_type_frequency"],
        key=lambda x: (-x["failures"], x["arm_class"], x["operation_type"]),
    )[:20]
    op_rows = [[o["arm_class"], o["operation_type"], o["failures"]] for o in top_ops]

    diff_rows = [
        [d["arm_class"], d["frontier_size_bucket"], d["branching_factor_bucket"], d["failures"]]
        for d in sorted(
            matrix["difficulty_at_failure"],
            key=lambda x: (
                x["arm_class"],
                FRONTIER_BUCKETS.index(x["frontier_size_bucket"])
                if x["frontier_size_bucket"] in FRONTIER_BUCKETS
                else 99,
                BRANCHING_BUCKETS.index(x["branching_factor_bucket"])
                if x["branching_factor_bucket"] in BRANCHING_BUCKETS
                else 99,
            ),
        )
    ]

    tiny = [c for c in matrix["cells"] if c["descriptive_only"]]
    tiny_rows = [
        [
            "algorithm x modality x arm",
            f"{c['algorithm_family']} / {c['modality']} / {c['arm']}",
            c["failure_kind"],
            c["failures"],
            c["stratum_episodes"],
        ]
        for c in tiny
    ]
    panel_tiny = [p for p in matrix["branch_panel"] if p["descriptive_only"]]
    tiny_rows += [
        [
            "branch x panel x modality x arm",
            f"{p['branch']} / {p['panel']} / {p['modality']} / {p['arm']}",
            "",
            p["failures"],
            p["episodes"],
        ]
        for p in panel_tiny
    ]
    panel_rows = [
        [
            p["branch"],
            p["panel"],
            p["modality"],
            p["arm"],
            p["episodes"],
            p["failures"],
            "yes" if p["descriptive_only"] else "",
        ]
        for p in matrix["branch_panel"]
    ]

    successor_fail = [f for f in failures if "successor_prediction" in f["branches"]]
    succ_rows = []
    for k, n in sorted(Counter(f["failure_kind"] for f in successor_fail).items(), key=lambda x: -x[1]):
        succ_rows.append([k, n])

    genrob_fail = [
        f
        for f in failures
        if "generalization_robustness_v2" in f["branches"] and f["arm_class"] == "learned"
    ]
    genrob_family = Counter(f["family"] for f in genrob_fail)

    manifest_rows = [[k, v["files"], f"`{v['sha256'][:16]}…`"] for k, v in sorted(matrix["input_manifest"].items())]
    anchor_rows = [[a["check"], "PASS" if a["pass"] else "FAIL"] for a in matrix["anchor_checks"]]

    doc = f"""# Failure-mechanism calibration analysis from replayed episodes

Issue: #125 (parent #38, feeds the #121 manuscript analysis section).
Protocol: frozen as
[`failure-mechanism-protocol.md`](failure-mechanism-protocol.md) +
[`configs/experiments/expanded-study/failure-mechanism-protocol.json`](../../../configs/experiments/expanded-study/failure-mechanism-protocol.json)
**before** any outcomes were computed from the logs, per the issue's execution
rules. This document is descriptive only: it mines existing, independently
replay-verified episode evidence and makes no causal claim beyond what the
underlying verified experiments established. Budget: 0 GPU-h, CPU only; no new
model outcomes, no retraining, no re-rendering.

## Inputs, coverage and missingness

{len(failures)} failed episodes were mined out of
{matrix['episodes_consumed_unique']} unique replay-verified episodes
({sum(c['episodes_consumed'] for c in cov)} branch bindings across the five
named sources; episodes reused as comparators are mined once).

{_md_table(["store", "files", "sha256 (prefix)"], manifest_rows)}

{_md_table(["branch", "issue", "expected", "consumed", "missing", "failed", "succeeded"], cov_rows)}

Replay anchors re-verified while mining:

{_md_table(["anchor check", "outcome"], anchor_rows)}

Missingness by construction, stated per source branch:

- **generalization_robustness_v2 (#124)** evaluated only the two additive
  best-first families (not `bfs`/`best_first_width`), 25 of the 120-variant
  suite (k=5 cheapest prefix per family) and 6 of the 12 frozen adapters; the
  base arm was capped at one model call per episode. These were frozen
  cost-only decisions of the source branch, not outcome-based exclusions.
- **successor_prediction (#89/#99)** covered 15 of the 27 panel tasks (3
  development + 12 outcome-blind unseen); the full 24-task panel was priced
  infeasible by the source branch and remains missing.
- **dagger (#84)** is `bfs` only; **curriculum (#119)** is
  `best_first_add_greedy` only; **baseline (#118)** is the only branch
  covering all four algorithm families.
- Development-panel comparators for dagger/curriculum are v5 episodes without
  a `schema_version`; they entered only through the replay-verified
  dagger/curriculum audits.

Per-branch panel strata (episodes and failures per branch x panel x modality x
arm; `tiny` marks strata below the frozen {TINY_LIMIT}-episode limit):

{_md_table(["branch", "panel", "modality", "arm", "episodes", "failures", "tiny"], panel_rows)}

## Headline failure profile

- **Base policy (`pretrained_base`):** {len(base_fail)} failures in
  {base_eps} episodes; {base_step0} fail on the very first decision and
  {base_malformed} of them emit a malformed output that never reaches the
  operation checker. The base never succeeds anywhere in the mined evidence.
- **Learned arms:** {len(learned_fail)} failures across {learned_eps} learned
  episodes; {learned_step0} on the first decision. Failures concentrate in
  the BFS and best-first-width families: every baseline SFT BFS and
  best-first-width episode fails ({sft_bfs_width_fail}/{sft_bfs_width_eps}),
  the DAgger-iteration BFS arms fail {dagger_fail}/{dagger_eps}, while the
  learned additive best-first families fail {additive_fail}/{additive_eps}
  episodes ({additive_fail / additive_eps:.1%}).
- **Oracle control (`random_valid`):** {by_arm_class.get('oracle_control', 0)}
  failures, all `expansion_budget_exhausted` — the control emits only valid
  operations but can starve its expansion budget; it is an oracle-assisted
  bound, not learned ability.
- **Reference arms** ({by_arm_class.get('reference', 0)} failures): the
  reference bounds hold everywhere except where noted as tiny strata.

## Failure taxonomy distribution

{_md_table(["arm class", "failure kind", "failures", "share of class"], kind_rows)}

Successor-prediction rejection kinds (verbatim from the episodes'
`verification.failure_kind`):

{_md_table(["successor failure kind", "episodes"], succ_rows)}

Generalization-v2 learned failures by perturbation/shift family (k=5 variants
per family; descriptive-only strata):

{_md_table(["family", "learned failures"], sorted(genrob_family.items()))}

## Horizon position (first-failure step distribution)

First-failure decision index over the frozen buckets `0, 1, 2, 3-4, 5-8,
9-16, 17-32, 33+`:

{_md_table(["arm class", "horizon bucket", "failures"], horizon_rows)}

Horizon ratio `first_failure_step / reference_decisions` against the matched
`exact_reference` decision counts ({matrix['failures_missing_reference']}
failure records lacked a reference and are excluded here):

{_md_table(["arm class", "algorithm family", "n", "mean", "median", "min", "max"], ratio_rows)}

## Operation type at first failure

Top operation types (action names; `frontier:<type>` for rejected BFS
frontier operations) across all failed episodes:

{_md_table(["arm class", "operation type", "failures"], op_rows)}

## Frontier/branching difficulty at first failure

Frontier size and branching factor (successor candidate count) logged at the
first-failure event, over the frozen buckets `0, 1-2, 3-5, 6-10, 11+` and
`0-1, 2-3, 4-6, 7-12, 13+`:

{_md_table(["arm class", "frontier size bucket", "branching factor bucket", "failures"], diff_rows)}

## Tiny-strata register

Strata with fewer than {TINY_LIMIT} episodes are descriptive-only; they are
listed here and in `tiny-strata.csv`, never silently pooled or dropped:

{_md_table(["stratum scope", "stratum", "failure kind", "failures", "stratum episodes"], tiny_rows)}

## Claim discipline and boundaries

- Descriptive only: no causal claims beyond the underlying verified
  experiments; no intervals are computed over tiny strata.
- `random_valid` is oracle-assisted; controls are bounds, not learned
  ability. Validity-conditioned success is selected and is not
  repaired-policy counterfactual performance.
- P3 name-compression lossy strata (generalization v2) are reported
  separately per family above and never pooled with semantics-preserving
  variants.
- All learned arms rest on training seed 17 and evaluation seed 17; no
  seed-variance claims. The base arm in generalization v2 was capped at one
  call, so its horizon statistics are structurally step-0.
- #96, #98, #102, #103, #121 and #122 are neither closed nor modified by
  this analysis.

## Reproducibility

`python3 scripts/failure_mechanism_analysis.py` regenerates
`failure-mechanism-matrix.json`, `failure-mechanism-tables/*.csv` and this
document; `--check` byte-compares a fresh regeneration against the published
artifacts and re-verifies the anchor checks, the zero-`unclassified` gate and
the frozen coverage counts. The machine-readable matrix records one row per
failed episode with the raw failing output preserved.
"""
    return doc


# ---------------------------------------------------------------------------
# Publishing / check mode
# ---------------------------------------------------------------------------


def build_outputs():
    mined = mine()
    agg = aggregate(mined)
    anchors = verify_anchors()
    matrix = render_matrix(mined, agg, anchors)
    tables = render_tables(matrix)
    doc = render_document(matrix, agg, mined)
    return mined, matrix, tables, doc, anchors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate and byte-compare against published outputs without writing",
    )
    args = parser.parse_args()

    mined, matrix, tables, doc, anchors = build_outputs()

    failures = []
    if not all(a["pass"] for a in anchors):
        failures.append("one or more replay anchor checks failed")
    if mined["unclassified"]:
        failures.append(f"{mined['unclassified']} unclassified failures (must be zero)")
    for c in matrix["coverage"]:
        if c["missing_episodes"]:
            failures.append(f"branch {c['branch']} missing {c['missing_episodes']} episodes")

    outputs = {MATRIX_PATH: json.dumps(matrix, indent=1, sort_keys=False) + "\n"}
    for name, content in sorted(tables.items()):
        outputs[TABLES_DIR / name] = content
    outputs[DOC_PATH] = doc

    if args.check:
        for path, content in sorted(outputs.items(), key=str):
            if not path.exists():
                failures.append(f"missing published output: {path}")
                continue
            if path.read_text() != content:
                failures.append(f"published output differs from regeneration: {path}")
        if failures:
            for f in failures:
                print(f"CHECK FAIL: {f}")
            sys.exit(1)
        print(
            f"CHECK PASS: {len(outputs)} outputs byte-identical; "
            f"{matrix['episodes_consumed_unique']} unique episodes, "
            f"{matrix['failures_total']} failures; anchors PASS; unclassified = 0"
        )
        return

    if failures:
        for f in failures:
            print(f"REFUSING TO PUBLISH: {f}")
        sys.exit(1)

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        path.write_text(content)
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
