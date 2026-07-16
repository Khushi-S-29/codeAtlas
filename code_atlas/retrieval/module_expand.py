from qdrant_client.models import Filter, FieldCondition, MatchValue


def expand_module_seeds(client, collection_name, hits, limit_per_file=5):
    """
    For module-kind hits, pull sibling function/method/class chunks
    from the same file. Compensates for the graph having no
    module -> function containment edges.
    """
    extra_ids = set()

    for h in hits:
        if h.payload.get("node_type") != "module":
            continue

        file_path = h.payload.get("file_path")
        if not file_path:
            continue

        siblings, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))],
                must_not=[FieldCondition(key="node_type", match=MatchValue(value="module"))],
            ),
            limit=limit_per_file,
            with_payload=True,
        )
        for s in siblings:
            nid = s.payload.get("node_id")
            if nid:
                extra_ids.add(nid)

    return extra_ids