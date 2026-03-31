from code_atlas.retrieval.embeddings import embed_query, embed_texts


def test_embed_query():
    vec = embed_query("hello")

    assert vec is not None
    assert len(vec) > 0


def test_embed_texts():
    texts = ["hello", "world"]

    vectors = embed_texts(texts)

    assert len(vectors) == 2