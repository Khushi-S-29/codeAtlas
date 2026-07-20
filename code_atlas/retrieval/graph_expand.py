def expand_nodes(graph, node_ids, depth=1):
    expanded = set(n for n in node_ids if n in graph)

    for _ in range(depth):
        new_nodes = set()
        for node in expanded:
            new_nodes.update(graph.successors(node))
            new_nodes.update(graph.predecessors(node))
        expanded.update(new_nodes)

    return list(expanded)