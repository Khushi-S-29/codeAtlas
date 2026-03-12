from __future__ import annotations

import networkx as nx
from typing import List

from code_atlas.core.models import NodeKind


def find_dead_functions(graph: nx.DiGraph) -> List[str]:
    """
    Identify potentially dead functions and methods.

    A node is considered dead if:
    - It represents a function or method
    - It has no incoming edges (nothing calls it)
    - It is not explicitly exported (public API)
    """

    dead_nodes: List[str] = []

    for node_id, data in graph.nodes(data=True):

        kind = data.get("kind")

        # only analyze functions + methods
        if kind not in (NodeKind.FUNCTION.value, NodeKind.METHOD.value):
            continue

        # exported/public functions are entrypoints
        if data.get("is_exported"):
            continue

        # if nobody calls this function → potential dead code
        if graph.in_degree(node_id) == 0:
            dead_nodes.append(node_id)

    return dead_nodes