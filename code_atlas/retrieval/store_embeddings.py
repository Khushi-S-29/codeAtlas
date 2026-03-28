from qdrant_client import QdrantClient

COLLECTION_NAME = "codeatlas_nodes"


def get_client():
    return QdrantClient(host="localhost", port=6333)