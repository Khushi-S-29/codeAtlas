from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field


DATA_DIR = Path(os.getenv("CODE_ATLAS_DATA_DIR", Path.home() / ".code_atlas"))

REPOS_DIR    = DATA_DIR / "repos"       
MANIFESTS_DIR = DATA_DIR / "manifests" 
GRAPHS_DIR   = DATA_DIR / "graphs"     
INDEXES_DIR  = DATA_DIR / "indexes"     

for _dir in (REPOS_DIR, MANIFESTS_DIR, GRAPHS_DIR, INDEXES_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


@dataclass
class IngestionConfig:
    excluded_dirs: frozenset[str] = field(default_factory=lambda: frozenset({
        "node_modules", ".git", "__pycache__", ".mypy_cache", ".pytest_cache",
        "build", "dist", "out", "target", ".gradle", ".idea", ".vscode",
        "vendor", "third_party", "venv", ".venv", "env", ".env",
        "coverage", ".nyc_output", "htmlcov",
    }))

    source_extensions: frozenset[str] = field(default_factory=lambda: frozenset({
        # Python
        ".py", ".pyi",
        # JavaScript / TypeScript
        ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        # Java / JVM
        ".java", ".kt", ".scala", ".groovy",
        # Systems
        ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".rs", ".go",
        # Web
        ".html", ".css", ".scss", ".vue", ".svelte",
        # Config / data (parsed for deps)
        ".toml", ".yaml", ".yml", ".json",
        # Ruby / PHP / others
        ".rb", ".php", ".cs", ".swift",
        # Shell
        ".sh", ".bash", ".zsh",
    }))

    max_file_size_bytes: int =2 * 1024 * 1024

    clone_depth: int | None = 1

    hash_workers: int = 8


EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",   ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",   ".kts": "kotlin",
    ".scala": "scala",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",         ".h": "c",
    ".cpp": "cpp",     ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".vue": "vue",
    ".svelte": "svelte",
    ".html": "html",   ".htm": "html",
    ".css": "css",     ".scss": "scss",
    ".sh": "shell",    ".bash": "shell", ".zsh": "shell",
    ".toml": "toml",
    ".yaml": "yaml",   ".yml": "yaml",
    ".json": "json",
    ".groovy": "groovy",
}

SHEBANG_TO_LANGUAGE: dict[str, str] = {
    "python":  "python",
    "python3": "python",
    "node":    "javascript",
    "ruby":    "ruby",
    "bash":    "shell",
    "sh":      "shell",
    "zsh":     "shell",
    "perl":    "perl",
    "php":     "php",
}


DEFAULT_INGESTION_CONFIG = IngestionConfig()







# This file defines:

# Where data will be stored

# What files should be ignored

# What file types are considered source code

# Limits for ingestion

# Language detection rules

# It acts like a central configuration for the ingestion pipeline