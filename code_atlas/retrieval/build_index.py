import uuid
import logging
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

from code_atlas.retrieval.load_graph import load_graph
from code_atlas.retrieval.build_documents import build_documents
from code_atlas.retrieval.embeddings import embed_texts
from code_atlas.graph.builder import CodeGraphBuilder

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

COLLECTION_NAME = "codeatlas_nodes"

def build_index(repo_id: str, graph=None):
    """
    Builds the vector index in Qdrant. 
    If the graph is missing, it builds it from the IR store automatically.
    """
    logger.info("Starting indexing process...")

    if graph is None:
        try:
            graph = load_graph(repo_id)
            logger.info(f"Existing graph loaded for {repo_id}")
        except FileNotFoundError:
            logger.warning(f"Graph file (.pkl) not found. Building now from IR store...")
            builder = CodeGraphBuilder(repo_id)
            graph = builder.build()
            if not graph:
                logger.error(" Failed to build graph. Aborting indexing.")
                return

    nodes_count = len(graph.nodes) if hasattr(graph, 'nodes') else 0
    logger.info(f"Graph ready. Nodes found: {nodes_count}")

    docs, metadata = build_documents(graph)
    logger.info(f"Documents created: {len(docs)}")

    if not docs:
        logger.warning("No documents to index! Check if your graph is empty.")
        return

    logger.info("Generating embeddings (this may take a moment)...")
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

    logger.info(" Indexing process complete. Project is ready for queries.")

if __name__ == "__main__":
    import sys
    repo = sys.argv[1] if len(sys.argv) > 1 else "github_com-Khushi-S-29-codeAtlas"
    build_index(repo)