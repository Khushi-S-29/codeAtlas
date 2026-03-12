from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, computed_field

class FileStatus(str, Enum):
    NEW      = "new"      
    MODIFIED = "modified"  
    UNCHANGED= "unchanged" 
    DELETED  = "deleted"   


class IngestionSource(str, Enum):
    GIT_URL    = "git_url"    
    LOCAL_PATH = "local_path" 

class FileRecord(BaseModel):
    path: str
    absolute_path: Optional[str] = Field(default=None, exclude=True)
    language: str
    sha256: str
    size_bytes: int
    last_modified: datetime
    status: FileStatus = FileStatus.NEW
    line_count: int = 0
    model_config = {"use_enum_values": True}

    @computed_field 
    @property
    def extension(self) -> str:
        return Path(self.path).suffix.lower()

    @computed_field  
    @property
    def filename(self) -> str:
        return Path(self.path).name

    def __repr__(self) -> str:
        return f"<FileRecord {self.path} [{self.language}] {self.status}>"

class RepoManifest(BaseModel):
    repo_id: str
    source: str                        
    source_type: IngestionSource
    local_path: str
    git_branch: Optional[str] = None
    git_commit: Optional[str] = None     
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    previous_index_at: Optional[datetime] = None  
    files: list[FileRecord] = Field(default_factory=list)

    model_config = {"use_enum_values": True}
    @computed_field  
    @property
    def change_set(self) -> list[FileRecord]:
        return [f for f in self.files if f.status in (FileStatus.NEW, FileStatus.MODIFIED)]

    @computed_field 
    @property
    def deleted_files(self) -> list[FileRecord]:
        return [f for f in self.files if f.status == FileStatus.DELETED]

    @computed_field 
    @property
    def unchanged_files(self) -> list[FileRecord]:
        return [f for f in self.files if f.status == FileStatus.UNCHANGED]

    @computed_field  
    @property
    def language_breakdown(self) -> dict[str, int]:
        """{ language: file_count } for all non-deleted files."""
        result: dict[str, int] = {}
        for f in self.files:
            if f.status != FileStatus.DELETED:
                result[f.language] = result.get(f.language, 0) + 1
        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))

    @computed_field  
    @property
    def total_source_files(self) -> int:
        return len([f for f in self.files if f.status != FileStatus.DELETED])

    @computed_field  
    @property
    def total_lines(self) -> int:
        return sum(f.line_count for f in self.files if f.status != FileStatus.DELETED)

    def summary(self) -> str:
        lines = [
            f"Repo      : {self.repo_id}",
            f"Source    : {self.source} ({self.source_type})",
            f"Commit    : {self.git_commit or 'N/A'}",
            f"Files     : {self.total_source_files} ({self.total_lines:,} lines)",
            f"New       : {len([f for f in self.change_set if f.status == FileStatus.NEW])}",
            f"Modified  : {len([f for f in self.change_set if f.status == FileStatus.MODIFIED])}",
            f"Unchanged : {len(self.unchanged_files)}",
            f"Deleted   : {len(self.deleted_files)}",
            f"Languages : {self.language_breakdown}",
        ]
        return "\n".join(lines)


class NodeKind(str, Enum):
    """
    Universal node types matching the spec's five categories:
    Structural / Object-Oriented / Execution / Dependency / Behavior / Type
    """
    # Structural
    FILE       = "file"
    MODULE     = "module"
    PACKAGE    = "package"
    NAMESPACE  = "namespace"

    # Object-Oriented
    CLASS      = "class"
    INTERFACE  = "interface"
    STRUCT     = "struct"
    ENUM       = "enum"

    # Execution
    FUNCTION    = "function"
    METHOD      = "method"
    CONSTRUCTOR = "constructor"
    LAMBDA      = "lambda"

    # Dependency
    IMPORT  = "import"
    EXPORT  = "export"
    INCLUDE = "include"
    REQUIRE = "require"

    # Behavior
    CALL_EXPRESSION  = "call_expression"
    ASSIGNMENT       = "assignment"
    RETURN_STATEMENT = "return_statement"
    CONDITIONAL      = "conditional"
    LOOP             = "loop"

    # Type
    TYPE_ANNOTATION = "type_annotation"
    GENERIC_TYPE    = "generic_type"
    UNION_TYPE      = "union_type"

    # Legacy alias
    VARIABLE = "variable"


class Parameter(BaseModel):
    name: str
    type: Optional[str] = None     
    def __repr__(self) -> str:
        return f"{self.name}: {self.type}" if self.type else self.name


class IRNode(BaseModel):
    """
    Language-agnostic Intermediate Representation node.

    Matches the spec's ASTNode schema:
        node_id, node_type (kind), language, name, value,
        start_line, end_line, start_column (start_col), end_column (end_col),
        parent (parent_id), children ([node_id]), file_path
    """
    id:         str
    name:       str
    kind:       NodeKind
    file_path:  str
    language:   str

    start_line: int
    end_line:   int
    start_col:  int = 0
    end_col:    int = 0

    parent_id: Optional[str]  = None
    children:  list[str]      = Field(default_factory=list)

    value: Optional[str] = None

    typed_parameters: list[Parameter] = Field(default_factory=list)

    parameters: list[str] = Field(default_factory=list)

    parent_class: Optional[str] = None
    return_type:  Optional[str] = None
    docstring:    Optional[str] = None
    signature:    Optional[str] = None
    calls:        list[str]     = Field(default_factory=list)
    imports:      list[str]     = Field(default_factory=list)
    bases:        list[str]     = Field(default_factory=list)
    decorators:   list[str]     = Field(default_factory=list)
    is_exported:  bool          = True

    model_config = {"use_enum_values": True}

    def __repr__(self) -> str:
        return f"<IRNode {self.kind}:{self.name} @ {self.file_path}:{self.start_line}:{self.start_col}>"



class CallEdge(BaseModel):
    """
    Spec: CallEdge { caller_function, callee_function, file_id, line_number }
    """
    caller_id:      str
    callee_name:    str
    callee_id:      Optional[str] = None
    file_path:      str = ""
    line_number:    int = 0
    col_number:     int = 0
    is_method_call: bool = False


class ImportEdge(BaseModel):
    """
    Spec: ImportEdge { source_file, target_module }
    """
    source_file:   str
    target_module: str
    alias:         Optional[str] = None
    line_number:   int = 0
    is_default:    bool = False
    is_wildcard:   bool = False


class InheritanceEdge(BaseModel):
    """
    Spec: InheritanceEdge { child_class, parent_class }
    """
    child_id:    str
    parent_name: str
    parent_id:   Optional[str] = None
    kind:        str = "inherits"  

class ReferenceEdge(BaseModel):
    """
    Spec: ReferenceEdge { source_node, target_node }
    """
    source_id:   str
    target_name: str
    target_id:   Optional[str] = None
    line_number: int = 0



class ParseResult(BaseModel):
    file_path: str
    language:  str
    nodes:     list[IRNode]          = Field(default_factory=list)
    errors:    list[str]             = Field(default_factory=list)
    success:   bool                  = True

    call_edges:        list[CallEdge]        = Field(default_factory=list)
    import_edges:      list[ImportEdge]      = Field(default_factory=list)
    inheritance_edges: list[InheritanceEdge] = Field(default_factory=list)
    reference_edges:   list[ReferenceEdge]   = Field(default_factory=list)

    @property
    def functions(self) -> list[IRNode]:
        return [n for n in self.nodes if n.kind in (
            NodeKind.FUNCTION, NodeKind.METHOD,
            NodeKind.CONSTRUCTOR, NodeKind.LAMBDA,
        )]

    @property
    def classes(self) -> list[IRNode]:
        return [n for n in self.nodes if n.kind in (
            NodeKind.CLASS, NodeKind.INTERFACE,
            NodeKind.STRUCT, NodeKind.ENUM,
        )]

    @property
    def imports(self) -> list[IRNode]:
        return [n for n in self.nodes if n.kind in (
            NodeKind.IMPORT, NodeKind.REQUIRE, NodeKind.INCLUDE,
        )]

    def __repr__(self) -> str:
        return (
            f"<ParseResult {self.file_path} "
            f"nodes={len(self.nodes)} errors={len(self.errors)}>"
        )


class ParsingReport(BaseModel):
    repo_id:   str
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    results:   list[ParseResult] = Field(default_factory=list)

    @computed_field 
    @property
    def all_nodes(self) -> list[IRNode]:
        nodes = []
        for r in self.results:
            nodes.extend(r.nodes)
        return nodes

    @computed_field  
    @property
    def all_call_edges(self) -> list[CallEdge]:
        edges = []
        for r in self.results:
            edges.extend(r.call_edges)
        return edges

    @computed_field  
    @property
    def all_import_edges(self) -> list[ImportEdge]:
        edges = []
        for r in self.results:
            edges.extend(r.import_edges)
        return edges

    @computed_field 
    @property
    def all_inheritance_edges(self) -> list[InheritanceEdge]:
        edges = []
        for r in self.results:
            edges.extend(r.inheritance_edges)
        return edges

    @computed_field 
    @property
    def all_reference_edges(self) -> list[ReferenceEdge]:
        edges = []
        for r in self.results:
            edges.extend(r.reference_edges)
        return edges

    @computed_field  
    @property
    def failed_files(self) -> list[str]:
        return [r.file_path for r in self.results if not r.success]

    @computed_field  
    @property
    def total_nodes(self) -> int:
        return sum(len(r.nodes) for r in self.results)

    def summary(self) -> str:
        lines = [
            f"Repo         : {self.repo_id}",
            f"Files parsed : {len(self.results)}",
            f"Total nodes  : {self.total_nodes}",
            f"Call edges   : {len(self.all_call_edges)}",
            f"Import edges : {len(self.all_import_edges)}",
            f"Inherit edges: {len(self.all_inheritance_edges)}",
            f"Failed files : {len(self.failed_files)}",
        ]
        if self.failed_files:
            for fp in self.failed_files[:5]:
                lines.append(f"  ✗ {fp}")
        return "\n".join(lines)


class EdgeKind(str, Enum):
    CONTAINS   = "contains"
    CALLS      = "calls"
    IMPORTS    = "imports"
    INHERITS   = "inherits"
    IMPLEMENTS = "implements"
    DEFINES    = "defines"
    REFERENCES = "references"


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    kind: EdgeKind
    weight: float = 1.0
    metadata: dict = Field(default_factory=dict)
    model_config = {"use_enum_values": True}

    def __repr__(self) -> str:
        return f"<Edge {self.kind}: {self.source_id[:30]} → {self.target_id[:30]}>"


class GraphStats(BaseModel):
    repo_id:      str
    built_at:     datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    node_count:   int = 0
    edge_count:   int = 0
    orphan_count: int = 0
    nodes_by_kind: dict[str, int] = Field(default_factory=dict)
    edges_by_kind: dict[str, int] = Field(default_factory=dict)
    most_called:   list[tuple[str, int]] = Field(default_factory=list)
    most_complex:  list[tuple[str, int]] = Field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Repo         : {self.repo_id}",
            f"Nodes        : {self.node_count}",
            f"Edges        : {self.edge_count}",
            f"Orphans      : {self.orphan_count}",
            f"Nodes/kind   : {self.nodes_by_kind}",
            f"Edges/kind   : {self.edges_by_kind}",
        ]
        if self.most_called:
            top = ", ".join(f"{n}({c})" for n, c in self.most_called[:5])
            lines.append(f"Most called  : {top}")
        if self.most_complex:
            top = ", ".join(f"{n}({c})" for n, c in self.most_complex[:5])
            lines.append(f"Most complex : {top}")
        return "\n".join(lines)


