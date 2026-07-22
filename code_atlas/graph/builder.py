# # from __future__ import annotations

# # import networkx as nx
# # from typing import Iterable

# # from code_atlas.parsing.ir_store import IRStore
# # from code_atlas.core.models import IRNode
# # from code_atlas.graph.schema import EdgeType


# # class CodeGraphBuilder:
# #     """
# #     Builds a directed dependency graph from IR nodes.

# #     Nodes represent structural code elements:
# #         modules, classes, functions, methods, imports

# #     Edges represent relationships:
# #         CALLS, IMPORTS, DEFINES, INHERITS
# #     """

# #     def __init__(self, repo_id: str):
# #         self.repo_id = repo_id
# #         self.store = IRStore(repo_id)
# #         self.graph = nx.DiGraph()

# #     def build(self) -> nx.DiGraph:
# #         """
# #         Main entrypoint for graph construction.
# #         """
# #         nodes = self.store.load_all()

# #         self._add_nodes(nodes)
# #         self._add_call_edges(nodes)
# #         self._add_import_edges(nodes)
# #         self._add_class_edges(nodes)

# #         return self.graph

# #     # ---------- NODE CREATION ----------

# #     def _add_nodes(self, nodes: Iterable[IRNode]) -> None:
# #         """
# #         Add IR nodes as graph nodes.
# #         """
# #         for node in nodes:
# #             self.graph.add_node(
# #                 node.id,
# #                 name=node.name,
# #                 kind=node.kind,
# #                 file=node.file_path,
# #                 start_line=node.start_line,
# #                 end_line=node.end_line,
# #                 language=node.language,
# #                 is_exported=getattr(node, "is_exported", False),
# #             )

# #     # ---------- CALL RELATIONSHIPS ----------

# #     def _add_call_edges(self, nodes: Iterable[IRNode]) -> None:

# #         name_to_ids = {}

# #     # build lookup
# #         for node in nodes:
# #             name_to_ids.setdefault(node.name, []).append(node.id)

# #     # add edges
# #         for node in nodes:

# #             if not node.calls:
# #                 continue

# #             for call in node.calls:

# #              leaf = call.split(".")[-1]

# #              targets = name_to_ids.get(call) or name_to_ids.get(leaf)

# #              if targets:
# #                 for target in targets:
# #                     self.graph.add_edge(
# #                         node.id,
# #                         target,
# #                         type=EdgeType.CALLS.value,
# #                     )

# #     # ---------- IMPORT RELATIONSHIPS ----------

# #     def _add_import_edges(self, nodes: Iterable[IRNode]) -> None:
# #         """
# #         Create IMPORT edges.
# #         """
# #         name_to_id = {node.name: node.id for node in nodes}

# #         for node in nodes:
# #             if not node.imports:
# #                 continue

# #             for imp in node.imports:
# #                 target = name_to_id.get(imp)

# #                 if target:
# #                     self.graph.add_edge(
# #                         node.id,
# #                         target,
# #                         type=EdgeType.IMPORTS.value,
# #                     )

# #     # ---------- CLASS RELATIONSHIPS ----------

# #     def _add_class_edges(self, nodes: Iterable[IRNode]) -> None:
# #         """
# #         Connect methods to parent classes.
# #         """
# #         name_to_id = {node.name: node.id for node in nodes}

# #         for node in nodes:
# #             if node.parent_class:
# #                 parent = name_to_id.get(node.parent_class)

# #                 if parent:
# #                     self.graph.add_edge(
# #                         parent,
# #                         node.id,
# #                         type=EdgeType.DEFINES.value,
# #                     )

# #             if node.bases:
# #                 for base in node.bases:
# #                     parent = name_to_id.get(base)

# #                     if parent:
# #                         self.graph.add_edge(
# #                             node.id,
# #                             parent,
# #                             type=EdgeType.INHERITS.value,
# #                         )

# #     # ---------- UTILITY ----------

# #     def stats(self) -> dict:
# #         """
# #         Return graph statistics.
# #         """
# #         return {
# #             "nodes": self.graph.number_of_nodes(),
# #             "edges": self.graph.number_of_edges(),
# #         }
# from __future__ import annotations

# import logging
# from typing import List

# import networkx as nx

# from code_atlas.parsing.ir_store import IRStore
# from code_atlas.core.models import IRNode, NodeKind
# from code_atlas.graph.schema import EdgeType

# logger = logging.getLogger(__name__)


# class CodeGraphBuilder:
#     """
#     Builds a directed dependency graph from IR nodes.

#     Nodes represent structural code elements:
#         modules, classes, functions, methods, imports

#     Edges represent relationships:
#         CALLS, IMPORTS, DEFINES, INHERITS, REFERENCES

#     Design notes
#     ------------
#     * We load the full node list **once** and materialise it into a Python
#       list so it can be iterated multiple times safely.
#     * Call / import / inheritance edges are loaded from the typed edge tables
#       that the parsing phase already populated.  Re-deriving them from raw
#       string lists (node.calls, node.imports) is lossy and unreliable.
#     * String-based fallback for calls is kept as a best-effort supplement
#       when callee_id is not yet resolved in the store.
#     """

#     def __init__(self, repo_id: str):
#         self.repo_id = repo_id
#         self.store   = IRStore(repo_id)
#         self.graph   = nx.DiGraph()

#     # ------------------------------------------------------------------
#     # Public API
#     # ------------------------------------------------------------------

#     def build(self) -> nx.DiGraph:
#         """Main entry-point for graph construction."""

#         # Materialise once — many methods need multiple passes.
#         nodes: List[IRNode] = self.store.load_all()

#         self._add_nodes(nodes)
#         self._add_call_edges(nodes)
#         self._add_import_edges(nodes)
#         self._add_inheritance_edges()
#         self._add_class_membership_edges(nodes)

#         logger.info(
#             "Graph built: %d nodes, %d edges",
#             self.graph.number_of_nodes(),
#             self.graph.number_of_edges(),
#         )
#         return self.graph

#     # ------------------------------------------------------------------
#     # Node creation
#     # ------------------------------------------------------------------

#     def _add_nodes(self, nodes: List[IRNode]) -> None:
#         """Add every IR node as a graph node with its metadata."""
#         for node in nodes:
#             self.graph.add_node(
#                 node.id,
#                 name=node.name,
#                 kind=node.kind,                          # already a string value
#                 file=node.file_path,
#                 start_line=node.start_line,
#                 end_line=node.end_line,
#                 language=node.language,
#                 is_exported=node.is_exported,
#                 parent_id=node.parent_id,
#                 parent_class=node.parent_class,
#             )

#     # ------------------------------------------------------------------
#     # Call edges  (primary: typed CallEdge rows; fallback: node.calls strings)
#     # ------------------------------------------------------------------

#     def _add_call_edges(self, nodes: List[IRNode]) -> None:
#         """
#         Add CALLS edges.

#         Strategy (two-pass):
#           1. Load stored CallEdge rows from the IR store.  When callee_id is
#              already resolved use it directly; otherwise fall back to name
#              lookup.
#           2. For any node whose calls list has entries not covered by the
#              typed rows, attempt a name-based match as a supplement.
#         """
#         # Build name → [node_id] lookup for fallback resolution.
#         name_to_ids: dict[str, list[str]] = {}
#         for node in nodes:
#             name_to_ids.setdefault(node.name, []).append(node.id)

#         # Track which (caller, callee) pairs are already added.
#         seen: set[tuple[str, str]] = set()

#         # --- Primary: use typed CallEdge rows ---
#         for edge in self.store.load_call_edges():
#             caller_id = edge.caller_id
#             if caller_id not in self.graph:
#                 continue  # stale edge from a deleted file

#             if edge.callee_id and edge.callee_id in self.graph:
#                 pair = (caller_id, edge.callee_id)
#                 if pair not in seen:
#                     self.graph.add_edge(caller_id, edge.callee_id, type=EdgeType.CALLS.value)
#                     seen.add(pair)
#             else:
#                 # callee_id not resolved yet — try name lookup
#                 callee_name = edge.callee_name
#                 leaf        = callee_name.split(".")[-1]
#                 targets     = name_to_ids.get(callee_name) or name_to_ids.get(leaf, [])
#                 for target in targets:
#                     pair = (caller_id, target)
#                     if pair not in seen:
#                         self.graph.add_edge(caller_id, target, type=EdgeType.CALLS.value)
#                         seen.add(pair)

#         # --- Fallback: node.calls strings for any calls not yet in the store ---
#         for node in nodes:
#             if not node.calls:
#                 continue
#             for call in node.calls:
#                 leaf    = call.split(".")[-1]
#                 targets = name_to_ids.get(call) or name_to_ids.get(leaf, [])
#                 for target in targets:
#                     pair = (node.id, target)
#                     if pair not in seen:
#                         self.graph.add_edge(node.id, target, type=EdgeType.CALLS.value)
#                         seen.add(pair)

#     # ------------------------------------------------------------------
#     # Import edges  (use typed ImportEdge rows; match by target_module name)
#     # ------------------------------------------------------------------

#     def _add_import_edges(self, nodes: List[IRNode]) -> None:
#         """
#         Add IMPORTS edges using stored ImportEdge rows.

#         ImportEdge.target_module is a module/file path string, not a node
#         name.  We match it against node.file_path (shortest-suffix match) and
#         also against node.name for named exports.
#         """
#         # Build lookup maps.
#         file_to_ids:   dict[str, list[str]] = {}
#         name_to_ids:   dict[str, list[str]] = {}
#         for node in nodes:
#             file_to_ids.setdefault(node.file_path, []).append(node.id)
#             name_to_ids.setdefault(node.name,      []).append(node.id)

#         seen: set[tuple[str, str]] = set()

#         for edge in self.store.load_import_edges():
#             # Find the source node(s) whose file_path == edge.source_file.
#             source_ids = file_to_ids.get(edge.source_file, [])
#             if not source_ids:
#                 continue

#             # Resolve target: try exact file match first, then name match.
#             target_mod = edge.target_module
#             # Normalise: strip leading './' or '../' for matching
#             target_stem = target_mod.replace("\\", "/").split("/")[-1].split(".")[0]

#             target_ids: list[str] = []
#             # Exact file path match
#             for fp, ids in file_to_ids.items():
#                 if fp == target_mod or fp.endswith("/" + target_mod) or \
#                    fp.replace("\\", "/").split("/")[-1].split(".")[0] == target_stem:
#                     target_ids.extend(ids)
#             # Name match as fallback
#             if not target_ids:
#                 target_ids = name_to_ids.get(target_mod, []) or \
#                              name_to_ids.get(target_stem, [])

#             for src_id in source_ids:
#                 for tgt_id in target_ids:
#                     if src_id == tgt_id:
#                         continue
#                     pair = (src_id, tgt_id)
#                     if pair not in seen:
#                         self.graph.add_edge(src_id, tgt_id, type=EdgeType.IMPORTS.value)
#                         seen.add(pair)

#     # ------------------------------------------------------------------
#     # Inheritance edges  (use typed InheritanceEdge rows)
#     # ------------------------------------------------------------------

#     def _add_inheritance_edges(self) -> None:
#         """
#         Add INHERITS edges using stored InheritanceEdge rows.
#         When parent_id is resolved use it directly; otherwise fall back to
#         a name lookup inside the graph.
#         """
#         # Build name→id map from graph nodes (already added).
#         name_to_id: dict[str, str] = {}
#         for node_id, data in self.graph.nodes(data=True):
#             name_to_id[data["name"]] = node_id

#         seen: set[tuple[str, str]] = set()

#         for edge in self.store.load_inheritance_edges():
#             child_id = edge.child_id
#             if child_id not in self.graph:
#                 continue

#             if edge.parent_id and edge.parent_id in self.graph:
#                 parent_id = edge.parent_id
#             else:
#                 parent_id = name_to_id.get(edge.parent_name)
#                 if not parent_id:
#                     continue

#             pair = (child_id, parent_id)
#             if pair not in seen:
#                 self.graph.add_edge(child_id, parent_id, type=EdgeType.INHERITS.value)
#                 seen.add(pair)

#     # ------------------------------------------------------------------
#     # Class membership (DEFINES) edges  — parent class → method / nested
#     # ------------------------------------------------------------------

#     def _add_class_membership_edges(self, nodes: List[IRNode]) -> None:
#         """
#         For every node that declares a parent_class or parent_id, add a
#         DEFINES edge from the parent to the child.

#         This captures the class→method containment that isn't covered by
#         the inheritance edge table.
#         """
#         id_exists = set(self.graph.nodes())
#         seen: set[tuple[str, str]] = set()

#         for node in nodes:
#             # parent_id is the most reliable link (set by visitors).
#             if node.parent_id and node.parent_id in id_exists:
#                 pair = (node.parent_id, node.id)
#                 if pair not in seen:
#                     self.graph.add_edge(node.parent_id, node.id, type=EdgeType.DEFINES.value)
#                     seen.add(pair)

#     # ------------------------------------------------------------------
#     # Utility
#     # ------------------------------------------------------------------

#     def stats(self) -> dict:
#         """Return graph statistics."""
#         return {
#             "nodes": self.graph.number_of_nodes(),
#             "edges": self.graph.number_of_edges(),
#         }


from __future__ import annotations

import logging
from typing import List

import networkx as nx

from code_atlas.parsing.ir_store import IRStore
from code_atlas.core.models import IRNode, NodeKind
from code_atlas.graph.schema import EdgeType

logger = logging.getLogger(__name__)

_EXECUTABLE_KINDS: frozenset[str] = frozenset({
    NodeKind.FUNCTION.value,
    NodeKind.METHOD.value,
    NodeKind.CONSTRUCTOR.value,
    NodeKind.LAMBDA.value,
})

# Kinds that can hold meaningful function references in their node.references.
# ASSIGNMENT nodes represent array/object patterns like:
#   const validateSignup = [body(...), handleValidation]
#   const routes = { path: myHandler }
# These reference functions by name and must emit CALLS edges.
_REFERENCE_EMITTING_KINDS: frozenset[str] = _EXECUTABLE_KINDS | frozenset({
    NodeKind.ASSIGNMENT.value,
})

_STRUCTURAL_KINDS: frozenset[str] = frozenset({
    NodeKind.FILE.value,
    NodeKind.MODULE.value,
    NodeKind.PACKAGE.value,
    NodeKind.NAMESPACE.value,
    NodeKind.IMPORT.value,
    "require",
})

_SKIP_REFS: frozenset[str] = frozenset({
    "true","false","null","undefined","this","self",
    "console","process","window","document","module","exports","require",
    "arguments","prototype","length","name","type","value","data","error",
    "res","req","next","err","e","event","cb","callback",
    "response","request","result","results","resolve","reject",
    "index","item","items","key","keys","id","ids","i","j","n","x","y","k",
    "props","state","ref","ctx","context",
    "True","False","None","cls",
    "useState","useEffect","useCallback","useMemo","useRef",
    "useContext","useNavigate","useParams","useLocation",
    "Math","JSON","Date","Object","Array","String","Number",
    "Promise","Error","Set","Map",
    "alert","confirm","prompt","db","pool","token","password","email",
    "user","users","api","axios","fetch","navigate","location","history",
    "children","params","body","headers","log","warn","info","debug",
    "BrowserRouter","Routes","Route","Switch","Link","NavLink",
    "div","span","button","input","form","table","thead","tbody",
    "tr","td","th","h1","h2","h3","h4","p","ul","li","a","img",
    "select","option","label","header","footer","main","section",
})


class CodeGraphBuilder:
    """
    Builds a directed dependency graph from IR nodes.

    Edge types
    ----------
    CALLS    — execution flow. THE ONLY type traversed by dead-code DFS.
    IMPORTS  — file-level dependency. NOT traversed by DFS.
    DEFINES  — structural containment. NOT traversed by DFS.
    INHERITS — class hierarchy. Traversed by DFS.

    Key invariant — edge priority
    ------------------------------
    CALLS > INHERITS > IMPORTS > DEFINES

    Every method that adds edges checks a global `all_pairs` set before
    calling graph.add_edge().  This guarantees:
      - A CALLS edge is never overwritten by a later IMPORTS or DEFINES edge
        on the same node pair.
      - NetworkX DiGraph stores one edge per pair — without this guard,
        _add_import_edges (step 3) would silently overwrite CALLS edges
        added by _add_reference_edges (step 2), making those nodes
        invisible to the CALLS-only DFS.
    """

    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self.store   = IRStore(repo_id)
        self.graph   = nx.DiGraph()

    def build(self) -> nx.DiGraph:
        nodes: List[IRNode] = self.store.load_all()

        self._add_nodes(nodes)

        # One global set tracks every (src, dst) pair added to the graph.
        # Later steps skip any pair already present — preserving the
        # higher-priority edge type placed by an earlier step.
        all_pairs: set[tuple[str, str]] = set()

        self._add_call_edges(nodes, all_pairs)       # CALLS  — highest priority
        self._add_reference_edges(nodes, all_pairs)  # CALLS  — ref-based
        self._add_import_edges(nodes, all_pairs)     # IMPORTS — skip if pair exists
        self._add_inheritance_edges(all_pairs)       # INHERITS
        self._add_class_membership_edges(nodes, all_pairs)  # DEFINES — lowest priority

        logger.info(
            "Graph built: %d nodes, %d edges",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )
        return self.graph

    def _add_nodes(self, nodes: List[IRNode]) -> None:
        for node in nodes:
            self.graph.add_node(
                node.id,
                name=node.name,
                kind=node.kind,
                file=node.file_path,
                start_line=node.start_line,
                end_line=node.end_line,
                language=node.language,
                is_exported=node.is_exported,
                parent_id=node.parent_id,
                parent_class=node.parent_class,
                decorators=node.decorators,
            )

    def _add_call_edges(self, nodes: List[IRNode],
                        all_pairs: set[tuple[str, str]]) -> None:
        name_to_ids: dict[str, list[str]] = {}
        for node in nodes:
            name_to_ids.setdefault(node.name, []).append(node.id)

        for edge in self.store.load_call_edges():
            caller_id   = edge.caller_id
            callee_name = edge.callee_name
            if caller_id not in self.graph:
                continue
            if edge.callee_id and edge.callee_id in self.graph:
                pair = (caller_id, edge.callee_id)
                if pair not in all_pairs:
                    self.graph.add_edge(caller_id, edge.callee_id,
                                        type=EdgeType.CALLS.value)
                    all_pairs.add(pair)
            else:
                leaf    = callee_name.split(".")[-1]
                targets = name_to_ids.get(callee_name) or name_to_ids.get(leaf, [])
                for target in targets:
                    pair = (caller_id, target)
                    if pair not in all_pairs:
                        self.graph.add_edge(caller_id, target,
                                            type=EdgeType.CALLS.value)
                        all_pairs.add(pair)

        for node in nodes:
            if not node.calls or node.kind in _STRUCTURAL_KINDS:
                continue
            for call in node.calls:
                leaf    = call.split(".")[-1]
                targets = name_to_ids.get(call) or name_to_ids.get(leaf, [])
                for target in targets:
                    pair = (node.id, target)
                    if pair not in all_pairs:
                        self.graph.add_edge(node.id, target,
                                            type=EdgeType.CALLS.value)
                        all_pairs.add(pair)

    def _add_reference_edges(self, nodes: List[IRNode],
                             all_pairs: set[tuple[str, str]]) -> None:
        """
        CALLS edges from node.references (passed-by-reference patterns).

        Processes:
        1. Executable nodes (functions/methods/constructors/lambdas) — full refs
        2. Assignment nodes — array/object patterns like middleware chains:
               const validateSignup = [body(...), handleValidation]
        3. Module nodes — ONLY refs collected from route/middleware registration
               calls (router.X, app.X, server.X). All other module-level refs
               are noise (import names, JSX tags etc.) and are excluded.
        """
        name_to_ids: dict[str, list[str]] = {}
        for node in nodes:
            name_to_ids.setdefault(node.name, []).append(node.id)

        # Route-registration callee prefixes — only these make module-level
        # identifier arguments meaningful as function references.
        _ROUTE_CALLEES: frozenset[str] = frozenset({
            "router.", "app.", "server.", "express.",
        })

        for node in nodes:
            if not node.references:
                continue

            is_executable   = node.kind in _REFERENCE_EMITTING_KINDS
            is_route_module = (
                node.kind in _STRUCTURAL_KINDS
                and any(c.startswith(tuple(_ROUTE_CALLEES))
                        for c in (node.calls or []))
            )

            if not is_executable and not is_route_module:
                continue

            for ref in node.references:
                ref = ref.strip()
                if not ref or ref in _SKIP_REFS or len(ref) <= 1:
                    continue
                leaf    = ref.split(".")[-1]
                targets = name_to_ids.get(ref) or name_to_ids.get(leaf, [])
                for target in targets:
                    if target == node.id:
                        continue
                    pair = (node.id, target)
                    if pair not in all_pairs:
                        self.graph.add_edge(node.id, target,
                                            type=EdgeType.CALLS.value)
                        all_pairs.add(pair)

    def _add_import_edges(self, nodes: List[IRNode],
                         all_pairs: set[tuple[str, str]]) -> None:
        """
        IMPORTS edges between file/module nodes.
        Skips any pair already in all_pairs — preserving CALLS edges placed
        by _add_reference_edges for the same pair (e.g. App→Login).
        """
        file_to_ids: dict[str, list[str]] = {}
        name_to_ids: dict[str, list[str]] = {}
        for node in nodes:
            file_to_ids.setdefault(node.file_path, []).append(node.id)
            name_to_ids.setdefault(node.name,      []).append(node.id)

        for edge in self.store.load_import_edges():
            source_ids = file_to_ids.get(edge.source_file, [])
            if not source_ids:
                continue
            target_mod  = edge.target_module
            target_stem = target_mod.replace("\\", "/").split("/")[-1].split(".")[0]
            target_ids: list[str] = []
            for fp, ids in file_to_ids.items():
                if fp.replace("\\", "/").split("/")[-1].split(".")[0] == target_stem:
                    target_ids.extend(ids)
            if not target_ids:
                target_ids = (name_to_ids.get(target_mod, []) or
                              name_to_ids.get(target_stem, []))
            for src_id in source_ids:
                for tgt_id in target_ids:
                    if src_id == tgt_id:
                        continue
                    pair = (src_id, tgt_id)
                    if pair not in all_pairs:
                        self.graph.add_edge(src_id, tgt_id,
                                            type=EdgeType.IMPORTS.value)
                        all_pairs.add(pair)

    def _add_inheritance_edges(self,
                               all_pairs: set[tuple[str, str]]) -> None:
        name_to_id = {data["name"]: nid
                      for nid, data in self.graph.nodes(data=True)}
        for edge in self.store.load_inheritance_edges():
            child_id = edge.child_id
            if child_id not in self.graph:
                continue
            parent_id = (edge.parent_id if edge.parent_id in self.graph
                         else name_to_id.get(edge.parent_name))
            if not parent_id:
                continue
            pair = (child_id, parent_id)
            if pair not in all_pairs:
                self.graph.add_edge(child_id, parent_id,
                                    type=EdgeType.INHERITS.value)
                all_pairs.add(pair)

    def _add_class_membership_edges(self, nodes: List[IRNode],
                                    all_pairs: set[tuple[str, str]]) -> None:
        """
        DEFINES edges — structural containment. Lowest priority.
        Skips any pair already registered in all_pairs.
        """
        id_exists = set(self.graph.nodes())
        for node in nodes:
            if not node.parent_id or node.parent_id not in id_exists:
                continue
            pair = (node.parent_id, node.id)
            if pair not in all_pairs:
                self.graph.add_edge(node.parent_id, node.id,
                                    type=EdgeType.DEFINES.value)
                all_pairs.add(pair)

    def stats(self) -> dict:
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
        }