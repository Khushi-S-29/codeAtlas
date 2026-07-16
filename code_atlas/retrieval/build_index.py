import uuid
import logging
import numpy as np
import os
import pickle

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, PayloadSchemaType

from code_atlas.retrieval.load_graph import load_graph
from code_atlas.retrieval.build_documents import build_documents
from code_atlas.retrieval.embeddings import embed_texts
from code_atlas.graph.builder import CodeGraphBuilder

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

QDRANT_HOST = "qdrant"
QDRANT_PORT = 6333
COLLECTION_NAME = "codeatlas_nodes"


def build_index(repo_id: str, graph=None):
    logger.info("==== BUILD INDEX STARTED ====")
    logger.info(f"Repo ID: {repo_id}")

    if graph is None:
        try:
            graph = load_graph(repo_id)
        except FileNotFoundError:
            logger.info("Graph not found. Building from IR store...")
            builder = CodeGraphBuilder(repo_id)
            graph = builder.build()

            if not graph:
                logger.error("Graph build failed")
                return

            os.makedirs("/root/.code_atlas/graphs", exist_ok=True)
            with open(f"/root/.code_atlas/graphs/{repo_id}.pkl", "wb") as f:
                pickle.dump(graph, f)

            logger.info(f"Graph saved to /root/.code_atlas/graphs/{repo_id}.pkl")

    nodes_count = len(graph.nodes) if hasattr(graph, "nodes") else 0
    logger.info(f"Graph nodes: {nodes_count}")

    docs, metadata = build_documents(graph)
    logger.info(f"Documents: {len(docs)}")

    if not docs:
        logger.warning("No documents generated")
        return

    embeddings = embed_texts(docs)

    if embeddings is None or len(embeddings) == 0:
        logger.error("Embedding generation failed")
        return

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    if not client.collection_exists(COLLECTION_NAME):
        vector_size = len(embeddings[0])

        logger.info(f"Creating collection: {COLLECTION_NAME}")

        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            )
        )

        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="node_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )

    batch_size = 64

    for i in range(0, len(docs), batch_size):
        batch = []
        end = min(i + batch_size, len(docs))

        for j in range(i, end):
            vec = embeddings[j]
            if isinstance(vec, np.ndarray):
                vec = vec.tolist()

            batch.append(
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, docs[j])),
                    vector=vec,
                    payload={
                        "text": docs[j],
                        **metadata[j]
                    }
                )
            )

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch
        )

        logger.info(f"Indexed batch {i}-{end}")

    logger.info("==== INDEXING COMPLETE ====")