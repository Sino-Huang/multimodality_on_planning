"""Compare task contexts modulo object names, preserving relations and goal scope."""

from collections import Counter

import networkx as nx


def atom_parts(atom):
    name, _, arguments = atom.partition("(")
    return name, tuple(arguments.rstrip(")").split(",")) if arguments else ()


def context_shape(context):
    """Cheap exact invariants used only to skip impossible isomorphisms."""
    kinds = tuple(sorted((k, len(v)) for k, v in context["objects_by_type"].items()))
    facts = []
    for role in ("static_initial_facts", "initial_dynamic_atoms", "initial_dynamic_fluents"):
        counts = Counter(atom_parts(f.split("=", 1)[0])[0] for f in context[role])
        facts.append((role, tuple(sorted(counts.items()))))
    return kinds, tuple(facts)


def context_graph(context):
    graph = nx.DiGraph()

    def node(label):
        key = len(graph)
        graph.add_node(key, label=label)
        return key

    objects = {}
    for kind, names in context["objects_by_type"].items():
        for name in names:
            objects[name] = node(("object", kind))

    def atom(name, arguments, role, scope):
        parent = node((role, name))
        for index, arg in enumerate(arguments):
            slot = node(("argument", index))
            graph.add_edge(parent, slot)
            target = scope.get(arg, objects.get(arg))
            if target is None:
                raise ValueError(f"unknown object or unbound goal variable: {arg}")
            graph.add_edge(slot, target)
        return parent

    for role in ("static_initial_facts", "initial_dynamic_atoms", "initial_dynamic_fluents"):
        for fact in context[role]:
            term, _, value = fact.partition("=")
            name, arguments = atom_parts(term)
            atom(name, arguments, (role, value), {})

    def goal(formula, scope):
        op = formula[0]
        if op == "atom":
            return atom(formula[1], formula[2], "goal_atom", scope)
        parent = node(("goal", op))
        if op in ("and", "or"):
            for child in formula[1]:
                graph.add_edge(parent, goal(child, scope))
        elif op == "not":
            graph.add_edge(parent, goal(formula[1], scope))
        elif op in ("forall", "exists"):
            local = dict(scope)
            for name, kind in formula[1]:
                variable = node(("variable", kind))
                graph.add_edge(parent, variable)
                local[name] = variable
            graph.add_edge(parent, goal(formula[2], local))
        elif op not in ("true", "false"):
            raise ValueError(f"unsupported goal expression for exact isomorphism: {op}")
        return parent

    goal(context["canonical_goal"], {})
    return graph


def same_instance(left, right):
    if context_shape(left) != context_shape(right):
        return False
    return nx.is_isomorphic(context_graph(left), context_graph(right), node_match=lambda a, b: a["label"] == b["label"])
