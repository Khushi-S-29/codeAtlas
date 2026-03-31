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
                limit=20
            )

            texts = [
                p.payload["text"]
                for p in results.points
                if p.payload and "FUNCTION LEVEL DOCUMENT" in p.payload["text"]
            ]

            filtered = []
            for t in texts:
                 if (
                    "Code:" in t and
                    ("def " in t or "class " in t) and
                    "Node ID:" not in t and
                    "Name:" not in t
                ):
                    filtered.append(t)

            if not filtered:
                filtered = texts

            filtered = sorted(
                filtered,
                key=lambda x: ("def " in x, "class " in x, len(x)),
                reverse=True
            )

            return filtered[:k]

        except Exception:
            return []

    def generate(self, query: str, context: List[str]) -> str:
        if not context:
            return "No relevant code found."

        prompt = build_prompt(query, context, max_context=len(context))
        answer = query_ollama(prompt)

        return answer.strip()

    def ask(self, query: str, k: int = 3):
        context = self.retrieve(query, k=k)
        answer = self.generate(query, context)
        return {
            "query": query,
            "context": context,
            "answer": answer
        }

# PURPOSE: Native version of the RAG pipeline (Custom Logic).