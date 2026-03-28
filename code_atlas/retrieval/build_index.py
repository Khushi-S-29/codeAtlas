import uuid
import logging
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

from code_atlas.retrieval.load_graph import load_graph
from code_atlas.retrieval.build_documents import build_documents
from code_atlas.retrieval.embeddings import embed_texts

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

COLLECTION_NAME = "codeatlas_nodes"

def build_index():
    logger.info("Starting indexing process...")
    graph = load_graph()
    
    logger.info(f"Graph loaded. Nodes found: {len(graph.nodes) if hasattr(graph, 'nodes') else 'Unknown'}")

    docs, metadata = build_documents(graph)

    logger.info(f"Documents created: {len(docs)}")

    if not docs:
        logger.warning("No documents to index! Check if your graph is empty.")
        return

    embeddings = embed_texts(docs)

    client = QdrantClient(host="qdrant", port=6333)

    if not client.collection_exists(COLLECTION_NAME):
        vector_size = len(embeddings[0])
        logger.info(f"Creating collection '{COLLECTION_NAME}' with size {vector_size}")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            )
        )

    batch_size = 64
    for i in range(0, len(docs), batch_size):
        batch_points = []
        end_idx = min(i + batch_size, len(docs))
        
        for j in range(i, end_idx):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, docs[j]))
            
            vector_data = embeddings[j]
            if isinstance(vector_data, np.ndarray):
                vector_data = vector_data.tolist()
            
            batch_points.append(PointStruct(
                id=point_id,
                vector=vector_data,
                payload={
                    "text": docs[j],
                    **metadata[j]
                }
            ))

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch_points
        )
        logger.info(f"Upserted batch: {i} to {end_idx}")

    logger.info("Indexing process complete.")

if __name__ == "__main__":
    build_index()