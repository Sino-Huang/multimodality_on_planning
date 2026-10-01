"""Image regressors and rankers over planning-state scenes (#149 protocol §9).

A shared pretrained backbone (torchvision ResNet-18 or timm ViT-S/16) encodes the
128 px unlabelled state scene (resized to 224) and each of the task's goal pages
(resized to 384 x 512, embeddings averaged over pages). A fusion MLP on
``[z_scene, z_goal, z_scene * z_goal]`` emits one score per state; lower means
closer to the goal. Three targets: Huber regression on h* (dead ends excluded),
Huber regression on h_add, and a pairwise logistic ranker on within-menu pairs
with different h*. Training is fine-tuned end to end with AdamW; the epoch with
the lowest validation loss (task-grouped sha256 split) is kept.

BatchNorm layers stay in inference mode during fine-tuning (pretrained running
statistics, affine parameters trained): goal pages are encoded in small
per-task batches, so batch statistics would be degenerate and would make the
training and scoring paths diverge.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch import nn

BACKBONES = ("cnn", "vit")
TARGETS = ("hstar", "hadd", "rank")

SCHEMA = "image-heuristic-v1"
VIT_MODEL = "vit_small_patch16_224.augreg_in21k_ft_in1k"
SCENE_SOURCE_SIZE = 128
SCENE_SIZE = 224
GOAL_PAGE_SIZE = (384, 512)  # (width, height); pages are 768 x 1024
HIDDEN = 512
LR = 1e-4
WEIGHT_DECAY = 0.01
HUBER_DELTA = 1.0
SCORE_BATCH = 64
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
MODEL_FILE = "model.pt"
RESULT_FILE = "result.json"


@dataclass(frozen=True)
class HeuristicState:
    key: str
    task_id: str
    scene: str
    goal_pages: tuple[str, ...]
    hstar: float | None
    hadd: float


def validation_tasks(task_ids: Iterable[str]) -> set[str]:
    """Fixed task-grouped validation split: sha256(task id) mod 10 == 0."""
    return {task for task in task_ids if int(hashlib.sha256(task.encode("utf-8")).hexdigest(), 16) % 10 == 0}


def ranker_pairs(menus: Iterable[Sequence[str]], hstar: Mapping[str, float | None]) -> list[tuple[str, str, float]]:
    """All within-menu pairs with different, known h*.

    Each unordered pair appears once (first occurrence, canonical key order
    ``a < b``); the label is 1.0 when ``h*(a) > h*(b)``, i.e. the ranker should
    score ``a`` higher (farther from the goal).
    """
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str, float]] = []
    for menu in menus:
        for a, b in combinations(sorted(set(menu)), 2):
            if a not in hstar or b not in hstar:
                missing = a if a not in hstar else b
                raise ValueError(f"menu references unknown state key {missing!r}")
            ha, hb = hstar[a], hstar[b]
            if ha is None or hb is None or ha == hb or (a, b) in seen:
                continue
            seen.add((a, b))
            pairs.append((a, b, 1.0 if ha > hb else 0.0))
    return pairs


def data_fingerprint(states: Sequence[HeuristicState], menus: Sequence[Sequence[str]]) -> str:
    payload = {
        "states": [
            {**asdict(state), "goal_pages": list(state.goal_pages)} for state in sorted(states, key=lambda s: s.key)
        ],
        "menus": [list(menu) for menu in menus],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _configure_determinism() -> None:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


class _SpatialMean(nn.Module):
    """Deterministic replacement for ResNet's AdaptiveAvgPool2d((1, 1))."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x.mean(dim=(2, 3), keepdim=True)


def _build_backbone(name: str, *, pretrained: bool) -> tuple[nn.Module, int, tuple[float, ...], tuple[float, ...]]:
    if name == "cnn":
        import torchvision

        weights = torchvision.models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
        model = torchvision.models.resnet18(weights=weights)
        model.avgpool = _SpatialMean()
        model.fc = nn.Identity()
        return model, 512, IMAGENET_MEAN, IMAGENET_STD
    if name == "vit":
        import timm

        model = timm.create_model(VIT_MODEL, pretrained=pretrained, dynamic_img_size=True, num_classes=0)
        cfg = model.pretrained_cfg
        return model, int(model.num_features), tuple(cfg["mean"]), tuple(cfg["std"])
    raise ValueError(f"unknown backbone {name!r}; expected one of {BACKBONES}")


class _HeuristicNet(nn.Module):
    def __init__(self, backbone: str, *, pretrained: bool) -> None:
        super().__init__()
        self.backbone, dim, mean, std = _build_backbone(backbone, pretrained=pretrained)
        self.register_buffer("pixel_mean", torch.tensor(mean).view(1, 3, 1, 1), persistent=False)
        self.register_buffer("pixel_std", torch.tensor(std).view(1, 3, 1, 1), persistent=False)
        self.head = nn.Sequential(nn.Linear(3 * dim, HIDDEN), nn.ReLU(), nn.Linear(HIDDEN, 1))

    def train(self, mode: bool = True) -> _HeuristicNet:
        super().train(mode)
        for module in self.modules():
            if isinstance(module, nn.modules.batchnorm._BatchNorm):
                module.eval()
        return self

    def _normalize(self, pixels: torch.Tensor) -> torch.Tensor:
        return (pixels.float() / 255.0 - self.pixel_mean) / self.pixel_std

    def encode_scenes(self, scenes: torch.Tensor) -> torch.Tensor:
        x = F.interpolate(scenes.float(), size=(SCENE_SIZE, SCENE_SIZE), mode="bilinear", align_corners=False)
        return self.backbone(self._normalize(x))

    def encode_pages(self, pages: torch.Tensor) -> torch.Tensor:
        return self.backbone(self._normalize(pages))

    def fuse(self, z_scene: torch.Tensor, z_goal: torch.Tensor) -> torch.Tensor:
        return self.head(torch.cat([z_scene, z_goal, z_scene * z_goal], dim=-1)).squeeze(-1)


def _load_scene(path: Path) -> torch.Tensor:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
    if rgb.size != (SCENE_SOURCE_SIZE, SCENE_SOURCE_SIZE):
        raise ValueError(f"scene {path} is {rgb.size}, expected {SCENE_SOURCE_SIZE}x{SCENE_SOURCE_SIZE}")
    return torch.from_numpy(np.asarray(rgb).copy()).permute(2, 0, 1).contiguous()


def _load_goal_pages(paths: Sequence[str], root: Path) -> torch.Tensor:
    if not paths:
        raise ValueError("a task needs at least one goal page")
    pages = []
    for path in paths:
        with Image.open(root / path) as image:
            page = image.convert("RGB").resize(GOAL_PAGE_SIZE, Image.Resampling.BILINEAR)
        pages.append(torch.from_numpy(np.asarray(page).copy()).permute(2, 0, 1))
    return torch.stack(pages)


def _goal_embeddings(
    net: _HeuristicNet, tasks: Sequence[str], pages: Mapping[str, torch.Tensor], device: str
) -> torch.Tensor:
    """Mean page embedding per task, one backbone pass over all pages of ``tasks``."""
    stacked = torch.cat([pages[task] for task in tasks]).to(device)
    z = net.encode_pages(stacked)
    counts = [pages[task].shape[0] for task in tasks]
    return torch.stack([chunk.mean(dim=0) for chunk in torch.split(z, counts)])


def _score_states(
    net: _HeuristicNet,
    indices: Sequence[int],
    task_of: Sequence[str],
    scenes: Mapping[int, torch.Tensor],
    pages: Mapping[str, torch.Tensor],
    device: str,
    goal_memo: dict[str, torch.Tensor] | None = None,
) -> torch.Tensor:
    tasks = list(dict.fromkeys(task_of[i] for i in indices))
    if goal_memo is None:
        z_goal_tasks = _goal_embeddings(net, tasks, pages, device)
    else:
        missing = [task for task in tasks if task not in goal_memo]
        if missing:
            for task, z in zip(missing, _goal_embeddings(net, missing, pages, device), strict=True):
                goal_memo[task] = z
        z_goal_tasks = torch.stack([goal_memo[task] for task in tasks])
    slot = {task: n for n, task in enumerate(tasks)}
    z_goal = z_goal_tasks[torch.tensor([slot[task_of[i]] for i in indices], device=device)]
    z_scene = net.encode_scenes(torch.stack([scenes[i] for i in indices]).to(device))
    return net.fuse(z_scene, z_goal)


def _mixed_batches(
    items: Sequence[Any], task_of_item: Callable[[Any], str], batch_size: int, rng: random.Random
) -> list[list[Any]]:
    """Shuffled batches that mix a few tasks each, bounding goal-page passes per batch.

    Each task's items are shuffled and cut into chunks of ``batch_size // 4``;
    the chunks are shuffled globally and concatenated into batches.
    """
    by_task: dict[str, list[Any]] = {}
    for item in items:
        by_task.setdefault(task_of_item(item), []).append(item)
    chunk = max(1, batch_size // 4)
    chunks: list[list[Any]] = []
    for task in sorted(by_task):
        group = list(by_task[task])
        rng.shuffle(group)
        chunks.extend(group[k : k + chunk] for k in range(0, len(group), chunk))
    rng.shuffle(chunks)
    flat = [item for part in chunks for item in part]
    return [flat[k : k + batch_size] for k in range(0, len(flat), batch_size)]


def _ordered_batches(items: Sequence[Any], task_of_item: Callable[[Any], str], batch_size: int) -> list[list[Any]]:
    ordered = sorted(items, key=lambda item: task_of_item(item))
    return [ordered[k : k + batch_size] for k in range(0, len(ordered), batch_size)]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _library_versions() -> dict[str, str]:
    import PIL
    import timm
    import torchvision

    return {
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "timm": timm.__version__,
        "numpy": np.__version__,
        "pillow": PIL.__version__,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _reusable_result(output_dir: Path, identity: Mapping[str, Any]) -> dict | None:
    result_path = output_dir / RESULT_FILE
    model_path = output_dir / MODEL_FILE
    if not result_path.exists() or not model_path.exists():
        return None
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if any(result.get(field) != value for field, value in identity.items()):
        return None
    if result.get("weights_sha256") != _sha256_file(model_path):
        return None
    return result


def train_model(
    states: list[HeuristicState],
    menus: list[list[str]],
    *,
    backbone: str,
    target: str,
    seed: int,
    output_dir: Path,
    root: Path,
    device: str = "cuda:0",
    epochs: int = 20,
    batch_size: int = 64,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    if backbone not in BACKBONES:
        raise ValueError(f"unknown backbone {backbone!r}; expected one of {BACKBONES}")
    if target not in TARGETS:
        raise ValueError(f"unknown target {target!r}; expected one of {TARGETS}")
    output_dir, root = Path(output_dir), Path(root)
    identity = {
        "schema": SCHEMA,
        "backbone": backbone,
        "target": target,
        "seed": seed,
        "epochs": epochs,
        "batch_size": batch_size,
        "data_sha256": data_fingerprint(states, menus),
    }
    reused = _reusable_result(output_dir, identity)
    if reused is not None:
        return reused

    keys = [state.key for state in states]
    if len(set(keys)) != len(keys):
        raise ValueError("state keys must be unique")
    index = {key: n for n, key in enumerate(keys)}
    task_of = [state.task_id for state in states]
    goal_paths: dict[str, tuple[str, ...]] = {}
    for state in states:
        if goal_paths.setdefault(state.task_id, tuple(state.goal_pages)) != tuple(state.goal_pages):
            raise ValueError(f"task {state.task_id!r} has inconsistent goal pages")
    validation = validation_tasks(goal_paths)

    # Examples: (state index, regression target) or (i, j, label) for the ranker.
    if target == "rank":
        pairs = ranker_pairs(menus, {state.key: state.hstar for state in states})
        examples: list[tuple] = []
        for a, b, label in pairs:
            i, j = index[a], index[b]
            if task_of[i] != task_of[j]:
                raise ValueError(f"menu pair {a!r}/{b!r} spans two tasks")
            examples.append((i, j, label))
    else:
        field = "hstar" if target == "hstar" else "hadd"
        examples = [
            (n, float(getattr(state, field))) for n, state in enumerate(states) if getattr(state, field) is not None
        ]

    def task_of_example(example: tuple) -> str:
        return task_of[example[0]]

    train_examples = [ex for ex in examples if task_of_example(ex) not in validation]
    val_examples = [ex for ex in examples if task_of_example(ex) in validation]
    if not train_examples or not val_examples:
        raise ValueError(f"empty split: {len(train_examples)} train / {len(val_examples)} validation examples")

    used_states = sorted({n for ex in examples for n in (ex[:2] if target == "rank" else ex[:1])})
    scenes = {n: _load_scene(root / states[n].scene) for n in used_states}
    pages = {task: _load_goal_pages(goal_paths[task], root) for task in sorted({task_of[n] for n in used_states})}

    _configure_determinism()
    _seed_everything(seed)
    net = _HeuristicNet(backbone, pretrained=True).to(device)
    optimizer = torch.optim.AdamW(net.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    rng = random.Random(seed)

    def batch_loss(batch: list[tuple], goal_memo: dict | None, reduction: str) -> tuple[torch.Tensor, torch.Tensor]:
        """Return (loss, per-example metric numerator): abs error for regressors, correctness for ranker."""
        if target == "rank":
            members = list(dict.fromkeys(n for i, j, _ in batch for n in (i, j)))
            slot = {n: k for k, n in enumerate(members)}
            scores = _score_states(net, members, task_of, scenes, pages, device, goal_memo)
            first = torch.tensor([slot[i] for i, _, _ in batch], device=device)
            second = torch.tensor([slot[j] for _, j, _ in batch], device=device)
            labels = torch.tensor([label for _, _, label in batch], device=device)
            logits = scores[first] - scores[second]
            loss = F.binary_cross_entropy_with_logits(logits, labels, reduction=reduction)
            return loss, ((logits > 0).float() == labels).float()
        members = [n for n, _ in batch]
        values = torch.tensor([value for _, value in batch], device=device)
        preds = _score_states(net, members, task_of, scenes, pages, device, goal_memo)
        loss = F.huber_loss(preds, values, delta=HUBER_DELTA, reduction=reduction)
        return loss, (preds - values).abs()

    metric_name = "val_pairwise_accuracy" if target == "rank" else "val_mae"
    history: list[dict] = []
    best_epoch, best_loss = 0, float("inf")
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / MODEL_FILE
    for epoch in range(1, epochs + 1):
        net.train()
        train_total = 0.0
        for batch in _mixed_batches(train_examples, task_of_example, batch_size, rng):
            loss, _ = batch_loss(batch, None, "mean")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            train_total += float(loss.detach()) * len(batch)
        net.eval()
        val_total, metric_total, goal_memo = 0.0, 0.0, {}
        with torch.no_grad():
            for batch in _ordered_batches(val_examples, task_of_example, batch_size):
                loss, metric = batch_loss(batch, goal_memo, "sum")
                val_total += float(loss)
                metric_total += float(metric.sum())
        row = {
            "epoch": epoch,
            "train_loss": train_total / len(train_examples),
            "val_loss": val_total / len(val_examples),
            metric_name: metric_total / len(val_examples),
        }
        history.append(row)
        if row["val_loss"] < best_loss:
            best_epoch, best_loss = epoch, row["val_loss"]
            tmp = model_path.with_suffix(".pt.tmp")
            torch.save(net.state_dict(), tmp)
            tmp.replace(model_path)
        if progress is not None:
            progress({"backbone": backbone, "target": target, "seed": seed, **row, "best_epoch": best_epoch})

    best = history[best_epoch - 1]
    result = {
        **identity,
        "best_epoch": best_epoch,
        "best_val_loss": best["val_loss"],
        metric_name: best[metric_name],
        "history": history,
        "n_train": len(train_examples),
        "n_val": len(val_examples),
        "n_train_tasks": len({task_of_example(ex) for ex in train_examples}),
        "n_val_tasks": len({task_of_example(ex) for ex in val_examples}),
        "validation_tasks": sorted({task_of_example(ex) for ex in val_examples}),
        "config": {
            "scene_size": SCENE_SIZE,
            "goal_page_size_wh": list(GOAL_PAGE_SIZE),
            "hidden": HIDDEN,
            "optimizer": {"name": "AdamW", "lr": LR, "weight_decay": WEIGHT_DECAY},
            "loss": "bce_logits_pairwise" if target == "rank" else f"huber(delta={HUBER_DELTA})",
            "vit_model": VIT_MODEL if backbone == "vit" else None,
            "batchnorm": "frozen running statistics",
        },
        "versions": _library_versions(),
        "weights_sha256": _sha256_file(model_path),
    }
    _write_json(output_dir / RESULT_FILE, result)
    return result


class HeuristicModel:
    """Frozen scorer: lower score = closer to the goal."""

    def __init__(self, net: _HeuristicNet, device: str, result: Mapping[str, Any]) -> None:
        self.net = net
        self.device = device
        self.result = dict(result)
        self._goal_cache: dict[tuple[str, tuple[str, ...]], torch.Tensor] = {}

    def _goal_embedding(self, goal_pages: tuple[str, ...], root: Path) -> torch.Tensor:
        key = (str(root), tuple(goal_pages))
        if key not in self._goal_cache:
            pages = _load_goal_pages(goal_pages, root).to(self.device)
            self._goal_cache[key] = self.net.encode_pages(pages).mean(dim=0)
        return self._goal_cache[key]

    def score(self, scenes: list[str], goal_pages: tuple[str, ...], root: Path) -> list[float]:
        root = Path(root)
        scores: list[float] = []
        with torch.no_grad():
            z_goal = self._goal_embedding(tuple(goal_pages), root)
            for start in range(0, len(scenes), SCORE_BATCH):
                chunk = scenes[start : start + SCORE_BATCH]
                pixels = torch.stack([_load_scene(root / path) for path in chunk]).to(self.device)
                z_scene = self.net.encode_scenes(pixels)
                scores.extend(self.net.fuse(z_scene, z_goal.expand(len(chunk), -1)).tolist())
        return scores


def load_model(output_dir: Path, device: str) -> HeuristicModel:
    output_dir = Path(output_dir)
    result = json.loads((output_dir / RESULT_FILE).read_text(encoding="utf-8"))
    model_path = output_dir / MODEL_FILE
    if _sha256_file(model_path) != result["weights_sha256"]:
        raise ValueError(f"{model_path} does not match the weights sha256 recorded in {RESULT_FILE}")
    _configure_determinism()
    net = _HeuristicNet(result["backbone"], pretrained=False)
    net.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
    net.to(device).eval()
    return HeuristicModel(net, device, result)
