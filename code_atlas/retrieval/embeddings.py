from sentence_transformers import SentenceTransformer
import numpy as np

"""
Module for generating semantic embeddings using a local Transformer model.
Uses 'all-MiniLM-L6-v2' for a balance of speed and accuracy on CPU.
"""

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return _model

def embed_texts(texts):
    """Converts a list of code/text nodes into vector embeddings."""
    if not texts:
        return np.array([])
    model = get_model()
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

def embed_query(query):
    """Converts a single user natural language query into a vector."""
    model = get_model()
    embedding = model.encode([query], convert_to_numpy=True)
    return embedding[0]

# PURPOSE:
# This module acts as the "Translator" between raw code and vectors.
# It uses a singleton pattern to keep memory usage low while 
# providing fast local inference.