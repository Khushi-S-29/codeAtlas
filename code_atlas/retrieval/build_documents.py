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
import os
import re
from pathlib import Path


def extract_functions(code):
    """
    Extract Python functions robustly (handles spacing + multiple defs)
    """
    pattern = r"def\s+\w+\(.*?\):[\s\S]*?(?=\n\s*def\s|\Z)"
    return re.findall(pattern, code)


def find_file(file_name):
    """
    Works for:
    - pytest tmp_path (/tmp)
    - docker (/app)
    - local execution
    """

    if os.path.exists(file_name):
        return file_name

    app_path = os.path.join("/app", file_name)
    if os.path.exists(app_path):
        return app_path

    tmp_dir = Path("/tmp")
    if tmp_dir.exists():
        for path in tmp_dir.rglob(file_name):
            return str(path)

    return None


def build_documents(graph):
    docs = []
    metadata = []

    seen_files = set()

    for node_id, data in graph.nodes(data=True):
        file_path = data.get("file")

        if not file_path or file_path in seen_files:
            continue

        if not file_path.endswith((".py", ".js", ".go")):
            continue

        seen_files.add(file_path)

        full_path = find_file(file_path)
        if not full_path:
            continue

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception:
            continue

        code = code.strip()
        if not code:
            continue

        functions = extract_functions(code)

        for idx, func in enumerate(functions):
            func = func.strip()

            if len(func) < 10:
                continue

            func_name_match = re.match(r"def\s+(\w+)\(", func)
            func_name = func_name_match.group(1) if func_name_match else f"func_{idx}"

            docs.append(f"""FUNCTION LEVEL DOCUMENT

Function Name: {func_name}
File: {file_path}

Description:
This function '{func_name}' is defined in {file_path}.
It performs operations based on its implementation.

Keywords:
{func_name}
{func_name} function
what does {func_name} do
implementation of {func_name}

Code:
{func}
""")
            metadata.append({
                "file": file_path,
                "function": func_name,
                "chunk": idx,
                "type": "function"
            })

        docs.append(
            f"""FILE LEVEL DOCUMENT

File: {file_path}

Code:
{code}
"""
        )

        metadata.append({
            "file": file_path,
            "function": "full_file",
            "chunk": 0,
            "type": "file"
        })

    return docs, metadata