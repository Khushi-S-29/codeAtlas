from __future__ import annotations

from code_atlas.parsing.visitors.base import BaseVisitor
from code_atlas.parsing.visitors.python_visitor import PythonVisitor
from code_atlas.parsing.visitors.javascript_visitor import JavaScriptVisitor
from code_atlas.parsing.visitors.go_visitor import GoVisitor
from code_atlas.parsing.visitors.generic_visitor import GenericVisitor

_REGISTRY: dict[str, BaseVisitor] = {
    "python":     PythonVisitor(),
    "javascript": JavaScriptVisitor(),
    "typescript": JavaScriptVisitor(),
    "jsx":        JavaScriptVisitor(),
    "tsx":        JavaScriptVisitor(),
    "go":         GoVisitor(),
}

_GENERIC = GenericVisitor()

def get_visitor(language: str) -> BaseVisitor:
    return _REGISTRY.get(language, _GENERIC)

def registered_languages() -> list[str]:
    return sorted(_REGISTRY.keys())