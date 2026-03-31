from code_atlas.retrieval.build_documents import build_documents
import networkx as nx

def test_build_documents_returns_function_docs(tmp_path):
    graph = nx.DiGraph()

    file_path = "test.py"
    code = """
def add(a, b):
    return a + b

def sub(a, b):
    return a - b
"""

    file_full_path = tmp_path / file_path
    file_full_path.write_text(code)

    graph.add_node("1", file=file_path)

    docs, metadata = build_documents(graph)

    assert len(docs) >= 1
    assert "FUNCTION LEVEL DOCUMENT" in docs[0]
    assert "def add" in docs[0] or "def sub" in docs[0]