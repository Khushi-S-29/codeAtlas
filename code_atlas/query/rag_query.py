import os
import time
from contextlib import contextmanager
from typing import List

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

from code_atlas.llm.prompt_builder import build_prompt
from code_atlas.llm.answer_generator import query_ollama
from code_atlas.retrieval.graph_expand import expand_nodes
from code_atlas.retrieval.load_graph import load_graph


COLLECTION_NAME = "codeatlas_nodes"
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

_embedder = None
_client = None


def get_embedder():
    global _embedder
    if _embedder is None:
        print("[INIT] Loading embedder...")
        _embedder = SentenceTransformer("BAAI/bge-large-en-v1.5", device="cpu")
    return _embedder


def get_client():
    global _client
    if _client is None:
        _client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _client


@contextmanager
def timer(label):
    start = time.perf_counter()
    yield
    print(f"[TIMER] {label}: {time.perf_counter() - start:.3f}s")


def boost_score(query: str, payload: dict, vector_score: float) -> float:
    score = vector_score
    query_lower = query.lower()

    file_path = payload.get("file", "") or ""
    filename = file_path.split("/")[-1].lower()
    func_name = payload.get("name", "") or ""

    if file_path.lower() in query_lower:
        score += 0.08
    elif filename and filename in query_lower:
        score += 0.05

    if func_name and func_name.lower() in query_lower:
        score += 0.05

    return score


class RAGQuery:

    def __init__(self, repo_id: str = None):
        self.embedder = get_embedder()
        self.client = get_client()
        self.repo_id = repo_id
        self.graph = None

        if repo_id:
            with timer("graph load"):
                try:
                    self.graph = load_graph(repo_id)
                    print(f"[GRAPH] Loaded: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
                except Exception as e:
                    print(f"[GRAPH] Could not load graph: {e}")

    def retrieve(self, query: str, k: int = 5) -> List[str]:

        with timer("query embedding"):
            query_vector = self.embedder.encode(query).tolist()

        with timer("vector search"):
            results = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=30,
                with_payload=True
            )

        points = results.points

        print(f"\n[RETRIEVED] top {len(points)} raw results:")
        for i, point in enumerate(points):
            payload = point.payload or {}
            print(f"  [{i}] score={point.score:.3f} | file={payload.get('file')} | type={payload.get('type')} | name={payload.get('name')}")

        with timer("reranking"):
            scored_points = []
            for point in points:
                payload = point.payload or {}
                if not payload:
                    continue
                boosted = boost_score(query, payload, point.score)
                scored_points.append((boosted, point))
            scored_points.sort(key=lambda x: x[0], reverse=True)

        texts = []
        node_ids = []
        seen_texts = set()

        for _, point in scored_points:
            payload = point.payload or {}
            file_path = payload.get("file", "")

            if any(x in file_path.lower() for x in ["test_", "/tests/", "\\tests\\"]):
                continue

            text = payload.get("text", "")
            if not text:
                continue

            is_new_format = any(f"TYPE: {t}" in text for t in ["FUNCTION", "CLASS", "METHOD", "FILE", "MODULE_LEVEL"])
            is_old_format = "FUNCTION LEVEL DOCUMENT" in text

            if not (is_new_format or is_old_format):
                continue

            if text in seen_texts:
                continue

            seen_texts.add(text)
            texts.append(text)

            if payload.get("node_id"):
                node_ids.append(payload["node_id"])

        if self.graph and node_ids:
            with timer("graph expansion"):
                expanded_ids = expand_nodes(self.graph, node_ids, depth=2)
                print(f"[GRAPH] Expanded {len(node_ids)} → {len(expanded_ids)} nodes")

                for node_id in expanded_ids:
                    if node_id in node_ids:
                        continue
                    try:
                        extra, _ = self.client.scroll(
                            collection_name=COLLECTION_NAME,
                            scroll_filter={
                                "must": [{"key": "node_id", "match": {"value": node_id}}]
                            },
                            limit=3,
                            with_payload=True
                        )
                        for point in extra:
                            payload = point.payload or {}
                            text = payload.get("text", "")
                            if text and text not in seen_texts:
                                seen_texts.add(text)
                                texts.append(text)
                    except Exception as e:
                        print(f"[GRAPH FETCH ERROR] {e}")

        return texts[:k]

    def generate(self, query: str, context: List[str]) -> str:
        if not context:
            return "No relevant code found."

        with timer("prompt build + LLM call"):
            prompt = build_prompt(query, context, max_context=len(context))
            answer = query_ollama(prompt)

        return answer.strip()

    def ask(self, query: str, k: int = 5):
        print(f"\n{'='*50}\n[QUERY] {query}\n{'='*50}")
        start = time.perf_counter()

        context = self.retrieve(query, k)
        answer = self.generate(query, context)

        print(f"[TIMER] total: {time.perf_counter() - start:.3f}s")

        return {
            "query": query,
            "context": context,
            "answer": answer
        }