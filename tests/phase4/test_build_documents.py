import networkx as nx
from code_atlas.retrieval.build_documents import build_documents

def test_build_documents_basic():
    graph = nx.DiGraph()

    graph.add_node("1", file="/tmp/test.py")

    docs, metadata = build_documents(graph)

    assert isinstance(docs, list)
    assert isinstance(metadata, list)