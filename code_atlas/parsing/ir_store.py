
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from code_atlas.core.config import DATA_DIR
from code_atlas.core.models import (
    IRNode, NodeKind, Parameter,
    CallEdge, ImportEdge, InheritanceEdge, ReferenceEdge,
)

logger = logging.getLogger(__name__)

IR_DIR = DATA_DIR / "ir"
IR_DIR.mkdir(parents=True, exist_ok=True)

_CREATE_NODES = """
CREATE TABLE IF NOT EXISTS ir_nodes (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    kind             TEXT NOT NULL,
    file_path        TEXT NOT NULL,
    start_line       INTEGER NOT NULL,
    end_line         INTEGER NOT NULL,
    start_col        INTEGER NOT NULL DEFAULT 0,
    end_col          INTEGER NOT NULL DEFAULT 0,
    language         TEXT NOT NULL,
    parent_id        TEXT,
    children         TEXT NOT NULL DEFAULT '[]',
    value            TEXT,
    typed_parameters TEXT NOT NULL DEFAULT '[]',
    parent_class     TEXT,
    return_type      TEXT,
    docstring        TEXT,
    signature        TEXT,
    is_exported      INTEGER NOT NULL DEFAULT 1,
    parameters       TEXT NOT NULL DEFAULT '[]',
    calls            TEXT NOT NULL DEFAULT '[]',
    imports          TEXT NOT NULL DEFAULT '[]',
    bases            TEXT NOT NULL DEFAULT '[]',
    decorators       TEXT NOT NULL DEFAULT '[]'
);
"""

_CREATE_CALL_EDGES = """
CREATE TABLE IF NOT EXISTS ir_call_edges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_id      TEXT NOT NULL,
    callee_name    TEXT NOT NULL,
    callee_id      TEXT,
    file_path      TEXT NOT NULL DEFAULT '',
    line_number    INTEGER NOT NULL DEFAULT 0,
    col_number     INTEGER NOT NULL DEFAULT 0,
    is_method_call INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_IMPORT_EDGES = """
CREATE TABLE IF NOT EXISTS ir_import_edges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file    TEXT NOT NULL,
    target_module  TEXT NOT NULL,
    alias          TEXT,
    line_number    INTEGER NOT NULL DEFAULT 0,
    is_default     INTEGER NOT NULL DEFAULT 0,
    is_wildcard    INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_INHERITANCE_EDGES = """
CREATE TABLE IF NOT EXISTS ir_inheritance_edges (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id     TEXT NOT NULL,
    parent_name  TEXT NOT NULL,
    parent_id    TEXT,
    kind         TEXT NOT NULL DEFAULT 'inherits'
);
"""

_CREATE_REFERENCE_EDGES = """
CREATE TABLE IF NOT EXISTS ir_reference_edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL,
    target_name TEXT NOT NULL,
    target_id   TEXT,
    line_number INTEGER NOT NULL DEFAULT 0
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_nodes_file   ON ir_nodes(file_path);",
    "CREATE INDEX IF NOT EXISTS idx_nodes_kind   ON ir_nodes(kind);",
    "CREATE INDEX IF NOT EXISTS idx_nodes_name   ON ir_nodes(name);",
    "CREATE INDEX IF NOT EXISTS idx_nodes_parent ON ir_nodes(parent_id);",
    "CREATE INDEX IF NOT EXISTS idx_calls_caller ON ir_call_edges(caller_id);",
    "CREATE INDEX IF NOT EXISTS idx_calls_file   ON ir_call_edges(file_path);",
    "CREATE INDEX IF NOT EXISTS idx_imports_src  ON ir_import_edges(source_file);",
    "CREATE INDEX IF NOT EXISTS idx_inherit_child ON ir_inheritance_edges(child_id);",
]

_MIGRATIONS = [
    "ALTER TABLE ir_nodes ADD COLUMN start_col        INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ir_nodes ADD COLUMN end_col          INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ir_nodes ADD COLUMN parent_id        TEXT",
    "ALTER TABLE ir_nodes ADD COLUMN children         TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE ir_nodes ADD COLUMN value            TEXT",
    "ALTER TABLE ir_nodes ADD COLUMN typed_parameters TEXT NOT NULL DEFAULT '[]'",
]


class IRStore:
    """
    Persists and retrieves IRNode objects and typed edge objects
    for a single repository.
    """

    def __init__(self, repo_id: str, ir_dir: Optional[Path] = None) -> None:
        self.repo_id = repo_id
        _dir = ir_dir or IR_DIR
        _dir.mkdir(parents=True, exist_ok=True)
        self.db_path = _dir / f"{repo_id}.db"
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL;")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init_db(self) -> None:
        with self._conn() as con:
            con.execute(_CREATE_NODES)
            con.execute(_CREATE_CALL_EDGES)
            con.execute(_CREATE_IMPORT_EDGES)
            con.execute(_CREATE_INHERITANCE_EDGES)
            con.execute(_CREATE_REFERENCE_EDGES)
            for idx in _INDEXES:
                con.execute(idx)
            for stmt in _MIGRATIONS:
                try:
                    con.execute(stmt)
                except sqlite3.OperationalError:
                    pass  

    def delete_file(self, file_path: str) -> int:
        with self._conn() as con:
            cur = con.execute("DELETE FROM ir_nodes WHERE file_path = ?", (file_path,))
            con.execute("DELETE FROM ir_call_edges WHERE file_path = ?", (file_path,))
            con.execute("DELETE FROM ir_import_edges WHERE source_file = ?", (file_path,))
            child_ids = [
                r[0] for r in con.execute(
                    "SELECT id FROM ir_nodes WHERE file_path = ?", (file_path,)
                ).fetchall()
            ]
            if child_ids:
                placeholders = ",".join("?" * len(child_ids))
                con.execute(
                    f"DELETE FROM ir_inheritance_edges WHERE child_id IN ({placeholders})",
                    child_ids,
                )
        deleted = cur.rowcount
        logger.debug("Deleted %d nodes for %s", deleted, file_path)
        return deleted

    def upsert_nodes(self, nodes: list[IRNode]) -> None:
        if not nodes:
            return
        rows = [_node_to_row(n) for n in nodes]
        with self._conn() as con:
            con.executemany(
                """
                INSERT OR REPLACE INTO ir_nodes
                  (id, name, kind, file_path, start_line, end_line,
                   start_col, end_col, language,
                   parent_id, children, value, typed_parameters,
                   parent_class, return_type, docstring, signature, is_exported,
                   parameters, calls, imports, bases, decorators)
                VALUES
                  (:id, :name, :kind, :file_path, :start_line, :end_line,
                   :start_col, :end_col, :language,
                   :parent_id, :children, :value, :typed_parameters,
                   :parent_class, :return_type, :docstring, :signature, :is_exported,
                   :parameters, :calls, :imports, :bases, :decorators)
                """,
                rows,
            )
        logger.debug("Upserted %d IR nodes.", len(nodes))


    def upsert_call_edges(self, edges: list[CallEdge]) -> None:
        if not edges:
            return
        rows = [
            {
                "caller_id":      e.caller_id,
                "callee_name":    e.callee_name,
                "callee_id":      e.callee_id,
                "file_path":      e.file_path,
                "line_number":    e.line_number,
                "col_number":     e.col_number,
                "is_method_call": int(e.is_method_call),
            }
            for e in edges
        ]
        with self._conn() as con:
            con.executemany(
                """
                INSERT INTO ir_call_edges
                  (caller_id, callee_name, callee_id, file_path,
                   line_number, col_number, is_method_call)
                VALUES
                  (:caller_id, :callee_name, :callee_id, :file_path,
                   :line_number, :col_number, :is_method_call)
                """,
                rows,
            )

    def upsert_import_edges(self, edges: list[ImportEdge]) -> None:
        if not edges:
            return
        rows = [
            {
                "source_file":   e.source_file,
                "target_module": e.target_module,
                "alias":         e.alias,
                "line_number":   e.line_number,
                "is_default":    int(e.is_default),
                "is_wildcard":   int(e.is_wildcard),
            }
            for e in edges
        ]
        with self._conn() as con:
            con.executemany(
                """
                INSERT INTO ir_import_edges
                  (source_file, target_module, alias, line_number, is_default, is_wildcard)
                VALUES
                  (:source_file, :target_module, :alias, :line_number, :is_default, :is_wildcard)
                """,
                rows,
            )

    def upsert_inheritance_edges(self, edges: list[InheritanceEdge]) -> None:
        if not edges:
            return
        rows = [
            {
                "child_id":    e.child_id,
                "parent_name": e.parent_name,
                "parent_id":   e.parent_id,
                "kind":        e.kind,
            }
            for e in edges
        ]
        with self._conn() as con:
            con.executemany(
                """
                INSERT INTO ir_inheritance_edges (child_id, parent_name, parent_id, kind)
                VALUES (:child_id, :parent_name, :parent_id, :kind)
                """,
                rows,
            )

    def upsert_reference_edges(self, edges: list[ReferenceEdge]) -> None:
        if not edges:
            return
        rows = [
            {
                "source_id":   e.source_id,
                "target_name": e.target_name,
                "target_id":   e.target_id,
                "line_number": e.line_number,
            }
            for e in edges
        ]
        with self._conn() as con:
            con.executemany(
                """
                INSERT INTO ir_reference_edges (source_id, target_name, target_id, line_number)
                VALUES (:source_id, :target_name, :target_id, :line_number)
                """,
                rows,
            )


    def load_all(self) -> list[IRNode]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM ir_nodes").fetchall()
        return [_row_to_node(r) for r in rows]

    def load_by_file(self, file_path: str) -> list[IRNode]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM ir_nodes WHERE file_path = ?", (file_path,)
            ).fetchall()
        return [_row_to_node(r) for r in rows]

    def load_by_kind(self, kind: NodeKind) -> list[IRNode]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM ir_nodes WHERE kind = ?", (kind.value,)
            ).fetchall()
        return [_row_to_node(r) for r in rows]

    def load_children(self, parent_id: str) -> list[IRNode]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM ir_nodes WHERE parent_id = ?", (parent_id,)
            ).fetchall()
        return [_row_to_node(r) for r in rows]

    def find_by_name(self, name: str) -> list[IRNode]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM ir_nodes WHERE lower(name) = lower(?)", (name,)
            ).fetchall()
        return [_row_to_node(r) for r in rows]


    def load_call_edges(self, file_path: Optional[str] = None) -> list[CallEdge]:
        with self._conn() as con:
            if file_path:
                rows = con.execute(
                    "SELECT * FROM ir_call_edges WHERE file_path = ?", (file_path,)
                ).fetchall()
            else:
                rows = con.execute("SELECT * FROM ir_call_edges").fetchall()
        return [
            CallEdge(
                caller_id=r["caller_id"],
                callee_name=r["callee_name"],
                callee_id=r["callee_id"],
                file_path=r["file_path"],
                line_number=r["line_number"],
                col_number=r["col_number"],
                is_method_call=bool(r["is_method_call"]),
            )
            for r in rows
        ]

    def load_import_edges(self, source_file: Optional[str] = None) -> list[ImportEdge]:
        with self._conn() as con:
            if source_file:
                rows = con.execute(
                    "SELECT * FROM ir_import_edges WHERE source_file = ?", (source_file,)
                ).fetchall()
            else:
                rows = con.execute("SELECT * FROM ir_import_edges").fetchall()
        return [
            ImportEdge(
                source_file=r["source_file"],
                target_module=r["target_module"],
                alias=r["alias"],
                line_number=r["line_number"],
                is_default=bool(r["is_default"]),
                is_wildcard=bool(r["is_wildcard"]),
            )
            for r in rows
        ]

    def load_inheritance_edges(self) -> list[InheritanceEdge]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM ir_inheritance_edges").fetchall()
        return [
            InheritanceEdge(
                child_id=r["child_id"],
                parent_name=r["parent_name"],
                parent_id=r["parent_id"],
                kind=r["kind"],
            )
            for r in rows
        ]


    def stats(self) -> dict:
        with self._conn() as con:
            total = con.execute("SELECT COUNT(*) FROM ir_nodes").fetchone()[0]
            by_kind = con.execute(
                "SELECT kind, COUNT(*) AS cnt FROM ir_nodes GROUP BY kind ORDER BY cnt DESC"
            ).fetchall()
            by_lang = con.execute(
                "SELECT language, COUNT(*) AS cnt FROM ir_nodes GROUP BY language ORDER BY cnt DESC"
            ).fetchall()
            call_count    = con.execute("SELECT COUNT(*) FROM ir_call_edges").fetchone()[0]
            import_count  = con.execute("SELECT COUNT(*) FROM ir_import_edges").fetchone()[0]
            inherit_count = con.execute("SELECT COUNT(*) FROM ir_inheritance_edges").fetchone()[0]
        return {
            "total_nodes":       total,
            "by_kind":           {r["kind"]: r["cnt"] for r in by_kind},
            "by_language":       {r["language"]: r["cnt"] for r in by_lang},
            "call_edges":        call_count,
            "import_edges":      import_count,
            "inheritance_edges": inherit_count,
        }



def _node_to_row(node: IRNode) -> dict:
    return {
        "id":               node.id,
        "name":             node.name,
        "kind":             node.kind if isinstance(node.kind, str) else node.kind.value,
        "file_path":        node.file_path,
        "start_line":       node.start_line,
        "end_line":         node.end_line,
        "start_col":        node.start_col,
        "end_col":          node.end_col,
        "language":         node.language,
        "parent_id":        node.parent_id,
        "children":         json.dumps(node.children),
        "value":            node.value,
        "typed_parameters": json.dumps([p.model_dump() for p in node.typed_parameters]),
        "parent_class":     node.parent_class,
        "return_type":      node.return_type,
        "docstring":        node.docstring,
        "signature":        node.signature,
        "is_exported":      int(node.is_exported),
        "parameters":       json.dumps(node.parameters),
        "calls":            json.dumps(node.calls),
        "imports":          json.dumps(node.imports),
        "bases":            json.dumps(node.bases),
        "decorators":       json.dumps(node.decorators),
    }


def _row_to_node(row: sqlite3.Row) -> IRNode:
    keys = row.keys()

    typed_params_raw = row["typed_parameters"] if "typed_parameters" in keys else "[]"
    try:
        typed_params_data = json.loads(typed_params_raw or "[]")
        typed_parameters  = [Parameter(**p) for p in typed_params_data]
    except Exception:
        typed_parameters = []

    return IRNode(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        file_path=row["file_path"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        start_col=row["start_col"]    if "start_col"  in keys else 0,
        end_col=row["end_col"]        if "end_col"    in keys else 0,
        language=row["language"],
        parent_id=row["parent_id"]    if "parent_id"  in keys else None,
        children=json.loads(row["children"]) if "children" in keys else [],
        value=row["value"]            if "value"     in keys else None,
        typed_parameters=typed_parameters,
        parent_class=row["parent_class"],
        return_type=row["return_type"],
        docstring=row["docstring"],
        signature=row["signature"],
        is_exported=bool(row["is_exported"]),
        parameters=json.loads(row["parameters"]),
        calls=json.loads(row["calls"]),
        imports=json.loads(row["imports"]),
        bases=json.loads(row["bases"]),
        decorators=json.loads(row["decorators"]),
    )



'''
Why IRStore exists

Parsing generates:

IRNode
CallEdge
ImportEdge
InheritanceEdge
ReferenceEdge

These must be stored because:

graph builder reads from here
'''