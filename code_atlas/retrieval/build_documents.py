def node_to_text(node_id, data):

    name = data.get("name", "")
    node_type = data.get("type", "")
    code = data.get("code", "")

    text = f"""
Node ID: {node_id}
Name: {name}
Type: {node_type}

Code:
{code}
"""

    return text


def build_documents(graph):

    documents = []
    metadata = []

    for node_id, data in graph.nodes(data=True):

        text = node_to_text(node_id, data)

        documents.append(text)

        metadata.append({
            "node_id": node_id,
            "name": data.get("name", ""),
            "type": data.get("type", "")
        })

    return documents, metadata