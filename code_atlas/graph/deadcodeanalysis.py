from __future__ import annotations

import networkx as nx
from typing import List

from code_atlas.core.models import NodeKind


def find_dead_functions(graph):

    dead = []

    for node, data in graph.nodes(data=True):

        kind = data.get("kind")
        name = data.get("name")
        file = data.get("file")

        if kind not in ("function", "method"):
            continue

        # skip CLI entrypoints
        if name in {"main"}:
            continue

        # skip tests
        if file and "tests" in file:
            continue

        if graph.in_degree(node) == 0:
            dead.append(node)

    return dead