import os
from typing import List
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

COLLECTION_NAME = "codeatlas_nodes"
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

class LocalEmbeddingWrapper:
    def __init__(self):
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")

    def embed_query(self, text: str):
        return self.model.encode(text).tolist()

    def embed_documents(self, texts: List[str]):
        return [self.model.encode(t).tolist() for t in texts]

class LangChainRAG:
    def __init__(self):
        self.embedder = LocalEmbeddingWrapper()
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        
        self.llm = OllamaLLM(model="llama2", base_url=OLLAMA_BASE_URL)

        self.prompt = ChatPromptTemplate.from_template(
            "Use ONLY the following context to answer.\n\nContext:\n{context}\n\nQuestion:\n{question}\n\nAnswer:"
        )

    def retrieve(self, query: str, k: int = 5):
        query_vector = self.embedder.embed_query(query)
        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=k
        )
        return [p.payload["text"] for p in results.points if p.payload and "text" in p.payload]

    def ask(self, query: str):
        context_list = self.retrieve(query)
        context = "\n\n".join(context_list)
        if not context:
            return "No relevant code found."
        
        chain = self.prompt | self.llm
        return chain.invoke({"context": context, "question": query})

# PURPOSE: LangChain version of the RAG pipeline.