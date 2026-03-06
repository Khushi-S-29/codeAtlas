from __future__ import annotations

import logging
from typing import Optional

import tree_sitter as ts

from code_atlas.core.models import IRNode, NodeKind, ParseResult
from code_atlas.parsing.visitors.base import BaseVisitor
from code_atlas.parsing.grammar_loader import get_parser

logger = logging.getLogger(__name__)

_FUNCTION_TYPES = frozenset({
    "function_declaration",
    "function",                
    "arrow_function",
    "generator_function_declaration",
    "generator_function",
})

_CLASS_TYPES = frozenset({
    "class_declaration",
    "class",                    
})

_METHOD_TYPES = frozenset({
    "method_definition",
    "function",
    "arrow_function",
})

_VAR_DECL_TYPES = frozenset({"lexical_declaration", "variable_declaration"})


class JavaScriptVisitor(BaseVisitor):
    language_name = "javascript"

    def parse(self, source_code: str, file_path: str, repo_id: str) -> ParseResult:
        lang = self._resolve_lang(file_path)
        result = ParseResult(file_path=file_path, language=lang)
        parser = get_parser(lang)

        if parser is None:
            parser = get_parser("javascript")
        if parser is None:
            result.success = False
            result.errors.append(f"No tree-sitter grammar available for {lang}")
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
            result.errors.append("Syntax errors present — results may be incomplete")

        module_imports: list[str] = []
        for node in root.children:
            if node.type == "import_statement":
                module_imports.append(self.node_text(node, source_bytes).strip())

        module_id = self.make_node_id(repo_id, file_path, "__module__", 1)
        result.nodes.append(IRNode(
            id=module_id,
            name=file_path,
            kind=NodeKind.MODULE,
            file_path=file_path,
            start_line=1,
            end_line=root.end_point[0] + 1,
            language=lang,
            imports=module_imports,
        ))

        for node in root.children:
            if node.type == "import_statement":
                imp_str = self.node_text(node, source_bytes).strip()
                imp_id = self.make_node_id(repo_id, file_path, imp_str[:40], node.start_point[0] + 1)
                result.nodes.append(IRNode(
                    id=imp_id,
                    name=imp_str,
                    kind=NodeKind.IMPORT,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    language=lang,
                    imports=[imp_str],
                ))

        self._walk_statements(root.children, file_path, repo_id, source_bytes, result, parent_class=None)

        return result

    def _resolve_lang(self, file_path: str) -> str:
        """Pick the right grammar based on file extension."""
        ext = file_path.rsplit(".", 1)[-1].lower()
        if ext in ("ts",):
            return "typescript"
        if ext in ("tsx",):
            return "typescript"   
        return "javascript"

    def _walk_statements(
        self,
        nodes: list[ts.Node],
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        parent_class: Optional[str],
    ) -> None:
        for node in nodes:
            t = node.type

            if t in _CLASS_TYPES:
                self._handle_class(node, file_path, repo_id, source, result)

            elif t in _FUNCTION_TYPES:
                self._handle_function(node, file_path, repo_id, source, result,
                                      parent_class=parent_class, exported=False)

            elif t == "export_statement":
                self._handle_export(node, file_path, repo_id, source, result)

            elif t in _VAR_DECL_TYPES:
                self._handle_var_decl(node, file_path, repo_id, source, result, parent_class)

    def _handle_export(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
    ) -> None:
        for child in node.children:
            if child.type in _CLASS_TYPES:
                self._handle_class(child, file_path, repo_id, source, result, exported=True)
            elif child.type in _FUNCTION_TYPES:
                self._handle_function(child, file_path, repo_id, source, result,
                                      parent_class=None, exported=True)
            elif child.type in _VAR_DECL_TYPES:
                self._handle_var_decl(child, file_path, repo_id, source, result,
                                      parent_class=None, exported=True)

    def _handle_class(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        exported: bool = False,
    ) -> None:
        name_node = node.child_by_field_name("name")
        name = self.node_text(name_node, source) if name_node else "<anonymous>"
        start_line = node.start_point[0] + 1
        end_line   = node.end_point[0] + 1

        bases: list[str] = []
        heritage = self.find_first(node, "class_heritage")
        if heritage:
            for ident in self.find_all(heritage, "identifier", "member_expression"):
                bases.append(self.node_text(ident, source).strip())
                break  
        node_id = self.make_node_id(repo_id, file_path, name, start_line)
        result.nodes.append(IRNode(
            id=node_id,
            name=name,
            kind=NodeKind.CLASS,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            language=self._resolve_lang(file_path),
            bases=bases,
            signature=self.first_line(node, source),
            is_exported=exported,
        ))

        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "method_definition":
                    self._handle_method(child, file_path, repo_id, source, result, parent_class=name)

    def _handle_method(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        parent_class: str,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)
        start_line = node.start_point[0] + 1
        end_line   = node.end_point[0] + 1

        params = self._extract_params(node, source)
        return_type = self._extract_return_type(node, source)
        calls = self._extract_calls(node, source)

        node_id = self.make_node_id(repo_id, file_path, f"{parent_class}.{name}", start_line)
        result.nodes.append(IRNode(
            id=node_id,
            name=name,
            kind=NodeKind.METHOD,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            language=self._resolve_lang(file_path),
            parent_class=parent_class,
            parameters=params,
            return_type=return_type,
            signature=self.first_line(node, source),
            calls=calls,
            is_exported=False,
        ))

    def _handle_function(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        parent_class: Optional[str],
        exported: bool,
    ) -> None:
        name_node = node.child_by_field_name("name")
        name = self.node_text(name_node, source) if name_node else "<anonymous>"
        start_line = node.start_point[0] + 1
        end_line   = node.end_point[0] + 1

        params = self._extract_params(node, source)
        return_type = self._extract_return_type(node, source)
        calls = self._extract_calls(node, source)
        kind = NodeKind.METHOD if parent_class else NodeKind.FUNCTION

        node_id = self.make_node_id(repo_id, file_path,
                                    f"{parent_class}.{name}" if parent_class else name, start_line)
        result.nodes.append(IRNode(
            id=node_id,
            name=name,
            kind=kind,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            language=self._resolve_lang(file_path),
            parent_class=parent_class,
            parameters=params,
            return_type=return_type,
            signature=self.first_line(node, source),
            calls=calls,
            is_exported=exported,
        ))

    def _handle_var_decl(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        parent_class: Optional[str],
        exported: bool = False,
    ) -> None:
        """Handle `const foo = () => {}` and `const foo = function() {}`."""
        for declarator in self.find_all(node, "variable_declarator"):
            name_node = declarator.child_by_field_name("name")
            value_node = declarator.child_by_field_name("value")

            if name_node is None or value_node is None:
                continue
            if value_node.type not in _FUNCTION_TYPES:
                continue

            name = self.node_text(name_node, source)
            start_line = node.start_point[0] + 1
            end_line   = node.end_point[0] + 1
            params = self._extract_params(value_node, source)
            return_type = self._extract_return_type(value_node, source)
            calls = self._extract_calls(value_node, source)

            node_id = self.make_node_id(repo_id, file_path, name, start_line)
            result.nodes.append(IRNode(
                id=node_id,
                name=name,
                kind=NodeKind.FUNCTION,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                language=self._resolve_lang(file_path),
                parent_class=parent_class,
                parameters=params,
                return_type=return_type,
                signature=self.first_line(node, source),
                calls=calls,
                is_exported=exported,
            ))

    def _extract_params(self, node: ts.Node, source: bytes) -> list[str]:
        params: list[str] = []
        params_node = node.child_by_field_name("parameters") or \
                      node.child_by_field_name("parameter")
        if params_node is None:
            return params
        for child in params_node.children:
            if child.type in ("identifier", "required_parameter", "optional_parameter",
                              "rest_parameter", "assignment_pattern"):
                id_node = child if child.type == "identifier" else self.find_first(child, "identifier")
                if id_node:
                    params.append(self.node_text(id_node, source))
        return params

    def _extract_return_type(self, node: ts.Node, source: bytes) -> Optional[str]:
        """TypeScript only — return type annotation after `:`."""
        ret = node.child_by_field_name("return_type")
        if ret:
            return self.node_text(ret, source).lstrip(":").strip()
        return None

    def _extract_calls(self, node: ts.Node, source: bytes) -> list[str]:
        calls: list[str] = []
        body = node.child_by_field_name("body")
        if body is None:
            return calls
        for call_node in self.find_all(body, "call_expression"):
            func = call_node.child_by_field_name("function")
            if func:
                calls.append(self.node_text(func, source).strip())
        return list(dict.fromkeys(calls))