import os
import tempfile
import networkx as nx

from code_atlas.retrieval.build_documents import build_documents


def test_build_documents_basic():
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("def test():\n    return 1\n")
        file_path = f.name

    graph = nx.DiGraph()

    graph.add_node(
        "1",
        kind="function",
        name="test",
        file=file_path,
        start_line=1,
        end_line=2,
    )

    docs, metadata = build_documents(graph)

    os.remove(file_path)

    assert len(docs) == 1
    assert len(metadata) == 1