"""Graphs given as {node: [nodes it points to]}."""


def find_cycle(edges):
    """The first cycle found as a path [a, b, ..., a], or None.

    Edges to a node missing from `edges`, or to the node itself, are ignored."""
    state = {}

    def visit(node, path):
        state[node] = 1
        for dep in edges[node]:
            if dep not in edges or dep == node:
                continue
            if state.get(dep) == 1:
                return path + [node, dep]
            if dep not in state:
                found = visit(dep, path + [node])
                if found:
                    return found
        state[node] = 2
        return None

    for node in edges:
        if node not in state:
            found = visit(node, [])
            if found:
                return found[found.index(found[-1]):]
    return None
