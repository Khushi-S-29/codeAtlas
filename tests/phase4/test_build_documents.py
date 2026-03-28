import networkx as nx
from code_atlas.retrieval.build_documents import build_documents


def test_build_documents():

    G = nx.Graph()

    G.add_node(1, name="add", type="function", code="def add(a,b): return a+b")

    docs, metadata = build_documents(G)

    assert len(docs) == 1
    assert "add" in docs[0]
    assert metadata[0]["name"] == "add"