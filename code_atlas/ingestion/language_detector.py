from __future__ import annotations

import logging
from pathlib import Path

from code_atlas.core.config import EXTENSION_TO_LANGUAGE, SHEBANG_TO_LANGUAGE

logger = logging.getLogger(__name__)

def detect_language(file_path: Path) -> str | None:
    ext = file_path.suffix.lower()
    if ext in EXTENSION_TO_LANGUAGE:
        return EXTENSION_TO_LANGUAGE[ext]

    lang = _detect_via_shebang(file_path)
    if lang:
        return lang

    lang = _detect_by_filename(file_path.name)
    if lang:
        return lang

    return None 

def _detect_via_shebang(file_path: Path) -> str | None:
    try:
        with file_path.open("rb") as fh:
            first_bytes = fh.read(128)

        if b"\x00" in first_bytes:
            return None

        first_line = first_bytes.split(b"\n", 1)[0].decode("utf-8", errors="ignore").strip()
        if not first_line.startswith("#!"):
            return None

        parts = first_line[2:].strip().split()
        if not parts:
            return None

        interpreter = parts[-1]  
        interpreter = Path(interpreter).name  

        for key, lang in SHEBANG_TO_LANGUAGE.items():
            if interpreter.startswith(key):
                return lang

    except (OSError, UnicodeDecodeError):
        pass

    return None

def _detect_by_filename(name: str) -> str | None:
    _FILENAME_MAP: dict[str, str] = {
        "Makefile":   "makefile",
        "makefile":   "makefile",
        "GNUmakefile":"makefile",
        "Dockerfile": "dockerfile",
        "Jenkinsfile":"groovy",
        "Vagrantfile":"ruby",
        "Rakefile":   "ruby",
        "Gemfile":    "ruby",
        "Podfile":    "ruby",
        ".bashrc":    "shell",
        ".zshrc":     "shell",
        ".profile":   "shell",
    }
    return _FILENAME_MAP.get(name)

def is_binary_file(file_path: Path, sample_bytes: int = 8192) -> bool:
    try:
        with file_path.open("rb") as fh:
            chunk = fh.read(sample_bytes)
        return b"\x00" in chunk
    except OSError:
        return True  




# Purpose

# Identify the programming language of each file.

# Needed because parsers are language-specific.