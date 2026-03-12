from __future__ import annotations

import uuid

import pytest
import networkx as nx

from code_atlas.graph.builder import CodeGraphBuilder
from code_atlas.graph.schema import EdgeType
from code_atlas.parsing.ir_store import IRStore
from code_atlas.core.models import IRNode, NodeKind


@pytest.fixture
def repo_store(tmp_path) -> tuple[str, IRStore]:
    """
    Return a tuple (repo_id, IRStore) backed by a temporary directory.

    Using a randomized repo id and a custom directory isolates the test
    from the global `DATA_DIR` and keeps runs deterministic.
    """
    repo_id = f"test_{uuid.uuid4().hex}"
    ir_dir = tmp_path / "ir"
    store = IRStore(repo_id, ir_dir=ir_dir)

    # build a small, self-contained set of IR nodes that exercise the
    # various relationship types.  Naming/numeric IDs are arbitrary but
    # stable across invocations.
    n1 = IRNode(
        id="n1",
        name="foo",
        kind=NodeKind.FUNCTION,
        file_path="foo.py",
        start_line=1,
        end_line=1,
        language="python",
    )
    n2 = IRNode(
        id="n2",
        name="bar",
        kind=NodeKind.FUNCTION,
        file_path="bar.py",
        start_line=1,
        end_line=1,
        language="python",
        calls=["foo"],
    )
    n3 = IRNode(
        id="n3",
        name="MyClass",
        kind=NodeKind.CLASS,
        file_path="a.py",
        start_line=1,
        end_line=3,
        imports=["foo"],
        language="python",
    )
    n4 = IRNode(
        id="n4",
        name="method",
        kind=NodeKind.METHOD,
        file_path="a.py",
        start_line=2,
        end_line=2,
        language="python",
        parent_class="MyClass",
    )

    store.upsert_nodes([n1, n2, n3, n4])

    return repo_id, store


@pytest.fixture
def builder(repo_store):
    repo_id, store = repo_store
    builder = CodeGraphBuilder(repo_id)
    # override the store so the builder reads from the temporary database
    builder.store = store
    return builder


class TestGraphBuilder:
    def test_graph_builds_from_ir(self, builder: CodeGraphBuilder):
        g = builder.build()
        assert isinstance(g, nx.DiGraph)
        # we inserted four nodes explicitly
        assert g.number_of_nodes() == 4
        # call + import + defines relationships
        assert g.number_of_edges() == 3

    def test_nodes_have_required_attributes(self, builder: CodeGraphBuilder):
        g = builder.build()
        for _, data in g.nodes(data=True):
            assert "name" in data
            assert "kind" in data
            assert "file" in data

    def test_edges_contain_types(self, builder: CodeGraphBuilder):
        g = builder.build()
        for _, _, data in g.edges(data=True):
            assert "type" in data

    def test_call_and_import_edges_are_present(self, builder: CodeGraphBuilder):
        g = builder.build()
        assert g.has_edge("n2", "n1")
        assert g.get_edge_data("n2", "n1")["type"] == EdgeType.CALLS.value

        assert g.has_edge("n3", "n1")
        assert g.get_edge_data("n3", "n1")["type"] == EdgeType.IMPORTS.value

    def test_method_defined_under_class(self, builder: CodeGraphBuilder):
        g = builder.build()
        assert g.has_edge("n3", "n4")
        assert g.get_edge_data("n3", "n4")["type"] == EdgeType.DEFINES.value

    def test_edge_nodes_exist(self, builder: CodeGraphBuilder):
        g = builder.build()
        for src, dst in g.edges():
            assert src in g.nodes
            assert dst in g.nodes

    def test_graph_not_empty(self, builder):

          g = builder.build()

          assert g.number_of_nodes() > 0
          assert g.number_of_edges() > 0