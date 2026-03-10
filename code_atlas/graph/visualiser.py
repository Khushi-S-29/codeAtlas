from pyvis.network import Network


class GraphVisualizer:

    def __init__(self, graph):
        self.graph = graph

    def build_html(self, output_file="code_graph.html"):
        net = Network(
            height="750px",
            width="100%",
            directed=True,
            bgcolor="#111111",
            font_color="white",
        )

        for node, data in self.graph.nodes(data=True):

            label = data.get("name", "unknown")
            kind = data.get("kind", "node")

            color = self._color_for_kind(kind)

            net.add_node(
                node,
                label=label,
                title=f"{kind} : {data.get('file','')}",
                color=color,
            )

        for src, dst, edge_data in self.graph.edges(data=True):

            edge_type = edge_data.get("type", "")

            net.add_edge(
                src,
                 dst,
                label=edge_type,      # shows on edge
                title=edge_type,      # shows on hover
                arrows="to"
            )

        # net.show(output_file)
        net.write_html(output_file)

    def _color_for_kind(self, kind):

        colors = {
            "module": "#FFD166",
            "class": "#EF476F",
            "function": "#06D6A0",
            "method": "#118AB2",
            "import": "#8D99AE",
        }

        return colors.get(kind, "#CCCCCC")