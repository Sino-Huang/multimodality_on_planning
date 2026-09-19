from __future__ import annotations

from scripts.smoke_qwen_text_policy import _initialize_cuda_memory_stats


class _FakeCuda:
    def __init__(self) -> None:
        self.initialized = False
        self.reset_device: int | None = None

    def reset_peak_memory_stats(self, device_index: int) -> None:
        if not self.initialized:
            raise RuntimeError("Invalid device argument")
        self.reset_device = device_index


class _FakeTorch:
    def __init__(self) -> None:
        self.cuda = _FakeCuda()

    def empty(self, _size: int, *, device: str) -> object:
        assert device == "cuda:1"
        self.cuda.initialized = True
        return object()


def test_cuda_allocator_is_initialized_before_peak_stats_are_reset() -> None:
    torch = _FakeTorch()

    _initialize_cuda_memory_stats(torch, device="cuda:1", device_index=1)

    assert torch.cuda.initialized is True
    assert torch.cuda.reset_device == 1
