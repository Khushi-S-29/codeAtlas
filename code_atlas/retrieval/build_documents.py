import os
from pathlib import Path


INDEXABLE_KINDS = {"module", "class", "function", "method", "constructor", "enum"}


def find_file(file_name):
    """
    Works for:
    - Local execution
    - Docker (/app)
    - pytest temp directories (/tmp)
    """
    if os.path.exists(file_name):
        return file_name

    app_path = os.path.join("/app", file_name)
    if os.path.exists(app_path):
        return app_path

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
    """
    start_line/end_line are 1-indexed, inclusive (as produced by
    most Python AST-based parsers). Falls back gracefully if missing.
    """
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


def build_documents(graph):
    """
    One document per graph node. node_id, node_type (kind), and symbol
    (name) are taken directly from the graph's own attributes, and code
    is sliced from the source file using the node's start_line/end_line
    — no regex extraction, no name-matching guesswork.

    Only structurally meaningful kinds are indexed (INDEXABLE_KINDS).
    Nodes like single-line 'assignment' and 'import' statements are
    skipped — they add noise to the vector index without being useful
    retrieval units. They remain in the graph itself and are still
    traversable during expand_nodes(), just not embedded/returned as
    context.
    """
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
                "node_id": node_id,
                "node_type": kind,
                "symbol": name,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                # backward-compatible keys
                "file": file_path,
                "type": kind,
                "function": name or "unknown",
                "chunk": 0,
            }
        )

    return docs, metadata