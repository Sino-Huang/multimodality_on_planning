#!/usr/bin/env python
"""External identity audit v2 (#142): control and reference arms on LLM-First Search.

Frozen protocol: ``docs/experiments/external-audit/issue-142-protocol.md``.

Interface: LLM-First Search (Herr, Rocktaeschel, Raileanu, arXiv 2506.05213), repository
https://github.com/NathanHerr/LLM-First-Search @ 3025bdaa3add (Apache-2.0), cloned untracked
under ``outputs/external-audit/v2/upstream/LLM-First-Search`` and imported, never copied.
Episodes run the upstream ``run_countdown`` / ``run_sudoku`` loops unchanged, on the upstream
data files, with the paper's token caps. The runner only (a) supplies the model client, (b)
records every node expansion (the search's decision) by wrapping ``PathNode.expand``, (c)
keeps the upstream per-episode result in memory instead of pickling the whole search tree,
and (d) for ``random_valid`` answers every agent query with a uniformly random valid response
instead of calling a model.

Arms:

- ``reference``    - the published LFS controller; every agent query goes to the substitute
  open-weight model served by vLLM (OpenAI-compatible endpoint), temperature 0.0,
  max_tokens 16384, timeout 300 s, as in the paper's Appendix D.
- ``random_valid`` - no model: ``explore`` is a fair coin, every requested value is an
  independent U(0, 1) draw (so the argmax child / popped frontier node is uniform among the
  valid options), zero tokens. Seeds 17, 5077, 6131, 7409, 8527; the per-episode RNG is
  ``random.Random(int(sha256(f"{seed}|{task}")[:16], 16))``.

The upstream code lives in the separate venv ``outputs/external-audit/v2/venv-lfs`` (the pinned
``requirements.txt``); started from ada_vla, the script re-executes itself with that interpreter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "external-audit" / "v2"
VENV_PYTHON = OUT / "venv-lfs" / "bin" / "python"
UPSTREAM = OUT / "upstream" / "LLM-First-Search"
UPSTREAM_COMMIT = "3025bdaa3add6f41388c1d5a6d354522489d312e"

SEEDS = (17, 5077, 6131, 7409, 8527)
# README "Reproducing Paper Results": --num-batches 20 --batch-size 1 -> games 0..19 of each file.
AUDIT_GAMES = tuple(range(20))
PROBE_GAMES = tuple(range(20, 25))  # feasibility probe only; never audited
# Task configurations (README tables): Countdown val split, difficulty 3/5/7, token cap 1e6;
# Sudoku 4x4 (2x2 boxes) hard, token cap 1e5. Sudoku 6x6 is excluded by the protocol's rule.
CONFIGS = {
    "cd3": {"game_type": "countdown", "difficulty": "3", "max_token_usage": 1_000_000},
    "cd5": {"game_type": "countdown", "difficulty": "5", "max_token_usage": 1_000_000},
    "cd7": {"game_type": "countdown", "difficulty": "7", "max_token_usage": 1_000_000},
    "su4": {"game_type": "sudoku", "size": 4, "width": 2, "height": 2, "difficulty": "hard",
            "max_token_usage": 100_000},
}
CONFIG_ORDER = ("cd3", "su4", "cd5", "cd7")
EXPANSION_CAP = 500_000  # safety guard (protocol "Budget"); hitting it is logged, counted as a loss
TEMPERATURE = 0.0
MAX_TOKENS = 16384
TIMEOUT = 300
MODEL_NAME = "Qwen/Qwen3-30B-A3B-Instruct-2507"
DETERMINISM_SEED = 142


def ensure_upstream_interpreter() -> None:
    try:
        import sudoku  # noqa: F401  (py-sudoku, only in venv-lfs)
    except ImportError:
        if Path(sys.prefix).resolve() == VENV_PYTHON.parents[1].resolve():
            raise
        os.execve(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]], dict(os.environ))


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def dumps(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(obj))


def task_list(games) -> list[dict]:
    return [{"task": f"{c}-{g:02d}", "config": c, "game": g, **CONFIGS[c]} for c in CONFIG_ORDER for g in games]


def episode_seed(seed: int, task: str) -> int:
    return int(hashlib.sha256(f"{seed}|{task}".encode()).hexdigest()[:16], 16)


def episode_path(out_dir: Path, task: str, arm: str, seed) -> Path:
    return out_dir / "episodes" / task / f"{arm}-{'ref' if seed is None else seed}.json"

# --------------------------------------------------------------------------- upstream hooks

_T = threading.local()  # per-episode state: decisions, labels, n_options, captured, responder, fast
_UP = None


class ExpansionCap(Exception):
    pass


class FastFrontier:
    """Unexpanded nodes of the episode's tree, kept incrementally (random_valid arm only).

    Upstream recomputes ``Explorer.frontier_nodes`` by a full-tree BFS several times per step and
    re-sums the token list inside the loop over the frontier, which is quadratic-to-cubic in the
    number of expansions and does not finish on Countdown-7 for a zero-token chooser. Under the
    random responder (i) every frontier node already holds a value when the frontier is read and
    (ii) all values are distinct doubles, so upstream's loop over the frontier evaluates nothing and
    ``create_sorted_nodes_by_value(...)[-1]`` is the unique maximum whatever the list order. This
    view returns the same node through a lazy max-heap and asserts (i) and (ii); equivalence with
    the unpatched loop is checked by ``fast-equivalence``.
    """

    def __init__(self):
        self.nodes: dict[int, object] = {}
        self.pending: list = []
        self.heap: list = []
        self.seq = 0
        self.expanded = 0
        self.size = 1

    def add_children(self, node) -> None:
        self.expanded += 1
        self.nodes.pop(id(node), None)
        for child in node.children:
            self.nodes[id(child)] = child
            self.pending.append(child)
        self.size += len(node.children)

    def _flush(self) -> None:
        import heapq

        for node in self.pending:
            assert node.value is not None, "random_valid invariant: frontier node without a value"
            heapq.heappush(self.heap, (-float(node.value), self.seq, node))
            self.seq += 1
        self.pending = []

    def __bool__(self) -> bool:
        return bool(self.nodes)

    def __len__(self) -> int:
        return len(self.nodes)

    def __iter__(self):
        self._flush()  # asserts every frontier node is valued: upstream's loop has nothing to evaluate
        return iter(())

    def top(self):
        import heapq

        self._flush()
        while self.heap and self.heap[0][2].expanded:
            heapq.heappop(self.heap)
        if not self.heap:
            return None
        best = self.heap[0]
        second = min((self.heap[i] for i in (1, 2) if i < len(self.heap)), default=None)
        if second is not None and not second[2].expanded:  # the runner-up must not tie with the maximum
            assert second[0] != best[0], "random_valid invariant: tied frontier values"
        return best[2]


def upstream():
    """Import the pinned upstream once and install the thread-local hooks."""
    global _UP
    if _UP is not None:
        return _UP
    os.environ.setdefault("TQDM_DISABLE", "1")
    sys.path.insert(0, str(UPSTREAM))
    import src.llm_first_search as lfs
    import src.utils.common_utils as common
    from src.countdown_game.countdown_agent import CountdownAgent
    from src.sudoku_game.sudoku_agent import SudokuAgent
    from src.utils.tree_utils import Explorer, PathNode

    orig_expand = PathNode.expand

    def expand(self):
        rec = getattr(_T, "decisions", None)
        if rec is not None and self.parent is not None:
            path, node = [], self
            while node.parent is not None:
                path.append(node.parent.children.index(node))
                node = node.parent
            if len(rec) >= _T.cap:
                raise ExpansionCap(len(rec))
            rec.append(".".join(map(str, reversed(path))))
            _T.labels.append(self.game_node.get_action_description())
            _T.n_options.append(len(self.parent.children))
        result = orig_expand(self)
        if getattr(_T, "fast", None) is not None:
            _T.fast.add_children(self)
        return result

    PathNode.expand = expand

    for cls in (CountdownAgent, SudokuAgent):
        orig_ask = cls.ask

        def ask(self, query_type, _orig=orig_ask, **kwargs):
            responder = getattr(_T, "responder", None)
            if responder is None:
                return _orig(self, query_type=query_type, **kwargs)
            return responder(query_type, kwargs)

        cls.ask = ask

    # Fast-path views (active only while _T.fast is set, i.e. random_valid episodes run with --fast).
    orig_frontier = Explorer.frontier_nodes.fget
    orig_unexpanded = Explorer.get_unexpanded_nodes
    orig_tree_size = Explorer.tree_size
    orig_expanded_count = Explorer.expanded_nodes_count
    orig_sorted = lfs.create_sorted_nodes_by_value
    orig_stats = common.calculate_token_stats

    def fast():
        return getattr(_T, "fast", None)

    Explorer.frontier_nodes = property(lambda self: fast() if fast() is not None else orig_frontier(self))
    Explorer.get_unexpanded_nodes = lambda self: fast() if fast() is not None else orig_unexpanded(self)
    Explorer.tree_size = lambda self: fast().size if fast() is not None else orig_tree_size(self)
    Explorer.expanded_nodes_count = (
        lambda self: fast().expanded if fast() is not None else orig_expanded_count(self))

    def sorted_nodes(nodes, use_adjusted_value=False):
        if isinstance(nodes, FastFrontier):
            best = nodes.top()
            return [best] if best is not None else []
        return orig_sorted(nodes, use_adjusted_value)

    def token_stats(token_usage):
        if fast() is None:
            return orig_stats(token_usage)
        memo = _T.stats_memo  # token lists only grow: add the new tail to the cached running total
        n, total = memo.get(id(token_usage), (0, 0))
        total += sum(u.get("total_tokens", 0) for _, u in token_usage[n:])
        memo[id(token_usage)] = (len(token_usage), total)
        return {"total_tokens": total, "api_call_count": len(token_usage)}

    lfs.create_sorted_nodes_by_value = sorted_nodes
    lfs.calculate_token_stats = token_stats
    common.calculate_token_stats = token_stats

    def save_game_state(output_path, all_outputs, game_idx, outputs):
        _T.captured = outputs[-1] if outputs else None

    lfs.save_game_state = save_game_state
    lfs.load_game_state = lambda output_path: ([], 0)
    _UP = lfs
    return lfs


def random_responder(rng: random.Random):
    zero = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def respond(query_type, kwargs):
        if query_type == "explore":
            resp = rng.random() < 0.5
        elif query_type == "value":
            resp = rng.random()
        elif query_type == "child_values":
            resp = {str(k): rng.random() for k in kwargs["action_list"]}
        elif query_type == "child_moves":
            resp = {str(k): rng.random() for k in kwargs["moves_list"]}
        elif query_type == "action":
            resp = rng.choice(sorted(kwargs["action_list"]))
        else:
            raise ValueError(f"unexpected query type {query_type}")
        return {"full_response": "", "resp": resp, "token_usage": dict(zero)}

    return respond


class RecordingClient:
    """OpenAI-client stand-in that forwards to a live client and logs each call."""

    def __init__(self, inner, calls: list):
        self.inner, self.calls = inner, calls
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **params):
        req = sha256(json.dumps({k: v for k, v in params.items() if k != "timeout"}, sort_keys=True))
        resp = self.inner.chat.completions.create(**params)
        u = resp.usage
        self.calls.append({
            "request_sha256": req,
            "content": resp.choices[0].message.content,
            "finish_reason": resp.choices[0].finish_reason,
            "usage": {"prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
                      "total_tokens": u.total_tokens},
        })
        return resp


class ReplayClient:
    """Returns logged responses in order; asserts each request is byte-identical to the logged one."""

    def __init__(self, calls: list):
        self.calls, self.i = calls, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **params):
        req = sha256(json.dumps({k: v for k, v in params.items() if k != "timeout"}, sort_keys=True))
        assert self.i < len(self.calls), "replay requested more calls than were logged"
        call = self.calls[self.i]
        assert req == call["request_sha256"], f"request {self.i} differs from the logged request"
        self.i += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=call["content"]),
                                     finish_reason=call["finish_reason"])],
            usage=SimpleNamespace(**call["usage"]),
        )


def upstream_args(task: dict, tmp: str):
    lfs = upstream()
    argv = ["--data_dir", str(UPSTREAM / "data" / task["game_type"]), "--output_dir", tmp,
            "--game_type", task["game_type"], "--search_method", "lfs",
            "--model_name", MODEL_NAME, "--model_type", "openai", "--temperature", str(TEMPERATURE),
            "--max_tokens", str(MAX_TOKENS), "--timeout", str(TIMEOUT), "--reasoning", "0",
            "--batch_num", str(task["game"]), "--batch_size", "1", "--num_its", "1",
            "--max_token_usage", str(task["max_token_usage"])]
    if task["game_type"] == "countdown":
        argv += ["--split", "val", "--countdown_difficulty", task["difficulty"]]
    else:
        argv += ["--sudoku_size", str(task["size"]), "--sudoku_width", str(task["width"]),
                 "--sudoku_height", str(task["height"]), "--sudoku_difficulty", task["difficulty"]]
    return lfs.get_standard_parser().parse_args(argv)


def run_episode(task: dict, arm: str, seed: int | None, client=None, fast: bool = False) -> dict:
    """One upstream LFS episode. ``client``: live/replay OpenAI client (reference) or None (random_valid).

    ``fast`` (random_valid only) swaps upstream's full-tree frontier scans for ``FastFrontier``; the
    episode log must not depend on it (checked by the ``fast-equivalence`` command).
    """
    assert not fast or arm == "random_valid"
    lfs = upstream()
    _T.decisions, _T.labels, _T.n_options, _T.captured, _T.cap = [], [], [], None, EXPANSION_CAP
    _T.responder = random_responder(random.Random(episode_seed(seed, task["task"]))) if arm == "random_valid" else None
    _T.fast, _T.stats_memo = (FastFrontier() if fast else None), {}
    calls: list = []
    model = RecordingClient(client, calls) if arm == "reference" and not isinstance(client, ReplayClient) else client
    error = None
    start = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        args = upstream_args(task, tmp)
        try:
            (lfs.run_countdown if task["game_type"] == "countdown" else lfs.run_sudoku)(args, model)
        except ExpansionCap:
            error = "expansion_cap"
        except Exception:  # upstream crash (e.g. an agent query that failed all 5 retries)
            error = "upstream_error: " + traceback.format_exc(limit=3).strip().splitlines()[-1]
    wall = time.time() - start
    out = _T.captured
    won = bool(out["won"]) if (out is not None and error is None) else False
    total_tokens = out["total_tokens"] if out is not None else sum(c["usage"]["total_tokens"] for c in calls)
    if error == "expansion_cap":
        terminated = "expansion_cap"
    elif error is not None:
        terminated = "upstream_error"
    elif won:
        terminated = "success"
    elif total_tokens >= task["max_token_usage"]:
        terminated = "token_limit"
    else:
        terminated = "frontier_exhausted"
    ep = {
        "benchmark": "llm-first-search",
        "task": task["task"],
        "arm": arm,
        "seed": seed,
        "budget": {"max_token_usage": task["max_token_usage"], "expansion_cap": EXPANSION_CAP},
        "decisions": list(_T.decisions),
        "labels": list(_T.labels),
        "n_options": list(_T.n_options),
        "won": won,
        "steps": len(_T.decisions),
        "total_tokens": total_tokens,
        "api_call_count": out["api_call_count"] if out is not None else len(calls),
        "backtrack_count": out["backtrack_count"] if out is not None else None,
        "attempts": out["attempts"] if out is not None else None,
        "terminated": terminated,
        "error": error,
        "metrics_sha16": (sha256(json.dumps(out["metrics_log"], sort_keys=True, default=str))[:16]
                          if out is not None else None),
    }
    if arm == "reference":
        ep["calls"] = calls if not isinstance(client, ReplayClient) else None
        ep["model"] = MODEL_NAME
    _T.decisions = _T.responder = _T.fast = None
    return ep, wall


def _random_task(job) -> str:
    task, seed, out_dir = job
    sys.stdout = open(os.devnull, "w")
    path = episode_path(out_dir, task["task"], "random_valid", seed)
    if not path.exists():
        ep, wall = run_episode(task, "random_valid", seed, fast=True)
        write_json(path, ep)
        with open(out_dir / "random-walltime.jsonl", "a") as f:
            f.write(json.dumps({"task": task["task"], "seed": seed, "wall_s": round(wall, 3),
                                "steps": ep["steps"], "won": ep["won"], "terminated": ep["terminated"]}) + "\n")
    return f"{task['task']} seed {seed}"


def check_upstream() -> None:
    head = subprocess.run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    assert head == UPSTREAM_COMMIT, f"upstream checkout {head} != pinned {UPSTREAM_COMMIT}"
    dirty = subprocess.run(["git", "-C", str(UPSTREAM), "status", "--porcelain"], check=True,
                           capture_output=True, text=True).stdout.strip()
    assert not dirty, f"upstream checkout is modified:\n{dirty}"


def log(msg: str) -> None:
    print(msg, file=sys.__stderr__, flush=True)


def cmd_random(args, tasks, out_dir) -> None:
    jobs = [(t, s, out_dir) for t in tasks for s in SEEDS]
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(args.workers) as pool:
        for k, name in enumerate(pool.imap_unordered(_random_task, jobs)):
            log(f"[random {k + 1}/{len(jobs)}] {name}")


def _reference_task(job) -> str:
    import openai

    task, base_url, out_dir = job
    sys.stdout = open(os.devnull, "w")
    live = openai.OpenAI(base_url=base_url, api_key="EMPTY", timeout=TIMEOUT)
    ep, wall = run_episode(task, "reference", None, live)
    ep["wall_s"] = round(wall, 3)
    write_json(episode_path(out_dir, task["task"], "reference", None), ep)
    return f"{task['task']} won={ep['won']} steps={ep['steps']} tokens={ep['total_tokens']} {ep['terminated']}"


def cmd_reference(args, tasks, out_dir) -> None:
    import openai

    served = [m.id for m in openai.OpenAI(base_url=args.base_url, api_key="EMPTY").models.list().data]
    assert served == [MODEL_NAME], served
    todo = [(t, args.base_url, out_dir) for t in tasks
            if not episode_path(out_dir, t["task"], "reference", None).exists()]
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(args.concurrency) as pool:
        for k, res in enumerate(pool.imap_unordered(_reference_task, todo)):
            log(f"[reference {k + 1}/{len(todo)}] {res}")


COMPARE = ("decisions", "labels", "n_options", "won", "steps", "total_tokens", "api_call_count",
           "backtrack_count", "attempts", "terminated", "error", "metrics_sha16")


def cmd_fast_equivalence(args, tasks, out_dir) -> None:
    """random_valid episodes with the unpatched upstream loop vs FastFrontier: logs must be byte-identical."""
    rows = []
    for task in tasks:
        for seed in SEEDS[: args.equivalence_seeds]:
            fast, t_fast = run_episode(task, "random_valid", seed, fast=True)
            if fast["steps"] > args.equivalence_max_steps:
                rows.append({"task": task["task"], "seed": seed, "status": "skipped_long", "steps": fast["steps"]})
                continue
            slow, t_slow = run_episode(task, "random_valid", seed, fast=False)
            same = dumps(slow) == dumps(fast)
            rows.append({"task": task["task"], "seed": seed, "status": "identical" if same else "DIFFERENT",
                         "steps": fast["steps"], "won": fast["won"], "wall_s_upstream": round(t_slow, 2),
                         "wall_s_fast": round(t_fast, 3)})
            log(json.dumps(rows[-1]))
    checked = [r for r in rows if r["status"] != "skipped_long"]
    write_json(out_dir / "fast-equivalence.json", {
        "description": ("random_valid episodes run twice in one process, through the unpatched upstream loop and "
                        "with FastFrontier; episode logs (decisions, labels, options, outcome, token counts, "
                        "metrics_log hash) compared byte for byte"),
        "checked": len(checked), "identical": sum(r["status"] == "identical" for r in checked),
        "skipped_long": len(rows) - len(checked), "max_steps": args.equivalence_max_steps, "rows": rows,
    })


def cmd_replay(args, tasks, out_dir) -> None:
    """Replay every reference episode from its logged model responses; re-run random_valid episodes."""
    ref = []
    for task in tasks:
        path = episode_path(out_dir, task["task"], "reference", None)
        if not path.exists():
            ref.append({"task": task["task"], "status": "missing"})
            continue
        logged = json.loads(path.read_text())
        client = ReplayClient(logged["calls"])
        try:
            ep, _ = run_episode(task, "reference", None, client)
            diff = [k for k in COMPARE if ep[k] != logged[k]]
            if client.i != len(logged["calls"]):
                diff.append(f"calls_consumed {client.i}/{len(logged['calls'])}")
        except AssertionError as e:
            diff = [f"replay assertion: {e}"]
        ref.append({"task": task["task"], "status": "match" if not diff else "mismatch", "diff": diff,
                    "calls": len(logged["calls"]), "sha16": sha16(path)})
        log(f"[replay] {task['task']} {ref[-1]['status']} {diff}")
    picks = [(t, s) for t in tasks for s in SEEDS]
    if args.random_sample:
        picks = random.Random(DETERMINISM_SEED).sample(picks, min(args.random_sample, len(picks)))
    rnd = []
    for task, seed in picks:
        path = episode_path(out_dir, task["task"], "random_valid", seed)
        if not path.exists():
            rnd.append({"task": task["task"], "seed": seed, "status": "missing"})
            continue
        ep, _ = run_episode(task, "random_valid", seed, fast=True)
        same = path.read_bytes() == dumps(ep).encode()
        rnd.append({"task": task["task"], "seed": seed, "status": "match" if same else "mismatch", "sha16": sha16(path)})
    count = lambda rows, s: sum(r["status"] == s for r in rows)  # noqa: E731
    summary = {
        "description": ("reference: every episode re-executed through the unchanged upstream loop with a client that "
                        "returns the logged model responses in order and asserts each request equals the logged "
                        "request (sha256); decisions/outcome compared field by field. random_valid: episodes re-run "
                        "in a fresh process and compared byte for byte."),
        "reference": {"episodes": len(ref), "match": count(ref, "match"), "mismatch": count(ref, "mismatch"),
                      "missing": count(ref, "missing"), "rows": ref},
        "random_valid": {"episodes": len(rnd), "match": count(rnd, "match"), "mismatch": count(rnd, "mismatch"),
                         "missing": count(rnd, "missing"), "sample": args.random_sample or "all", "rows": rnd},
    }
    write_json(out_dir / "replay.json", summary)
    log(json.dumps({k: {kk: v for kk, v in summary[k].items() if kk != "rows"} for k in ("reference", "random_valid")}))


def main() -> None:
    ensure_upstream_interpreter()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("random", "reference", "replay", "fast-equivalence"))
    parser.add_argument("--set", choices=("audit", "probe", "smoke"), default="audit",
                        help="audit: games 0-19; probe: games 20-24 (feasibility only); smoke: games 20-21")
    parser.add_argument("--configs", default=",".join(CONFIG_ORDER))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--base-url", default="http://127.0.0.1:18850/v1")
    parser.add_argument("--random-sample", type=int, default=0, help="replay: 0 = all random_valid episodes")
    parser.add_argument("--equivalence-seeds", type=int, default=len(SEEDS))
    parser.add_argument("--equivalence-max-steps", type=int, default=3000)
    args = parser.parse_args()
    check_upstream()
    sys.stdout = open(os.devnull, "w")  # upstream prints every step; progress goes to stderr
    games = {"audit": AUDIT_GAMES, "probe": PROBE_GAMES, "smoke": PROBE_GAMES[:2]}[args.set]
    configs = args.configs.split(",")
    tasks = [t for t in task_list(games) if t["config"] in configs]
    out_dir = OUT / {"audit": "lfs", "probe": "lfs-probe", "smoke": "lfs-smoke"}[args.set]
    write_json(out_dir / "tasks.json", task_list(games))
    info_path = out_dir / f"run-info-{args.command}.json"
    write_json(info_path, {
        "interpreter": sys.executable, "upstream": str(UPSTREAM), "upstream_commit": UPSTREAM_COMMIT,
        "argv": sys.argv, "configs": configs, "seeds": list(SEEDS), "expansion_cap": EXPANSION_CAP,
        "model": MODEL_NAME if args.command != "random" else None,
        "base_url": args.base_url if args.command == "reference" else None,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    commands = {"random": cmd_random, "reference": cmd_reference, "replay": cmd_replay,
                "fast-equivalence": cmd_fast_equivalence}
    commands[args.command](args, tasks, out_dir)


if __name__ == "__main__":
    main()
