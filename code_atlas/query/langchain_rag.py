import os
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

COLLECTION_NAME = "codeatlas_nodes"
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama_server:11434")

_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("BAAI/bge-large-en-v1.5", device="cpu")
    return _embedder


def boost_score(query: str, payload: dict, vector_score: float) -> float:
    score = vector_score
    query_lower = query.lower()

    file_path = payload.get("file_path") or payload.get("file", "") or ""
    filename = file_path.split("/")[-1].lower()
    func_name = payload.get("symbol") or payload.get("function", "") or ""

    if file_path.lower() in query_lower:
        score += 0.08
    elif filename and filename in query_lower:
        score += 0.05

    if func_name and func_name.lower() in query_lower:
        score += 0.05

    return score


class LocalEmbeddingWrapper:
    def __init__(self):
        self.model = get_embedder()

    def embed_query(self, text: str):
        return self.model.encode(text).tolist()

    def embed_documents(self, texts: List[str]):
        return [self.model.encode(t).tolist() for t in texts]


class LangChainRAG:
    def __init__(self, repo_id: str = None):
        self.embedder = LocalEmbeddingWrapper()
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self.repo_id = repo_id
        self.llm = OllamaLLM(model="llama2", base_url=OLLAMA_BASE_URL)
        self.prompt = ChatPromptTemplate.from_template(
            "You are a senior software engineer analyzing a codebase called CodeAtlas.\n\n"
            "Answer the question using ONLY the code context provided below.\n"
            "Be specific: mention actual function names, file names, and what they do.\n"
            "Do NOT hallucinate code that is not in the context.\n\n"
            "Context:\n{context}\n\nQuestion:\n{question}\n\nAnswer:"
        )

    def retrieve(self, query: str, k: int = 5) -> List[str]:
        query_vector = self.embedder.embed_query(query)

        query_kwargs = {
            "collection_name": COLLECTION_NAME,
            "query": query_vector,
            "limit": 30,
            "with_payload": True,
        }

        if self.repo_id:
            query_kwargs["query_filter"] = Filter(
                must=[
                    FieldCondition(
                        key="repo_id",
                        match=MatchValue(value=self.repo_id)
                    )
                ]
            )

        results = self.client.query_points(**query_kwargs)

        scored_points = []
        for p in results.points:
            payload = p.payload or {}
            if not payload:
                continue
            boosted = boost_score(query, payload, p.score)
            scored_points.append((boosted, p))
        scored_points.sort(key=lambda x: x[0], reverse=True)

        seen_texts = set()
        filtered = []

        for _, p in scored_points:
            payload = p.payload or {}
            file_path = payload.get("file_path") or payload.get("file", "") or ""
            text = payload.get("text", "")

            if not text:
                continue

            if any(x in file_path.lower() for x in ["test_", "/tests/", "\\tests\\"]):
                continue

            is_new_format = any(f"TYPE: {t}" in text for t in ["FUNCTION", "CLASS", "METHOD", "FILE", "MODULE_LEVEL"])
            is_old_format = "FUNCTION LEVEL DOCUMENT" in text

            if not (is_new_format or is_old_format):
                continue

            if "Code:" not in text:
                continue

            if text in seen_texts:
                continue

            seen_texts.add(text)
            filtered.append(text)

        return filtered[:k]

    def ask(self, query: str, k: int = 5):
        context_list = self.retrieve(query, k=k)
        context = "\n\n---\n\n".join(context_list)

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