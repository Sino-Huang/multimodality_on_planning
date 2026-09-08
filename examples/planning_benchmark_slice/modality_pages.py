"""Complete annotation pages and on-demand stored-scene composition for #72."""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .source_goal import goal_blocks

CONTRACT_ID = "issue-72-readable-pages-v1"
PAGE_SIZE = (768, 1024)
FONT_SIZE = 24
CACHE_BYTES = 64 * 1024 * 1024
ROLES = ("task-context", "current-state", "goal")
LEGEND = (
    "Complete task-context, current-state, then partial-goal pages are attached on every call. "
    "Facts list ordered arguments and full names. Absent state facts are false; unspecified goal facts "
    "are unconstrained. Scene geometry is illustrative. Goal block IDs name lexical scopes: ALL requires "
    "all children; ANY requires some child; NOT negates its child. Quantifiers bind the typed variables "
    "in their children. A continuation repeats its block label, not its semantic content. "
    "@type-T@(x) means object x has type T. Text broken across lines joins without added characters."
)


@dataclass(frozen=True)
class PageRecipe:
    role: str
    index: int
    total: int
    # Each fragment refers to one complete semantic block, with exact character offsets.
    fragments: tuple[dict[str, Any], ...]
    scene: str | None = None

    def to_dict(self):
        return asdict(self)


@lru_cache(maxsize=1)
def font():
    return ImageFont.truetype("DejaVuSans.ttf", FONT_SIZE)


@lru_cache(maxsize=8192)
def wrap(text: str, width: int) -> tuple[str, ...]:
    """Lossless measured wrapping, including identifiers longer than one line."""
    if not text:
        return ("",)
    lines = []
    while text:
        low, high = 1, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if font().getlength(text[:middle]) <= width:
                low = middle
            else:
                high = middle - 1
        if font().getlength(text[:low]) > width:
            raise ValueError("one character exceeds page width")
        end = low
        if end < len(text):
            boundary = max(text.rfind(" ", 0, end), text.rfind(",", 0, end))
            if boundary >= end // 2:
                end = boundary + 1
        lines.append(text[:end])
        text = text[end:]
    return tuple(lines)


def fact_blocks(context: dict[str, Any], state: dict[str, Any], source: dict[str, Any]):
    """One semantic projection supplies both text and drawing recipes."""
    sections = {
        "objects": [f"{name} : {kind}" for kind, names in source["objects_by_type"].items() for name in names],
        "types": [f"{kind} : {parent or 'object'}" for kind, parent in sorted(source["type_parents"].items())],
        "static": context["static_initial_facts"],
        "initial": context["initial_dynamic_atoms"],
        "initial_fluent": context["initial_dynamic_fluents"],
    }

    def blocks(parts):
        result = []
        for section, facts in parts.items():
            groups = {}
            for fact in sorted(facts):
                predicate = fact.partition("(")[0] if section not in ("objects", "types") else section
                groups.setdefault(predicate, []).append(fact)
            for index, (predicate, grouped) in enumerate(groups.items()):
                result.append(
                    {"id": f"{section}:{index}", "label": f"{section} / {predicate}", "text": "; ".join(grouped)}
                )
        return result

    return {
        "task-context": blocks(sections),
        "current-state": blocks({"state": state["atoms"], "state_fluent": state["fluents"]}),
        "goal": goal_blocks(source["source_goal"]),
    }


def paginate(role: str, blocks: list[dict[str, str]], scene: str | None = None) -> tuple[PageRecipe, ...]:
    if role not in ROLES or (scene is not None and role != "current-state"):
        raise ValueError("invalid page role / scene binding")
    columns = 1 if role == "goal" else 2
    width = 720 if columns == 1 else 348
    pages: list[list[dict[str, Any]]] = [[]]
    column, y = 0, 220 if scene else 72

    def advance():
        nonlocal column, y
        column += 1
        if column == columns:
            column = 0
            pages.append([])
        y = 220 if scene and len(pages) == 1 else 72

    for block in blocks:
        lines = wrap(block["text"], width - 16)
        offset = 0
        part = 0
        while lines:
            label = block["label"] + (" [continued]" if part else "")
            heading = wrap(label, width - 16)
            room = (980 - y) // 32 - len(heading) - 1
            if room < 1:
                advance()
                if (980 - y) // 32 - len(heading) - 1 < 1:
                    raise ValueError("block label cannot fit at fixed font size")
                continue
            shown, lines = lines[:room], lines[room:]
            fragment = {
                "id": block["id"],
                "offset": offset,
                "text": "".join(shown),
                "label": label,
                "lines": list(shown),
                "heading": list(heading),
                "x": 24 + column * 372,
                "y": y,
                "width": width,
            }
            pages[-1].append(fragment)
            y += (len(heading) + len(shown) + 1) * 32
            offset += len(fragment["text"])
            part += 1
    result = tuple(
        PageRecipe(role, i, len(pages), tuple(items), scene if i == 0 else None) for i, items in enumerate(pages)
    )
    validate_pages(blocks, result)
    return result


def validate_pages(blocks: list[dict[str, str]], pages: tuple[PageRecipe, ...]) -> None:
    exposed = {block["id"]: "" for block in blocks}
    seen = set()
    for page in pages:
        for fragment in page.fragments:
            key = fragment["id"]
            if key not in exposed or len(exposed[key]) != fragment["offset"] or (key in seen and not fragment["text"]):
                raise ValueError("missing, duplicated or reordered semantic fragment")
            if "".join(fragment["lines"]) != fragment["text"]:
                raise ValueError("drawing text differs from semantic fragment")
            exposed[key] += fragment["text"]
            seen.add(key)
    if len(exposed) != len(blocks) or seen != set(exposed) or any(exposed[b["id"]] != b["text"] for b in blocks):
        raise ValueError("pages do not expose complete semantics")


def compose_page(page: PageRecipe, root: Path) -> Image.Image:
    canvas = Image.new("RGB", PAGE_SIZE, "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 20), f"{page.role.upper()}  {page.index + 1}/{page.total}", font=font(), fill="black")
    if page.scene:
        with Image.open(root / page.scene) as scene:
            if scene.size != (128, 128):
                raise ValueError("stored scene must remain 128 x 128")
            canvas.paste(scene.convert("RGB"), (24, 72))
        draw.text((172, 100), "Illustrative scene", font=font(), fill="black")
    for fragment in page.fragments:
        x, y, width = fragment["x"], fragment["y"], fragment["width"]
        height = 32 * (len(fragment["heading"]) + len(fragment["lines"]))
        draw.rectangle((x, y, x + width, y + height), fill="#eef2f7", outline="#536174")
        for line in (*fragment["heading"], *fragment["lines"]):
            draw.text((x + 8, y + 2), line, font=font(), fill="black")
            y += 32
    return canvas


class StatePageCache:
    """Per-process 64 MiB LRU; task/state/page IDs, never content hashes."""

    def __init__(self, root: Path, capacity: int = CACHE_BYTES):
        self.root, self.capacity = root, capacity
        self.bytes = 0
        self.pages: OrderedDict[tuple[str, int, int], Image.Image] = OrderedDict()

    def get(self, task_id: str, state_id: int, page: PageRecipe) -> Image.Image:
        key = (task_id, state_id, page.index)
        if page.role != "current-state":
            raise ValueError("state cache requires current-state page")
        if key in self.pages:
            self.pages.move_to_end(key)
            return self.pages[key].copy()
        image = compose_page(page, self.root)
        size = image.width * image.height * 3
        while self.pages and self.bytes + size > self.capacity:
            _, old = self.pages.popitem(last=False)
            self.bytes -= old.width * old.height * 3
            old.close()
        if size <= self.capacity:
            self.pages[key] = image.copy()
            self.bytes += size
        return image


@lru_cache(maxsize=1)
def shared_state_page_cache(root: Path) -> StatePageCache:
    """One 64 MiB cache shared by corpus and concurrent live views in a worker."""
    return StatePageCache(root)


def project_messages(
    raw: dict[str, Any], algorithm: str, modality: str, blocks: dict[str, Any], images: list[tuple[str, Any]]
) -> list[dict[str, Any]]:
    """Retain the family builder's common input and replace only modality semantics."""
    from .best_first_model_input import serialize_best_first_message_prefix
    from .bfws_model_input import bfws_text_policy_training_messages
    from .qwen_text_policy import qwen_text_policy_training_messages

    payload = json.loads(json.dumps(raw))
    if algorithm == "best_first_width":
        # Candidate action arguments and set deltas use this exact symbol table.
        payload["candidate_object_symbols"] = payload["task_context"]["objects"]
        payload["observation"]["state"].pop("atoms", None)
        payload["observation"]["state"].pop("fluents", None)
    payload.pop("task_context", None)
    payload.pop("goal_atoms", None)
    for field in ("current", "observation", "expanded_state"):
        if isinstance(payload.get(field), dict):
            for key in ("state_atoms", "state_facts", "atoms", "fluents", "state_fluents", "goal_atoms", "modality"):
                payload[field].pop(key, None)
    payload["representation"] = modality
    payload["view_legend"] = LEGEND
    if modality != "visual-state":
        payload["semantic_blocks"] = blocks
    builder = (
        serialize_best_first_message_prefix
        if algorithm.startswith("best_first_add")
        else (
            bfws_text_policy_training_messages
            if algorithm == "best_first_width"
            else qwen_text_policy_training_messages if algorithm == "bfs" else None
        )
    )
    if builder is None:
        raise ValueError(f"unsupported family: {algorithm}")
    messages: list[dict[str, Any]] = [dict(message) for message in builder(payload)]
    content: list[dict[str, Any]] = [{"type": "text", "text": messages[-1]["content"]}]
    if modality != "text-state":
        for role, image in images:
            content.extend([{"type": "text", "text": f"Page role: {role}"}, {"type": "image", "image": image}])
    messages[-1] = {"role": "user", "content": content}
    return messages


@dataclass(frozen=True)
class ObservationPage:
    role: str
    index: int
    image: Image.Image


@dataclass(frozen=True)
class PagedModalityObservation:
    """Ordered, role-labelled page collection attached in full on every model call."""

    modality: str
    messages: list[dict[str, Any]]
    pages: tuple[ObservationPage, ...]
    input_tokens: int


class ModalityViewStore:
    """Consume an approved successor; original two-image freezes remain unchanged."""

    def __init__(self, root: Path, report_path: Path):
        from .modality_view_panel import load_view_panel
        from .modality_view_preparation import CONTRACT, require_approval
        from .scene_assets import read_json

        report = read_json(report_path)
        contract = CONTRACT
        if report.get("contract", {}).get("panel_manifest"):
            _, contract = load_view_panel(root, root / report["contract"]["panel_manifest"])
        if (
            report.get("contract") != contract
            or report.get("counts") != contract["expected"]
            or not report.get("model_input_ready")
            or report.get("outcome") != "PASS"
        ):
            raise ValueError("view store requires complete authorized materialization")
        qualification = read_json(Path(report["qualification_report"]))
        require_approval(report["binding"]["approval"], qualification, report_path.parent, contract)
        self.root = root
        self.context = report["approved_context"]
        self.manifests = {r["task_id"]: r["manifest"] for r in report["results"]}
        if len(self.manifests) != contract["expected"]["tasks"] or not report.get("complete_selected_coverage"):
            raise ValueError("view store task coverage is incomplete")
        self.cache = shared_state_page_cache(root)
        self._task_id = None
        self._manifest: dict[str, Any] | None = None
        self._catalog: dict[str, Any] | None = None

    def observations(
        self, task_id: str, algorithm: str, decision_index: int, raw: dict
    ) -> tuple[PagedModalityObservation, ...]:
        from .modality_view_preparation import OUTPUT_TOKENS, frozen_processor, validate_process_state
        from .scene_assets import read_json

        if self._task_id != task_id:
            self._manifest = read_json(self.root / self.manifests[task_id])
            assert self._manifest is not None
            self._catalog = read_json(self.root / self._manifest["scene_catalog"])
            self._task_id = task_id
        manifest, catalog = self._manifest, self._catalog
        assert manifest is not None and catalog is not None
        decision = next(d for d in manifest["decisions"] if d["algorithm"] == algorithm and d["index"] == decision_index)
        state_index = decision["state"]
        validate_process_state(raw, algorithm, catalog["states"][state_index])
        blocks = fact_blocks(catalog["task_context"], catalog["states"][state_index], manifest["source"])
        pages = []
        for role, bound_state, index in decision["input_pages"]:
            if role == "current-state":
                if bound_state != state_index:
                    raise ValueError("future-image leakage in decision binding")
                recipe = PageRecipe(**manifest["state_recipes"][state_index][index])
                image = self.cache.get(task_id, state_index, recipe)
            else:
                with Image.open(self.root / manifest["reusable_pages"][role][index]) as stored:
                    image = stored.convert("RGB")
            pages.append(ObservationPage(role, index, image))
        observations = []
        for modality in ("text-state", "visual-state", "multimodal-state"):
            messages = project_messages(raw, algorithm, modality, blocks, [(p.role, p.image) for p in pages])
            count = frozen_processor().count(messages)
            if count + OUTPUT_TOKENS > self.context:
                raise ValueError("VALID_STOP: complete observation exceeds approved context")
            observations.append(
                PagedModalityObservation(
                    modality,
                    messages,
                    () if modality == "text-state" else tuple(pages),
                    count,
                )
            )
        return tuple(observations)
