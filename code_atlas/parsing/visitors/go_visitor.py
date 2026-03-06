from __future__ import annotations

import logging
from typing import Optional

import tree_sitter as ts

from code_atlas.core.models import IRNode, NodeKind, ParseResult
from code_atlas.parsing.visitors.base import BaseVisitor
from code_atlas.parsing.grammar_loader import get_parser

logger = logging.getLogger(__name__)


class GoVisitor(BaseVisitor):
    language_name = "go"

    def parse(self, source_code: str, file_path: str, repo_id: str) -> ParseResult:
        result = ParseResult(file_path=file_path, language="go")
        parser = get_parser("go")
        if parser is None:
            return result

        source_bytes = source_code.encode("utf-8", errors="replace")
        tree = parser.parse(source_bytes)
        root = tree.root_node

        package_name: Optional[str] = None
        module_imports: list[str] = []

        for node in self.find_all(root, "package_clause"):
            name_node = self.find_first(node, "identifier")

            if name_node:
                package_name = self.node_text(name_node, source_bytes).strip()
                break

        if not package_name:
            stripped = source_code.strip().splitlines()
            if stripped and stripped[0].startswith("package "):
                package_name = stripped[0].split()[1].strip()

        if not package_name:
            package_name = "main"

        for node in self.find_all(root, "import_declaration"):
            for spec in self.find_all(node, "import_spec"):

                path_node = self.find_first(spec, "interpreted_string_literal")
                if not path_node:
                    path_node = self.find_first(spec, "raw_string_literal")

                if not path_node:
                    continue

                imp_path = self.node_text(path_node, source_bytes).strip()

                module_imports.append(imp_path)

                imp_id = self.make_node_id(
                    repo_id,
                    file_path,
                    imp_path[:40],
                    spec.start_point[0] + 1,
                )

                result.nodes.append(
                    IRNode(
                        id=imp_id,
                        name=imp_path,
                        kind=NodeKind.IMPORT,
                        file_path=file_path,
                        start_line=spec.start_point[0] + 1,
                        end_line=spec.end_point[0] + 1,
                        language="go",
                        imports=[imp_path],
                    )
                )

        for node in root.children:

            if node.type == "function_declaration":
                self._handle_function(node, file_path, repo_id, source_bytes, result)

            elif node.type == "method_declaration":
                self._handle_method(node, file_path, repo_id, source_bytes, result)

            elif node.type == "type_declaration":
                self._handle_type(node, file_path, repo_id, source_bytes, result)

        module_id = self.make_node_id(repo_id, file_path, "__module__", 1)

        result.nodes.append(
            IRNode(
                id=module_id,
                name=f"package {package_name}",
                kind=NodeKind.MODULE,
                file_path=file_path,
                start_line=1,
                end_line=root.end_point[0] + 1,
                language="go",
                imports=module_imports,
            )
        )

        return result

    def _handle_function(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
    ):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self.node_text(name_node, source)
        start_line = node.start_point[0] + 1

        params = self._extract_params(node.child_by_field_name("parameters"), source)
        calls = self._extract_calls(node.child_by_field_name("body"), source)

        node_id = self.make_node_id(repo_id, file_path, name, start_line)

        result.nodes.append(
            IRNode(
                id=node_id,
                name=name,
                kind=NodeKind.FUNCTION,
                file_path=file_path,
                start_line=start_line,
                end_line=node.end_point[0] + 1,
                language="go",
                parameters=params,
                signature=self.first_line(node, source),
                calls=calls,
                is_exported=name[0].isupper(),
            )
        )

    def _handle_method(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
    ):
        receiver_node = node.child_by_field_name("receiver")
        name_node = node.child_by_field_name("name")

        if not name_node or not receiver_node:
            return

        name = self.node_text(name_node, source)

        receiver_type = (
            self.node_text(receiver_node, source)
            .strip("() ")
            .split()[-1]
            .lstrip("*")
        )

        start_line = node.start_point[0] + 1

        node_id = self.make_node_id(
            repo_id,
            file_path,
            f"{receiver_type}.{name}",
            start_line,
        )

        result.nodes.append(
            IRNode(
                id=node_id,
                name=name,
                kind=NodeKind.METHOD,
                file_path=file_path,
                start_line=start_line,
                end_line=node.end_point[0] + 1,
                language="go",
                parent_class=receiver_type,
                parameters=self._extract_params(
                    node.child_by_field_name("parameters"), source
                ),
                signature=self.first_line(node, source),
                calls=self._extract_calls(node.child_by_field_name("body"), source),
                is_exported=name[0].isupper(),
            )
        )

    def _handle_type(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
    ):
        for spec in self.find_all(node, "type_spec"):

            name_node = spec.child_by_field_name("name")
            if not name_node:
                continue

            name = self.node_text(name_node, source)
            start_line = spec.start_point[0] + 1

            node_id = self.make_node_id(repo_id, file_path, name, start_line)

            result.nodes.append(
                IRNode(
                    id=node_id,
                    name=name,
                    kind=NodeKind.CLASS,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=spec.end_point[0] + 1,
                    language="go",
                    signature=self.first_line(spec, source),
                    is_exported=name[0].isupper(),
                )
            )

    def _extract_params(
        self,
        params_node: Optional[ts.Node],
        source: bytes,
    ) -> list[str]:

        if not params_node:
            return []

        params: list[str] = []

        for param in self.find_all(params_node, "parameter_declaration"):
            idents = self.get_children_of_type(param, "identifier")

            for ident in idents:
                params.append(self.node_text(ident, source))

        return params

    def _extract_calls(
        self,
        body_node: Optional[ts.Node],
        source: bytes,
    ) -> list[str]:

        if not body_node:
            return []

        calls: list[str] = []

        for call in self.find_all(body_node, "call_expression"):

            func = call.child_by_field_name("function")

            if func:
                calls.append(self.node_text(func, source).strip())

        return list(dict.fromkeys(calls))