from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

Atom = tuple[str, ...]
BranchOrder = Literal["forward", "reverse"]
JsonValue: TypeAlias = str | int | bool | list["JsonValue"] | dict[str, "JsonValue"] | None


@dataclass(frozen=True, slots=True)
class CanonicalGraphError(RuntimeError):
    code: str

    def __str__(self) -> str:
        return self.code


def _canonical(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class Edge:
    source: int
    target: int
    label: int


@dataclass(frozen=True, slots=True)
class Relation:
    sort: Literal["goal", "init"]
    predicate: str
    arguments: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CanonicalGraph:
    object_names: tuple[str, ...]
    relations: tuple[Relation, ...]
    edges: tuple[Edge, ...]

    @property
    def vertex_count(self) -> int:
        return len(self.object_names) + len(self.relations)

    def relation_vertex(self, relation: Relation) -> int:
        return len(self.object_names) + self.relations.index(relation)


@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    leaf_bytes: bytes
    candidate_id: str
    explored_branches: int


@dataclass(frozen=True, slots=True)
class _SearchResult:
    leaf: bytes
    branches: int


def identity_graph(
    object_names: tuple[str, ...],
    init_atoms: frozenset[Atom],
    goal_atoms: frozenset[Atom],
) -> CanonicalGraph:
    object_index = {name: index for index, name in enumerate(object_names)}
    atom_groups: tuple[tuple[Literal["goal", "init"], frozenset[Atom]], ...] = (
        ("init", init_atoms),
        ("goal", goal_atoms),
    )
    relations = tuple(
        Relation(sort, atom[0], tuple(object_index[name] for name in atom[1:]))
        for sort, atoms in atom_groups
        for atom in sorted(atoms)
    )
    edges = tuple(
        Edge(len(object_names) + relation_index, target, label)
        for relation_index, relation in enumerate(relations)
        for label, target in enumerate(relation.arguments)
    )
    return CanonicalGraph(object_names, relations, edges)


def initial_color_descriptors(graph: CanonicalGraph) -> tuple[bytes, ...]:
    object_descriptors = (_canonical("object"),) * len(graph.object_names)
    relation_descriptors = tuple(
        _canonical({"arity": len(relation.arguments), "predicate": relation.predicate, "sort": relation.sort})
        for relation in graph.relations
    )
    return object_descriptors + relation_descriptors


def _color_ids(descriptors: tuple[bytes, ...]) -> tuple[int, ...]:
    identifiers = {descriptor: index for index, descriptor in enumerate(sorted(set(descriptors)))}
    return tuple(identifiers[descriptor] for descriptor in descriptors)


def initial_colors(graph: CanonicalGraph) -> tuple[int, ...]:
    return _color_ids(initial_color_descriptors(graph))


def individualize_colors(colors: tuple[int, ...], selected: int, depth: int) -> tuple[int, ...]:
    descriptors = tuple(
        _canonical({"individualization_depth": depth})
        if index == selected
        else _canonical({"stable_color": color})
        for index, color in enumerate(colors)
    )
    return _color_ids(descriptors)


def _refinement_round(graph: CanonicalGraph, colors: tuple[int, ...]) -> tuple[int, ...]:
    incoming: list[list[tuple[int, int]]] = [[] for _ in colors]
    outgoing: list[list[tuple[int, int]]] = [[] for _ in colors]
    for edge in graph.edges:
        outgoing[edge.source].append((edge.label, colors[edge.target]))
        incoming[edge.target].append((edge.label, colors[edge.source]))
    signatures = tuple(
        _canonical({
            "color": color,
            "incoming": [list(item) for item in sorted(incoming[index])],
            "outgoing": [list(item) for item in sorted(outgoing[index])],
        })
        for index, color in enumerate(colors)
    )
    return _color_ids(signatures)


def _same_partition(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    return all((left[a] == left[b]) == (right[a] == right[b]) for a in range(len(left)) for b in range(a))


def refine_colors(graph: CanonicalGraph, colors: tuple[int, ...]) -> tuple[int, ...]:
    current = colors
    while True:
        refined = _refinement_round(graph, current)
        if _same_partition(current, refined):
            return refined
        current = refined


def _leaf_bytes(graph: CanonicalGraph, colors: tuple[int, ...]) -> bytes:
    object_order = sorted(range(len(graph.object_names)), key=colors.__getitem__)
    labels = {vertex: f"o{index:02d}" for index, vertex in enumerate(object_order)}
    relation_records: list[dict[str, JsonValue]] = []
    for relation in graph.relations:
        arguments: list[JsonValue] = [
            {"label": f"arg{label}", "object": labels[vertex]}
            for label, vertex in enumerate(relation.arguments)
        ]
        relation_records.append({"arguments": arguments, "color": f"{relation.sort}:{relation.predicate}"})
    relation_records.sort(key=_canonical)
    objects: list[JsonValue] = [f"o{index:02d}" for index in range(len(object_order))]
    relations: list[JsonValue] = list(relation_records)
    payload: dict[str, JsonValue] = {"objects": objects, "relations": relations}
    return _canonical(payload)


def _object_cell(colors: tuple[int, ...], object_count: int) -> tuple[int, ...] | None:
    cells: dict[int, list[int]] = defaultdict(list)
    for vertex in range(object_count):
        cells[colors[vertex]].append(vertex)
    candidates = [(color, tuple(vertices)) for color, vertices in cells.items() if len(vertices) > 1]
    return min(candidates)[1] if candidates else None


def _search(graph: CanonicalGraph, colors: tuple[int, ...], depth: int, order: BranchOrder) -> _SearchResult:
    stable = refine_colors(graph, colors)
    cell = _object_cell(stable, len(graph.object_names))
    if cell is None:
        return _SearchResult(_leaf_bytes(graph, stable), 1)
    members = cell if order == "forward" else tuple(reversed(cell))
    best: bytes | None = None
    branches = 0
    for member in members:
        result = _search(graph, individualize_colors(stable, member, depth), depth + 1, order)
        branches += result.branches
        if best is None or result.leaf < best:
            best = result.leaf
    if best is None:
        raise CanonicalGraphError("canonical_graph_no_branch")
    return _SearchResult(best, branches)


def canonicalize_graph(graph: CanonicalGraph, *, branch_order: BranchOrder = "forward") -> CanonicalizationResult:
    result = _search(graph, initial_colors(graph), 0, branch_order)
    return CanonicalizationResult(result.leaf, hashlib.sha256(result.leaf).hexdigest(), result.branches)


def canonical_leaf_bytes(graph: CanonicalGraph) -> bytes:
    return canonicalize_graph(graph).leaf_bytes


CANONICAL_LEAF_SCHEMA: Final = "cgas_canonical_graph_leaf_v1"
