from qdrant_client import QdrantClient
from code_atlas.retrieval.embeddings import embed_query

COLLECTION_NAME = "codeatlas_nodes"

class Retriever:
    def __init__(self, collection_name=COLLECTION_NAME):
        self.collection_name = collection_name
        self.client = QdrantClient(host="qdrant", port=6333)

    def retrieve(self, query, top_k=5):
        query_vector = embed_query(query)

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector.tolist(),
            limit=top_k,
            with_payload=True
        )

        output = []

        for r in response.points:
            payload = r.payload or {}

            output.append({
                "text": payload.get("text", ""),
                "score": r.score,
                "metadata": {
                    "node_id": payload.get("node_id"),
                    "name": payload.get("name"),
                    "type": payload.get("type"),
                    "file": payload.get("file")
                }
            })

        return output
# PURPOSE: Handles semantic code search.