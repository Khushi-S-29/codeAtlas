from code_atlas.graph.pipeline import build_graph
from code_atlas.graph.visualiser import GraphVisualizer

repo_id = "github_com-Khushi-S-29-codeAtlas"

graph = build_graph(repo_id)

viz = GraphVisualizer(graph)
viz.build_html("graph.html")

print("Graph visualization generated: graph.html")

from code_atlas.graph.pipeline import build_graph
from code_atlas.graph.deadcodeanalysis import find_dead_functions

repo_id = "github_com-Khushi-S-29-codeAtlas"

graph = build_graph(repo_id)

dead = find_dead_functions(graph)

print("Dead functions:")
for node in dead:
    data = graph.nodes[node]

    print(
        f"{data['name']}  "
        f"({data['file']}:{data['start_line']})"
    )