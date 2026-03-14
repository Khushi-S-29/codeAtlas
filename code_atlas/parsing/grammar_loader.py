from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

_LANG_REGISTRY: dict[str, tuple[str, str]] = {
    "python":     ("tree_sitter_python",     "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx":        ("tree_sitter_typescript", "language_tsx"),
    "java":       ("tree_sitter_java",       "language"),
    "go":         ("tree_sitter_go",         "language"),
    "rust":       ("tree_sitter_rust",       "language"),
    "cpp":        ("tree_sitter_cpp",        "language"),
    "c":          ("tree_sitter_c",          "language"),
}

_LANG_ALIASES: dict[str, str] = {
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "kotlin": "java",  
}


@lru_cache(maxsize=None)
def get_language(lang_name: str):
    try:
        import tree_sitter as ts
    except ImportError:
        logger.error("tree-sitter is not installed. Run: pip install tree-sitter")
        return None

    resolved = _LANG_ALIASES.get(lang_name, lang_name)

    if resolved not in _LANG_REGISTRY:
        logger.debug("No grammar registered for language: %s", lang_name)
        return None

    module_name, attr = _LANG_REGISTRY[resolved]

    try:
        import importlib
        mod = importlib.import_module(module_name)
        lang_fn = getattr(mod, attr)
        language = ts.Language(lang_fn()) if callable(lang_fn) else ts.Language(lang_fn)
        logger.debug("Loaded grammar for %s from %s", lang_name, module_name)
        return language
    except ImportError:
        logger.debug(
            "Grammar package '%s' not installed — %s files will be skipped.",
            module_name, lang_name,
        )
        return None
    except Exception as exc:
        logger.warning("Failed to load grammar for %s: %s", lang_name, exc)
        return None


def get_parser(lang_name: str):
    try:
        import tree_sitter as ts
    except ImportError:
        return None

    language = get_language(lang_name)
    if language is None:
        return None

    try:
        parser = ts.Parser(language)
        return parser
    except Exception as exc:
        logger.warning("Could not create parser for %s: %s", lang_name, exc)
        return None


def supported_languages() -> list[str]:
    available = []
    for name in list(_LANG_REGISTRY.keys()) + list(_LANG_ALIASES.keys()):
        if get_language(name) is not None:
            available.append(name)
    return sorted(set(available))









'''

# Purpose

# Loads Tree-sitter language grammars dynamically.

# Tree-sitter is the AST parser used by CodeAtlas.
python code → python AST
js code → javascript AST
'''