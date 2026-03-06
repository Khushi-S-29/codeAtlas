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
    """The type of code entity this IR node represents."""
    MODULE    = "module"    
    CLASS     = "class"
    FUNCTION  = "function"  
    METHOD    = "method"     
    VARIABLE  = "variable"   
    IMPORT    = "import" 


class IRNode(BaseModel):
    id: str
    name: str
    kind: NodeKind
    file_path: str
    start_line: int
    end_line: int
    language: str
    parent_class: Optional[str] = None
    parameters: list[str] = Field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    signature: Optional[str] = None
    calls: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    bases: list[str] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)
    is_exported: bool = True
    model_config = {"use_enum_values": True}

    def __repr__(self) -> str:
        return f"<IRNode {self.kind}:{self.name} @ {self.file_path}:{self.start_line}>"


class ParseResult(BaseModel):
    file_path: str
    language: str
    nodes: list[IRNode] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    success: bool = True

    @property
    def functions(self) -> list[IRNode]:
        return [n for n in self.nodes if n.kind in (NodeKind.FUNCTION, NodeKind.METHOD)]

    @property
    def classes(self) -> list[IRNode]:
        return [n for n in self.nodes if n.kind == NodeKind.CLASS]

    @property
    def imports(self) -> list[IRNode]:
        return [n for n in self.nodes if n.kind == NodeKind.IMPORT]

    def __repr__(self) -> str:
        return (
            f"<ParseResult {self.file_path} "
            f"nodes={len(self.nodes)} errors={len(self.errors)}>"
        )


class ParsingReport(BaseModel):
    """
    Aggregate output of Phase 2 — all ParseResults for a repo's change set.
    This is the input contract for Phase 3 (Graph Building).
    """
    repo_id: str
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    results: list[ParseResult] = Field(default_factory=list)

    @computed_field 
    @property
    def all_nodes(self) -> list[IRNode]:
        nodes = []
        for r in self.results:
            nodes.extend(r.nodes)
        return nodes

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
            f"Repo        : {self.repo_id}",
            f"Files parsed: {len(self.results)}",
            f"Total nodes : {self.total_nodes}",
            f"Failed files: {len(self.failed_files)}",
        ]
        if self.failed_files:
            for fp in self.failed_files[:5]:
                lines.append(f"  ✗ {fp}")
        return "\n".join(lines)



