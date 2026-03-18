# from __future__ import annotations

# import networkx as nx
# from typing import List

# from code_atlas.core.models import NodeKind


# import networkx as nx
# from typing import List, Set

# from code_atlas.core.models import NodeKind
from __future__ import annotations

import networkx as nx
from typing import List, Set

from code_atlas.core.models import NodeKind


def find_dead_functions(graph: nx.DiGraph) -> List[str]:
    """
    Detect dead functions using reachability analysis.

    Steps:
    1. Identify entry points
    2. Traverse graph from entry points
    3. Any function not reachable is dead
    """

    entry_nodes: Set[str] = set()

    # ---------- identify entry points ----------

    for node_id, data in graph.nodes(data=True):

        kind = data.get("kind")
        name = data.get("name")

        # exported/public API
        if data.get("is_exported"):
            entry_nodes.add(node_id)

        # modules are roots
        if kind == NodeKind.MODULE.value:
            entry_nodes.add(node_id)

        # main functions
        if name == "main":
            entry_nodes.add(node_id)

        # React component heuristic
        if kind == NodeKind.FUNCTION.value and name and name[0].isupper():
            entry_nodes.add(node_id)

    # ---------- graph traversal ----------

    reachable: Set[str] = set()

    stack = list(entry_nodes)

    while stack:
        node = stack.pop()

        if node in reachable:
            continue

        reachable.add(node)

        for neighbor in graph.successors(node):
            stack.append(neighbor)

    # ---------- find dead nodes ----------

    dead_nodes: List[str] = []

    for node_id, data in graph.nodes(data=True):

        kind = data.get("kind")

        if kind not in (
            NodeKind.FUNCTION.value,
            NodeKind.METHOD.value,
        ):
            continue

        if node_id not in reachable:
            dead_nodes.append(node_id)

    return dead_nodes