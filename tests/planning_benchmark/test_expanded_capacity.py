"""Complete-input limits reject requests before model execution or truncation."""

from types import SimpleNamespace
import pytest

from examples.planning_benchmark_slice import scene_only_views, visual_model


def test_native_observation_preserves_exact_limit_and_refuses_one_token_over(monkeypatch):
    counter = SimpleNamespace(value=32384)
    monkeypatch.setattr(
        scene_only_views, "frozen_processor", lambda: SimpleNamespace(count=lambda *a, **k: counter.value)
    )
    monkeypatch.setattr(scene_only_views, "project_messages", lambda *a, **k: [{"full": "unchanged"}])
    views = object.__new__(scene_only_views.SceneOnlyViews)
    views.pages = lambda *a, **k: ([], [])
    result = views.observe("task", 0, {}, "bfs", {}, "text-state", pixels=False)
    assert result["binding"]["input_tokens"] == 32384
    assert result["messages"] == [{"full": "unchanged"}]
    counter.value = 32385
    with pytest.raises(RuntimeError, match="complete input exceeds"):
        views.observe("task", 0, {}, "bfs", {}, "text-state", pixels=False)


@pytest.mark.parametrize("tokens,batch,cap", [(32385, 1, 32384), (12001, 2, 24000), (100, 3, 24000)])
def test_policy_rejects_oversize_without_a_model(monkeypatch, tokens, batch, cap):
    monkeypatch.setattr(visual_model, "frozen_processor", lambda: SimpleNamespace(count=lambda *a, **k: tokens))
    policy = object.__new__(visual_model.VisualPolicy)
    policy.max_batch_size = 2
    policy.max_batch_input_tokens = cap
    policy.max_context_tokens = 32768
    policy.max_new_tokens = 384
    with pytest.raises(RuntimeError, match="batch exceeds"):
        policy.generate([{"messages": [], "images": []} for _ in range(batch)])
