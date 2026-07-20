from code_atlas.retrieval.embeddings import embed_query, embed_texts


def test_embeddings():
    query_vec = embed_query("hello")

    assert query_vec is not None
    assert len(query_vec) > 0

    vectors = embed_texts(["hello"])

    assert len(vectors) == 1
    assert len(vectors[0]) == len(query_vec)