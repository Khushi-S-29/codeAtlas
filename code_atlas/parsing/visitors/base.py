from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Optional

import tree_sitter as ts

from code_atlas.core.models import IRNode, NodeKind, ParseResult

logger = logging.getLogger(__name__)


class BaseVisitor(ABC):
    """
    Abstract base for all tree-sitter language visitors.
    Subclasses only need to implement `parse()`.
    """

    language_name: str = "unknown"

    @abstractmethod
    def parse(self, source_code: str, file_path: str, repo_id: str) -> ParseResult:
        """
        Parse *source_code* (the full text of one file) and return a
        ParseResult containing all extracted IRNode objects.
        """

    def make_node_id(self, repo_id: str, file_path: str, name: str, start_line: int) -> str:
        raw = f"{repo_id}:{file_path}:{name}:{start_line}"
        return raw[:128]

    @staticmethod
    def node_text(node: ts.Node, source: bytes) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def first_line(node: ts.Node, source: bytes) -> str:
        text = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        return text.split("\n", 1)[0].strip()

    @staticmethod
    def get_children_of_type(node: ts.Node, *type_names: str) -> list[ts.Node]:
        return [c for c in node.children if c.type in type_names]

    @staticmethod
    def find_all(node: ts.Node, *type_names: str) -> list[ts.Node]:
        results: list[ts.Node] = []
        stack = list(node.children)
        while stack:
            current = stack.pop()
            if current.type in type_names:
                results.append(current)
            stack.extend(current.children)
        return results

    @staticmethod
    def find_first(node: ts.Node, *type_names: str) -> Optional[ts.Node]:
        stack = list(node.children)
        while stack:
            current = stack.pop()
            if current.type in type_names:
                return current
            stack.extend(current.children)
        return None


    @staticmethod
    def extract_docstring_from_body(body_node: ts.Node, source: bytes) -> Optional[str]:
        if body_node is None:
            return None
        for child in body_node.children:
            if child.type in ("expression_statement",):
                for sub in child.children:
                    if sub.type in ("string", "string_literal"):
                        raw = BaseVisitor.node_text(sub, source)
                        stripped = raw.strip("\"'").strip()
                        if stripped.startswith('"""') or stripped.startswith("'''"):
                            stripped = stripped[3:]
                        if stripped.endswith('"""') or stripped.endswith("'''"):
                            stripped = stripped[:-3]
                        return stripped.strip() or None
            break  
        return None