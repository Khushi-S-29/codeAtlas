def mock_search(query):
    return [
        {"text": "def add(a,b): return a+b", "score": 0.9},
        {"text": "def sub(a,b): return a-b", "score": 0.8}
    ]


def test_mock_search():
    results = mock_search("add")

    assert len(results) > 0
    assert "add" in results[0]["text"]