from code_atlas.graph.builder import CodeGraphBuilder


from code_atlas.graph.builder import CodeGraphBuilder
from code_atlas.graph.store import save_graph


def build_graph(repo_id: str):
    builder = CodeGraphBuilder(repo_id)

    graph = builder.build()

    stats = builder.stats()

    print("Graph built successfully")
    print("Nodes:", stats["nodes"])
    print("Edges:", stats["edges"])

    # NEW: persist graph
    path = save_graph(repo_id, graph)

    print("Graph saved to:", path)

    return graph