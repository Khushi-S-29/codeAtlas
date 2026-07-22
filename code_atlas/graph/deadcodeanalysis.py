# # from __future__ import annotations

# # import networkx as nx
# # from typing import List

# # from code_atlas.core.models import NodeKind


# # import networkx as nx
# # from typing import List, Set

# # from code_atlas.core.models import NodeKind
# from __future__ import annotations

# import networkx as nx
# from typing import List, Set

# from code_atlas.core.models import NodeKind


# def find_dead_functions(graph: nx.DiGraph) -> List[str]:
#     """
#     Detect dead functions using reachability analysis.

#     Steps:
#     1. Identify entry points
#     2. Traverse graph from entry points
#     3. Any function not reachable is dead
#     """

#     entry_nodes: Set[str] = set()

#     # ---------- identify entry points ----------

#     for node_id, data in graph.nodes(data=True):

#         kind = data.get("kind")
#         name = data.get("name")

#         # exported/public API
#         if data.get("is_exported"):
#             entry_nodes.add(node_id)

#         # modules are roots
#         if kind == NodeKind.MODULE.value:
#             entry_nodes.add(node_id)

#         # main functions
#         if name == "main":
#             entry_nodes.add(node_id)

#         # React component heuristic
#         if kind == NodeKind.FUNCTION.value and name and name[0].isupper():
#             entry_nodes.add(node_id)

#     # ---------- graph traversal ----------

#     reachable: Set[str] = set()

#     stack = list(entry_nodes)

#     while stack:
#         node = stack.pop()

#         if node in reachable:
#             continue

#         reachable.add(node)

#         for neighbor in graph.successors(node):
#             stack.append(neighbor)

#     # ---------- find dead nodes ----------

#     dead_nodes: List[str] = []

#     for node_id, data in graph.nodes(data=True):

#         kind = data.get("kind")

#         if kind not in (
#             NodeKind.FUNCTION.value,
#             NodeKind.METHOD.value,
#         ):
#             continue

#         if node_id not in reachable:
#             dead_nodes.append(node_id)

#     return dead_nodes

from __future__ import annotations

import logging
from typing import List, Set

import networkx as nx

from code_atlas.core.models import NodeKind
from code_atlas.graph.schema import EdgeType

logger = logging.getLogger(__name__)

_EXECUTABLE_KINDS: frozenset[str] = frozenset({
    NodeKind.FUNCTION.value,
    NodeKind.METHOD.value,
    NodeKind.CONSTRUCTOR.value,
    NodeKind.LAMBDA.value,
})

_STRUCTURAL_KINDS: frozenset[str] = frozenset({
    NodeKind.FILE.value,
    NodeKind.MODULE.value,
    NodeKind.PACKAGE.value,
    NodeKind.NAMESPACE.value,
})

_TRAVERSAL_EDGE_TYPES: frozenset[str] = frozenset({
    EdgeType.CALLS.value,
    EdgeType.INHERITS.value,
})

_ENTRY_NAMES: frozenset[str] = frozenset({
    "main", "__main__", "run", "start", "bootstrap",
    "createApp", "create_app", "makeApp", "make_app",
    "initApp", "init_app", "startServer", "initSuperAdmin",
    "setup", "teardown", "__init_subclass__", "__new__",
})

_REACT_ROOT_NAMES: frozenset[str] = frozenset({
    "App", "Root", "Application", "Main", "Index", "AppRouter",
})

_ENTRY_DECORATORS: frozenset[str] = frozenset({
    "route", "app.route", "get", "post", "put", "delete", "patch",
    "head", "options", "task", "shared_task", "celery.task",
    "pytest.fixture", "fixture", "property", "classmethod", "staticmethod",
    "click.command", "command", "receiver", "event_listener", "on_event",
})


def _parent_kind(graph: nx.DiGraph, node_id: str) -> str | None:
    parent_id = graph.nodes[node_id].get("parent_id")
    if not parent_id or parent_id not in graph:
        return None
    return graph.nodes[parent_id].get("kind", "")


def _is_truly_nested(graph: nx.DiGraph, node_id: str) -> bool:
    pk = _parent_kind(graph, node_id)
    if pk is None:
        return False
    if pk in _STRUCTURAL_KINDS:
        return False
    return True


def _build_imported_files(graph: nx.DiGraph) -> Set[str]:
    """
    Return the set of file paths that have at least one IMPORTS edge
    pointing INTO them from another file — i.e. they are actually imported
    somewhere. Used to distinguish exported-but-unused components from
    exported-and-imported ones.
    """
    imported_files: Set[str] = set()
    for src, dst, data in graph.edges(data=True):
        if data.get("type") == EdgeType.IMPORTS.value:
            dst_file = graph.nodes[dst].get("file", "")
            if dst_file:
                imported_files.add(dst_file)
    return imported_files


def find_dead_functions(graph: nx.DiGraph) -> List[str]:
    """
    Detect unreachable (dead) executable nodes via forward reachability DFS.

    Entry point rules
    -----------------
    1. Structural roots (file/module/package nodes).

    2. Named entry points (main, run, initSuperAdmin ...).

    3. React app roots (App, Root, AppRouter) — unconditional.

    4. Decorator-based entry points.

    5. Exported top-level non-React functions — backend controllers,
       middleware, model functions, utilities. React components (uppercase
       JS functions) are excluded here because export alone doesn't mean used.

    6. Exported top-level React components whose FILE is imported by at
       least one other file.
       Rationale: if a component's file is imported somewhere, the component
       is likely being used even if it's referenced under a different alias
       (e.g. import Simulation from './Simulation' then <Simulation/>
       where the function inside is named SimulationModal).
       BUT: if the file is NEVER imported anywhere (like EditSlotModal.jsx
       in DeptSync), the component is genuinely dead and should be flagged.

    Traversal: CALLS and INHERITS only — DEFINES and IMPORTS are structural,
    not execution flow.
    """

    # Pre-compute which files are imported by at least one other file
    imported_files = _build_imported_files(graph)

    entry_nodes: Set[str] = set()

    for node_id, data in graph.nodes(data=True):
        kind        = data.get("kind", "")
        name        = data.get("name", "") or ""
        is_exported = data.get("is_exported", False)
        parent_cls  = data.get("parent_class")
        language    = data.get("language", "")
        file_path   = data.get("file", "")
        decorators  = data.get("decorators") or []

        # 1. Structural roots
        if kind in _STRUCTURAL_KINDS:
            entry_nodes.add(node_id)
            continue

        # 2. Named entry points
        if name in _ENTRY_NAMES:
            entry_nodes.add(node_id)
            continue

        # 3. React app roots
        if name in _REACT_ROOT_NAMES and kind == NodeKind.FUNCTION.value:
            entry_nodes.add(node_id)
            continue

        # 4. Decorator-based entry points
        dec_lower = {d.lower().strip("@") for d in decorators}
        if dec_lower & _ENTRY_DECORATORS:
            entry_nodes.add(node_id)
            continue

        is_js_component = (
            kind == NodeKind.FUNCTION.value
            and name and name[0].isupper()
            and language in ("javascript", "typescript", "jsx", "tsx")
        )

        # 5. Exported top-level non-React functions
        if (is_exported
                and not parent_cls
                and not _is_truly_nested(graph, node_id)
                and not is_js_component):
            entry_nodes.add(node_id)
            continue

        # 6. Exported top-level React components whose file IS imported
        #    somewhere — the component is likely being used under an alias.
        #    Components whose file is NEVER imported are genuinely dead.
        if (is_js_component
                and is_exported
                and not parent_cls
                and not _is_truly_nested(graph, node_id)
                and file_path in imported_files):
            entry_nodes.add(node_id)
            continue

    logger.debug(
        "Dead-code analysis: %d entry nodes out of %d total",
        len(entry_nodes), graph.number_of_nodes(),
    )

    # Forward reachability — CALLS and INHERITS only
    reachable: Set[str] = set()
    stack = list(entry_nodes)
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        for neighbour, edge_data in graph[node].items():
            if edge_data.get("type", "") in _TRAVERSAL_EDGE_TYPES:
                if neighbour not in reachable:
                    stack.append(neighbour)

    logger.debug(
        "Dead-code analysis: %d / %d nodes reachable",
        len(reachable), graph.number_of_nodes(),
    )

    dead_nodes: List[str] = []
    for node_id, data in graph.nodes(data=True):
        if data.get("kind", "") not in _EXECUTABLE_KINDS:
            continue
        if node_id not in reachable:
            dead_nodes.append(node_id)

    logger.info(
        "Dead-code analysis complete: %d dead / %d executable nodes",
        len(dead_nodes),
        sum(1 for _, d in graph.nodes(data=True)
            if d.get("kind") in _EXECUTABLE_KINDS),
    )
    return dead_nodes

def find_unreachable_modules(graph: nx.DiGraph) -> List[str]:
    """
    Detect modules (files) that are never imported.
    """

    modules = []
    imported_files = set()

    # Step 1: collect all imported target files
    for src, dst, data in graph.edges(data=True):
        if data.get("type") == EdgeType.IMPORTS.value:
            file = graph.nodes[dst].get("file")
            if file:
                imported_files.add(file)

    # Step 2: check module nodes
    for node_id, data in graph.nodes(data=True):
        if data.get("kind") != NodeKind.MODULE.value:
            continue

        file_path = data.get("file")

        # skip entry files (important!)
        name = data.get("name", "").lower()
        if any(x in name for x in ("app", "main", "index")):
            continue

        if file_path not in imported_files:
            modules.append(node_id)

    return modules