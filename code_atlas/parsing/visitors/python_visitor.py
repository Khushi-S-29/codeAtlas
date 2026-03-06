from __future__ import annotations

import logging
from typing import Optional

import tree_sitter as ts

from code_atlas.core.models import IRNode, NodeKind, ParseResult
from code_atlas.parsing.visitors.base import BaseVisitor
from code_atlas.parsing.grammar_loader import get_parser

logger = logging.getLogger(__name__)

class PythonVisitor(BaseVisitor):
    language_name = "python"

    def parse(self, source_code: str, file_path: str, repo_id: str) -> ParseResult:
        result = ParseResult(file_path=file_path, language="python")
        parser = get_parser("python")

        if parser is None:
            result.success = False
            result.errors.append("tree-sitter-python grammar not available")
            return result

        source_bytes = source_code.encode("utf-8", errors="replace")

        try:
            tree = parser.parse(source_bytes)
        except Exception as exc:
            result.success = False
            result.errors.append(f"Parse error: {exc}")
            return result

        root = tree.root_node

        if root.has_error:
            result.errors.append("Syntax errors present — partial parse results may be incomplete")

        module_id = self.make_node_id(repo_id, file_path, "__module__", 1)
        module_imports: list[str] = []

        for node in root.children:
            if node.type in ("import_statement", "import_from_statement"):
                imp_str = self.node_text(node, source_bytes).strip()
                module_imports.append(imp_str)
                imp_id = self.make_node_id(repo_id, file_path, imp_str[:40], node.start_point[0] + 1)
                result.nodes.append(IRNode(
                    id=imp_id,
                    name=imp_str,
                    kind=NodeKind.IMPORT,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    language="python",
                    imports=[imp_str],
                ))

        module_node = IRNode(
            id=module_id,
            name=file_path,
            kind=NodeKind.MODULE,
            file_path=file_path,
            start_line=1,
            end_line=root.end_point[0] + 1,
            language="python",
            imports=module_imports,
        )
        result.nodes.append(module_node)

        self._walk_body(root, file_path, repo_id, source_bytes, result, parent_class=None)

        return result

    def _walk_body(
        self,
        body_node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        parent_class: Optional[str],
    ) -> None:
        for node in body_node.children:
            if node.type == "class_definition":
                self._handle_class(node, file_path, repo_id, source, result)
            elif node.type == "function_definition":
                kind = NodeKind.METHOD if parent_class else NodeKind.FUNCTION
                self._handle_function(node, file_path, repo_id, source, result, parent_class, kind)
            elif node.type == "decorated_definition":
                inner = self.find_first(node, "class_definition", "function_definition")
                if inner:
                    decorators = [
                        self.node_text(d, source).lstrip("@").strip()
                        for d in self.get_children_of_type(node, "decorator")
                    ]
                    if inner.type == "class_definition":
                        self._handle_class(inner, file_path, repo_id, source, result, decorators)
                    else:
                        kind = NodeKind.METHOD if parent_class else NodeKind.FUNCTION
                        self._handle_function(inner, file_path, repo_id, source, result, parent_class, kind, decorators)

    def _handle_class(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        decorators: list[str] | None = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = self.node_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line   = node.end_point[0] + 1

        bases: list[str] = []
        arg_list = node.child_by_field_name("superclasses")
        if arg_list:
            for arg in arg_list.children:
                if arg.type not in (",", "(", ")", "comment"):
                    bases.append(self.node_text(arg, source).strip())

        body = node.child_by_field_name("body")
        docstring = self.extract_docstring_from_body(body, source) if body else None

        node_id = self.make_node_id(repo_id, file_path, name, start_line)
        result.nodes.append(IRNode(
            id=node_id,
            name=name,
            kind=NodeKind.CLASS,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            language="python",
            bases=bases,
            docstring=docstring,
            signature=self.first_line(node, source),
            decorators=decorators or [],
            is_exported=not name.startswith("_"),
        ))

        if body:
            self._walk_body(body, file_path, repo_id, source, result, parent_class=name)

    def _handle_function(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        parent_class: Optional[str],
        kind: NodeKind,
        decorators: list[str] | None = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        name = self.node_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line   = node.end_point[0] + 1

        params: list[str] = []
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for p in params_node.children:
                if p.type in ("identifier",):
                    params.append(self.node_text(p, source))
                elif p.type in ("typed_parameter", "default_parameter", "typed_default_parameter"):
                    id_node = self.find_first(p, "identifier")
                    if id_node:
                        params.append(self.node_text(id_node, source))

        return_type: Optional[str] = None
        ret_node = node.child_by_field_name("return_type")
        if ret_node:
            return_type = self.node_text(ret_node, source).lstrip("->").strip()

        body = node.child_by_field_name("body")
        docstring = self.extract_docstring_from_body(body, source) if body else None

        calls: list[str] = []
        if body:
            for call_node in self.find_all(body, "call"):
                func_node = call_node.child_by_field_name("function")
                if func_node:
                    calls.append(self.node_text(func_node, source).strip())

        node_id = self.make_node_id(repo_id, file_path, f"{parent_class}.{name}" if parent_class else name, start_line)
        result.nodes.append(IRNode(
            id=node_id,
            name=name,
            kind=kind,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            language="python",
            parent_class=parent_class,
            parameters=params,
            return_type=return_type,
            docstring=docstring,
            signature=self.first_line(node, source),
            calls=list(dict.fromkeys(calls)), 
            decorators=decorators or [],
            is_exported=not name.startswith("_"),
        ))

        if body:
            self._walk_body(body, file_path, repo_id, source, result, parent_class=parent_class)