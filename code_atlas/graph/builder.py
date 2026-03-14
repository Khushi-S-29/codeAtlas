from __future__ import annotations

import networkx as nx
from typing import Iterable

from code_atlas.parsing.ir_store import IRStore
from code_atlas.core.models import IRNode
from code_atlas.graph.schema import EdgeType


class CodeGraphBuilder:
    """
    Builds a directed dependency graph from IR nodes.

    Nodes represent structural code elements:
        modules, classes, functions, methods, imports

    Edges represent relationships:
        CALLS, IMPORTS, DEFINES, INHERITS
    """

    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self.store = IRStore(repo_id)
        self.graph = nx.DiGraph()

    def build(self) -> nx.DiGraph:
        """
        Main entrypoint for graph construction.
        """
        nodes = self.store.load_all()

        self._add_nodes(nodes)
        self._add_call_edges(nodes)
        self._add_import_edges(nodes)
        self._add_class_edges(nodes)

        return self.graph

    # ---------- NODE CREATION ----------

    def _add_nodes(self, nodes: Iterable[IRNode]) -> None:
        """
        Add IR nodes as graph nodes.
        """
        for node in nodes:
            self.graph.add_node(
                node.id,
                name=node.name,
                kind=node.kind,
                file=node.file_path,
                start_line=node.start_line,
                end_line=node.end_line,
                language=node.language,
                is_exported=getattr(node, "is_exported", False),
            )

    # ---------- CALL RELATIONSHIPS ----------

    def _add_call_edges(self, nodes: Iterable[IRNode]) -> None:

        name_to_ids = {}

    # build lookup
        for node in nodes:
            name_to_ids.setdefault(node.name, []).append(node.id)

    # add edges
        for node in nodes:

            if not node.calls:
                continue

            for call in node.calls:

             leaf = call.split(".")[-1]

             targets = name_to_ids.get(call) or name_to_ids.get(leaf)

             if targets:
                for target in targets:
                    self.graph.add_edge(
                        node.id,
                        target,
                        type=EdgeType.CALLS.value,
                    )

    # ---------- IMPORT RELATIONSHIPS ----------

    def _add_import_edges(self, nodes: Iterable[IRNode]) -> None:
        """
        Create IMPORT edges.
        """
        name_to_id = {node.name: node.id for node in nodes}

        for node in nodes:
            if not node.imports:
                continue

            for imp in node.imports:
                target = name_to_id.get(imp)

                if target:
                    self.graph.add_edge(
                        node.id,
                        target,
                        type=EdgeType.IMPORTS.value,
                    )

    # ---------- CLASS RELATIONSHIPS ----------

    def _add_class_edges(self, nodes: Iterable[IRNode]) -> None:
        """
        Connect methods to parent classes.
        """
        name_to_id = {node.name: node.id for node in nodes}

        for node in nodes:
            if node.parent_class:
                parent = name_to_id.get(node.parent_class)

                if parent:
                    self.graph.add_edge(
                        parent,
                        node.id,
                        type=EdgeType.DEFINES.value,
                    )

            if node.bases:
                for base in node.bases:
                    parent = name_to_id.get(base)

                    if parent:
                        self.graph.add_edge(
                            node.id,
                            parent,
                            type=EdgeType.INHERITS.value,
                        )

    # ---------- UTILITY ----------

    def stats(self) -> dict:
        """
        Return graph statistics.
        """
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
        }