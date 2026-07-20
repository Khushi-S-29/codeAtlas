from qdrant_client.models import Filter, FieldCondition, MatchAny

from code_atlas.retrieval.graph_expand import expand_nodes
from code_atlas.retrieval.module_expand import expand_module_seeds  # new


def fetch_chunks_by_node_ids(client, collection_name, node_ids):
    if not node_ids:
        return []

    results, _ = client.scroll(
        collection_name=collection_name,
        scroll_filter=Filter(
            must=[FieldCondition(key="node_id", match=MatchAny(any=node_ids))]
        ),
        limit=len(node_ids) * 5,
        with_payload=True,
    )
    return results


def graph_rag_retrieve(client, collection_name, graph, query_vector, top_k=5, depth=1):
    hits = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=top_k,
    ).points

    seed_node_ids = [h.payload["node_id"] for h in hits if h.payload.get("node_id")]
    valid_seeds = [n for n in seed_node_ids if n in graph]

    expanded_ids = expand_nodes(graph, valid_seeds, depth=depth) if valid_seeds else []

    module_fallback_ids = expand_module_seeds(client, collection_name, hits)

    all_expanded_ids = set(expanded_ids) | module_fallback_ids
    expanded_points = fetch_chunks_by_node_ids(client, collection_name, list(all_expanded_ids))

    merged = {}
    for h in hits:
        node_id = h.payload.get("node_id")
        if node_id:
            merged[node_id] = h.payload.get("text")

    for p in expanded_points:
        node_id = p.payload.get("node_id")
        if node_id and node_id not in merged:
            merged[node_id] = p.payload.get("text")

    return list(merged.values())