from __future__ import annotations

from types import MethodType

from examples.planning_benchmark_slice.batched_search_evaluation import (
    DeterministicSearchScheduler,
    EvaluationTask,
    PerformanceQualificationReceipt,
    SchedulerStopToken,
    balanced_fallback_panel,
    cost_balanced_task_shards,
    form_deterministic_batches,
    select_certified_coverage,
)
from examples.planning_benchmark_slice.model_search_episode import SearchPolicyRequest
from examples.planning_benchmark_slice.qwen_text_policy import BatchedPolicyAdapter
from src.data_collect.governance import StopOutcome


def _request(
    *,
    session: str,
    adapter: str | None,
    seed: int,
    instance: str,
    decision: int = 0,
    value: str | None = None,
) -> SearchPolicyRequest:
    return SearchPolicyRequest(
        session_id=session,
        adapter_id=adapter,
        seed=seed,
        instance_id=instance,
        decision_index=decision,
        model_input={"value": instance if value is None else value},
    )


def test_deterministic_batches_sort_pack_and_isolate_adapters() -> None:
    requests = [
        _request(session="z", adapter="adapter-b", seed=29, instance="z"),
        _request(session="b", adapter=None, seed=17, instance="b"),
        _request(session="a", adapter=None, seed=17, instance="a"),
        _request(session="c", adapter=None, seed=29, instance="c"),
    ]
    lengths = {"a": 3, "b": 4, "c": 5, "z": 2}

    batches = form_deterministic_batches(
        requests,
        token_length=lambda request: lengths[request.instance_id],
        max_batch_size=2,
        max_batch_input_tokens=10,
    )

    assert [[request.session_id for request in batch.requests] for batch in batches] == [
        ["a", "b"],
        ["c"],
        ["z"],
    ]
    assert [batch.adapter_id for batch in batches] == [None, None, "adapter-b"]
    assert all(batch.padded_input_tokens <= 10 for batch in batches)


def test_batched_adapter_cache_shares_base_requests_but_isolates_adapters() -> None:
    policy = object.__new__(BatchedPolicyAdapter)
    policy._output_cache = {}
    calls: list[tuple[str | None, int]] = []

    def generate_uncached(
        _self: BatchedPolicyAdapter,
        adapter_id: str | None,
        requests: list[SearchPolicyRequest],
    ) -> list[str]:
        calls.append((adapter_id, len(requests)))
        return [f"{adapter_id or 'base'}:{request.model_input['value']}" for request in requests]

    policy._generate_uncached = MethodType(generate_uncached, policy)
    base_seed_17 = _request(session="base-17", adapter=None, seed=17, instance="x", value="same")
    base_seed_29 = _request(session="base-29", adapter=None, seed=29, instance="x", value="same")
    adapted = _request(session="adapted", adapter="seed-17", seed=17, instance="x", value="same")

    assert policy.generate_many([base_seed_17, base_seed_29, adapted]) == [
        "base:same",
        "base:same",
        "seed-17:same",
    ]
    assert calls == [(None, 1), ("seed-17", 1)]
    assert policy.generate_many([base_seed_29, adapted]) == ["base:same", "seed-17:same"]
    assert calls == [(None, 1), ("seed-17", 1)]


def test_scheduler_never_launches_the_next_adapter_after_stop() -> None:
    stop = SchedulerStopToken()

    class Session:
        def __init__(self, request: SearchPolicyRequest) -> None:
            self.session_id = request.session_id
            self.request = request
            self.submitted = False

        def next_request(self) -> SearchPolicyRequest | None:
            return None if self.submitted else self.request

        def submit_output(self, _output: str) -> None:
            self.submitted = True

        def episode(self) -> dict[str, object]:
            return {"result": {"termination_reason": "done"}}

    class Policy:
        max_batch_size = 8
        max_batch_input_tokens = 48_000

        def __init__(self) -> None:
            self.adapters: list[str | None] = []

        def input_token_length(self, _request: SearchPolicyRequest) -> int:
            return 10

        def generate_many(self, requests: tuple[SearchPolicyRequest, ...]) -> list[str]:
            self.adapters.append(requests[0].adapter_id)
            stop.request_stop("SIGINT")
            return ["output"] * len(requests)

    policy = Policy()
    sessions = [
        Session(_request(session="base", adapter=None, seed=17, instance="a")),
        Session(_request(session="adapted", adapter="seed-17", seed=17, instance="a")),
    ]

    result = DeterministicSearchScheduler(policy, stop_token=stop).run(sessions)  # type: ignore[arg-type]

    assert policy.adapters == [None]
    assert result.launched_batches == 1
    assert result.completed == {}
    assert result.incomplete_session_ids == ("adapted", "base")
    assert result.stop_reason == "SIGINT"


def test_frozen_panel_is_one_domain_each_and_balanced_without_outcomes() -> None:
    tasks = tuple(
        EvaluationTask(domain, difficulty, f"{domain}-{difficulty}", exact_reference_decisions=10)
        for domain in [f"domain-{index:02d}" for index in range(15)]
        for difficulty in ("easy", "medium", "hard")
    )
    panel = balanced_fallback_panel(tasks)

    assert len(panel) == 15
    assert len({task.domain for task in panel}) == 15
    assert {
        difficulty: sum(task.difficulty == difficulty for task in panel) for difficulty in ("easy", "medium", "hard")
    } == {
        "easy": 5,
        "medium": 5,
        "hard": 5,
    }

    full_receipt = PerformanceQualificationReceipt(0, 100, 0, 100, ("probe",))
    assert select_certified_coverage(tasks, full_receipt, model_sessions_per_task=10).mode == "full"
    stopped = select_certified_coverage(
        tasks,
        PerformanceQualificationReceipt(0, 0.001, 0, 100, ("probe",)),
        model_sessions_per_task=10,
    )
    assert stopped.outcome is StopOutcome.VALID_STOP
    assert stopped.tasks == ()


def test_cost_balanced_shards_are_deterministic_and_use_only_exact_cost() -> None:
    tasks = tuple(
        EvaluationTask(f"domain-{index}", "easy", f"task-{index}", exact_reference_decisions=cost)
        for index, cost in enumerate((20, 15, 10, 5))
    )

    shards = cost_balanced_task_shards(tuple(reversed(tasks)))

    assert [[task.instance_id for task in shard] for shard in shards] == [
        ["task-0", "task-3"],
        ["task-1", "task-2"],
    ]
