import os
from pathlib import Path


INDEXABLE_KINDS = {"module", "class", "function", "method", "constructor", "enum"}


_EXTRA_SEARCH_ROOTS = [
    "/app_repo",
    os.environ.get("CODE_ATLAS_REPO_ROOT"),  
]


def find_file(file_name):
    """
    Works for:
    - Local execution
    - Docker (/app)
    - Cloned repos under /app_repo (or CODE_ATLAS_REPO_ROOT if set)
    - pytest temp directories (/tmp)
    """
    if os.path.exists(file_name):
        return file_name

    app_path = os.path.join("/app", file_name)
    if os.path.exists(app_path):
        return app_path

    for root in _EXTRA_SEARCH_ROOTS:
        if not root:
            continue
        candidate = os.path.join(root, file_name)
        if os.path.exists(candidate):
            return candidate

    tmp_dir = Path("/tmp")
    if tmp_dir.exists():
        relative_name = Path(file_name).name
        for path in tmp_dir.rglob(relative_name):
            return str(path)

    return None


def _read_lines(file_path):
    full_path = find_file(file_path)
    if not full_path:
        return None
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            return f.readlines()
    except Exception:
        return None


def _slice_code(lines, start_line, end_line):
    if start_line is None or end_line is None:
        return None

    start_idx = max(start_line - 1, 0)
    end_idx = min(end_line, len(lines))

    if start_idx >= end_idx:
        return None

    return "".join(lines[start_idx:end_idx]).strip()


def _doc_for_node(node_id, kind, name, file_path, code):
    if kind in ("function", "method", "constructor"):
        return f"""FUNCTION LEVEL DOCUMENT

Node ID: {node_id}
Function Name: {name}
Kind: {kind}
File: {file_path}

Description:
This {kind} '{name}' is defined in {file_path}.
It performs operations based on its implementation.

Keywords:
{name}
{name} function
what does {name} do
implementation of {name}

Code:
{code}
"""

    if kind in ("class", "enum"):
        return f"""CLASS LEVEL DOCUMENT

Node ID: {node_id}
Class Name: {name}
Kind: {kind}
File: {file_path}

Description:
This {kind} '{name}' is defined in {file_path}.

Code:
{code}
"""

    if kind == "module":
        return f"""FILE LEVEL DOCUMENT

Node ID: {node_id}
File: {file_path}

Code:
{code}
"""

    return f"""NODE DOCUMENT

Node ID: {node_id}
Name: {name}
Kind: {kind}
File: {file_path}
"""


def build_documents(graph, repo_id=None):
    docs = []
    metadata = []

    file_cache = {}

    for node_id, data in graph.nodes(data=True):
        kind = data.get("kind", "unknown")

        if kind not in INDEXABLE_KINDS:
            continue

        file_path = data.get("file")
        name = data.get("name")
        start_line = data.get("start_line")
        end_line = data.get("end_line")

        if not file_path or not file_path.endswith((".py", ".js", ".go")):
            continue

        if file_path not in file_cache:
            file_cache[file_path] = _read_lines(file_path)

        lines = file_cache[file_path]
        if lines is None:
            continue

        if kind == "module":
            code = "".join(lines).strip()
        else:
            code = _slice_code(lines, start_line, end_line)

        if not code:
            continue

        docs.append(_doc_for_node(node_id, kind, name, file_path, code))

        metadata.append(
            {
                "repo_id": repo_id,
                "node_id": node_id,
                "node_type": kind,
                "symbol": name,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "file": file_path,
                "type": kind,
                "function": name or "unknown",
                "chunk": 0,
            }
        )

    return docs, metadata