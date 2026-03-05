"""
core/models.py
--------------
Pydantic models for the Phase 1 output: FileRecord and RepoManifest.
These are the canonical data shapes passed between pipeline phases.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, computed_field

class FileStatus(str, Enum):
    """How a file's state compares to the last indexed snapshot."""
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
        """Files that need (re-)parsing: new or modified only."""
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


