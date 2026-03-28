def expand_nodes(graph, node_ids, depth=1):

    expanded = set(node_ids)

    for _ in range(depth):

        new_nodes = set()

        for node in expanded:
            neighbors = list(graph.neighbors(node))
            new_nodes.update(neighbors)

        expanded.update(new_nodes)

    return list(expanded)