def node_to_text(node_id, data):

    return f"""
Node ID: {node_id}
Name: {data.get('name', '')}
Type: {data.get('type', '')}

Code:
{data.get('code', '')}
"""