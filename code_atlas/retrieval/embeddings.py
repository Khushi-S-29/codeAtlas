from sentence_transformers import SentenceTransformer
import numpy as np

"""
Module for generating semantic embeddings using BGE embeddings.
"""

_model = None


def get_model():
    global _model

    if _model is None:
        _model = SentenceTransformer(
            "BAAI/bge-large-en-v1.5",
            device="cpu"
        )

    return _model


def embed_texts(texts):
    """
    Converts documents into vector embeddings.
    """

    if not texts:
        return np.array([])

    model = get_model()

    texts = [
        f"Represent this code document for retrieval: {text}"
        for text in texts
    ]

    return model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False
    )


def embed_query(query):
    """
    Converts a user query into a vector embedding.
    """

    model = get_model()

    query = (
        f"Represent this query for retrieving relevant code: {query}"
    )

    embedding = model.encode(
        [query],
        convert_to_numpy=True
    )

    return embedding[0]


# PURPOSE:
# This module acts as the "Translator" between raw code and vectors.
# Uses 'BAAI/bge-large-en-v1.5' for higher-quality embeddings.