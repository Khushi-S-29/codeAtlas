import os
from typing import List
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

# --- CONFIG ---
COLLECTION_NAME = "codeatlas_nodes"
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")


class LocalEmbeddingWrapper:
    """Wrapper for SentenceTransformer embeddings."""
    def __init__(self):
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")

    def embed_query(self, text: str):
        return self.model.encode(text).tolist()

    def embed_documents(self, texts: List[str]):
        return [self.model.encode(t).tolist() for t in texts]


class LangChainRAG:
    """LangChain-based RAG pipeline mirroring native RAG logic."""
    def __init__(self):
        self.embedder = LocalEmbeddingWrapper()
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self.llm = OllamaLLM(model="llama2", base_url=OLLAMA_BASE_URL)

        self.prompt = ChatPromptTemplate.from_template(
            "Use ONLY the following context to answer.\n\nContext:\n{context}\n\nQuestion:\n{question}\n\nAnswer:"
        )

    def retrieve(self, query: str, k: int = 5) -> List[str]:
        """Retrieve top-k relevant code snippets from Qdrant with filtering."""
        query_vector = self.embedder.embed_query(query)
        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=20
        )

        texts = [
            p.payload["text"]
            for p in results.points
            if p.payload and "FUNCTION LEVEL DOCUMENT" in p.payload.get("text", "")
        ]

        filtered = [
            t for t in texts
            if "Code:" in t and ("def " in t or "class " in t) and "Node ID:" not in t and "Name:" not in t
        ]
        if not filtered:
            filtered = texts

        filtered = sorted(
            filtered,
            key=lambda x: ("def " in x, "class " in x, len(x)),
            reverse=True
        )

        return filtered[:k]

    def ask(self, query: str, k: int = 5):
        """Retrieve context and ask LLM."""
        context_list = self.retrieve(query, k=k)
        context = "\n\n".join(context_list)
        if not context:
            return {
                "query": query,
                "context": [],
                "answer": "No relevant code found."
            }

        final_prompt = self.prompt.format(context=context, question=query)
        answer = self.llm.invoke(final_prompt)

        return {
            "query": query,
            "context": context_list,
            "answer": answer.strip()
        }