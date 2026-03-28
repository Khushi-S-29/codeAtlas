import os
from typing import List
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from code_atlas.llm.prompt_builder import build_prompt
from code_atlas.llm.answer_generator import query_ollama

COLLECTION_NAME = "codeatlas_nodes"
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

class RAGQuery:
    def __init__(self):
        self.embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    def retrieve(self, query: str, k: int = 3) -> List[str]:
        query_vector = self.embedder.encode(query).tolist()

        try:
            results = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=k
            )
            return [p.payload["text"] for p in results.points if p.payload and "text" in p.payload]
        except Exception:
            return [] 

    def generate(self, query: str, context: List[str]) -> str:
        prompt = build_prompt(query, context)
        return query_ollama(prompt)

    def ask(self, query: str, k: int = 3):
        context = self.retrieve(query, k=k)
        answer = self.generate(query, context)
        return {
            "query": query,
            "context": context,
            "answer": answer
        }

# PURPOSE: Native version of the RAG pipeline (Custom Logic).