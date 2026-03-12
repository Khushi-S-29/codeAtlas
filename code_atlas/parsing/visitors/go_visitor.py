from __future__ import annotations

import logging
import re
from typing import Optional

import tree_sitter as ts

from code_atlas.core.models import (
    IRNode, NodeKind, Parameter, ParseResult,
    CallEdge, ImportEdge, InheritanceEdge,
)
from code_atlas.parsing.visitors.base import BaseVisitor
from code_atlas.parsing.grammar_loader import get_parser

logger = logging.getLogger(__name__)

_NOISY_GO = frozenset({
    "println", "print", "printf", "sprintf", "fprintf", "errorf", "scanf",
    "len", "cap", "append", "copy", "delete", "make", "new", "close",
    "panic", "recover",
    "string", "int", "int64", "int32", "float64", "bool", "byte", "rune",
    "error", "errors",
})


class GoVisitor(BaseVisitor):
    language_name = "go"

    def parse(self, source_code: str, file_path: str, repo_id: str) -> ParseResult:
        result = ParseResult(file_path=file_path, language="go")
        parser = get_parser("go")

        if parser is None:
            result.success = False
            result.errors.append("tree-sitter-go grammar not available")
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
            result.errors.append("Syntax errors — partial parse")

        module_id = self.make_node_id(repo_id, file_path, "__module__", 1)
        module_imports: list[str] = []

        package_name: Optional[str] = None
        for node in root.children:
            if node.type == "package_clause":
                pkg_id = self.find_first(node, "package_identifier")
                if pkg_id:
                    package_name = self.node_text(pkg_id, source_bytes)
                break

        for node in root.children:
            if node.type == "import_declaration":
                specs = self.find_all(node, "import_spec")
                if not specs:
                    path_node = self.find_first(node, "interpreted_string_literal",
                                                "raw_string_literal")
                    if path_node:
                        specs = [node]

                for spec in specs:
                    path_node = (spec.child_by_field_name("path")
                                 or self.find_first(spec, "interpreted_string_literal",
                                                    "raw_string_literal"))
                    if path_node is None:
                        continue
                    raw    = self.node_text(path_node, source_bytes).strip('"`')
                    alias_node = spec.child_by_field_name("name")
                    alias  = self.node_text(alias_node, source_bytes) if alias_node else None
                    if alias in (".", "_"):
                        alias = None

                    imp_str = self.node_text(spec, source_bytes).strip()
                    module_imports.append(imp_str)

                    stem = raw.split("/")[-1]
                    result.import_edges.append(ImportEdge(
                        source_file=file_path,
                        target_module=stem,
                        alias=alias,
                        line_number=node.start_point[0] + 1,
                    ))

        result.nodes.append(IRNode(
            id=module_id, name=file_path, kind=NodeKind.MODULE,
            file_path=file_path, start_line=1, end_line=root.end_point[0] + 1,
            start_col=0, end_col=0, language="go", imports=module_imports,
        ))
        type_index: dict[str, str] = {}  
        for node in root.children:
            t = node.type
            if t == "type_declaration":
                self._handle_type_decl(node, file_path, repo_id, source_bytes, result,
                                       module_id, type_index)
            elif t == "function_declaration":
                self._handle_func(node, file_path, repo_id, source_bytes, result,
                                  module_id, package_name, type_index)
            elif t == "method_declaration":
                self._handle_method(node, file_path, repo_id, source_bytes, result,
                                    module_id, package_name, type_index)
            elif t in ("var_declaration", "const_declaration"):
                self._handle_var(node, file_path, repo_id, source_bytes, result,
                                 module_id)

        _link_children(result.nodes)
        return result

    def _handle_type_decl(self, node, file_path, repo_id, source, result,
                          module_id, type_index) -> None:
        for spec in self.find_all(node, "type_spec"):
            name_node = spec.child_by_field_name("name")
            type_node = spec.child_by_field_name("type")
            if name_node is None or type_node is None:
                continue
            name = self.node_text(name_node, source)
            ttype = type_node.type

            if ttype == "struct_type":
                kind = NodeKind.STRUCT
            elif ttype == "interface_type":
                kind = NodeKind.INTERFACE
            else:
                node_id = self.make_node_id(repo_id, file_path, name,
                                            spec.start_point[0] + 1)
                result.nodes.append(IRNode(
                    id=node_id, name=name, kind=NodeKind.TYPE_ANNOTATION,
                    file_path=file_path,
                    start_line=spec.start_point[0] + 1, end_line=spec.end_point[0] + 1,
                    start_col=spec.start_point[1], end_col=spec.end_point[1],
                    language="go", parent_id=module_id,
                    value=self.node_text(type_node, source).strip(),
                    signature=f"type {name} = {self.node_text(type_node, source).strip()}",
                ))
                type_index[name] = node_id
                continue

            node_id = self.make_node_id(repo_id, file_path, name,
                                        spec.start_point[0] + 1)
            type_index[name] = node_id

            interface_methods: list[str] = []
            if kind == NodeKind.INTERFACE:
                for method_elem in self.find_all(type_node, "method_elem",
                                                 "method_spec"):
                    mname_node = method_elem.child_by_field_name("name")
                    if mname_node:
                        interface_methods.append(
                            self.node_text(mname_node, source).strip()
                        )
                        self._emit_interface_method(
                            method_elem, file_path, repo_id, source, result,
                            parent_class=name, parent_id=node_id,
                        )

            result.nodes.append(IRNode(
                id=node_id, name=name, kind=kind,
                file_path=file_path,
                start_line=spec.start_point[0] + 1, end_line=spec.end_point[0] + 1,
                start_col=spec.start_point[1], end_col=spec.end_point[1],
                language="go", parent_id=module_id,
                signature=f"type {name} {ttype.replace('_type', '')}",
                is_exported=name[0].isupper() if name else False,
            ))

    def _emit_interface_method(self, node, file_path, repo_id, source, result,
                               parent_class, parent_id) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name     = self.node_text(name_node, source)
        params   = self._extract_go_params(node, source)
        ret_type = self._extract_go_return(node, source)
        node_id  = self.make_node_id(repo_id, file_path,
                                      f"{parent_class}.{name}",
                                      node.start_point[0] + 1)
        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.METHOD,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language="go", parent_id=parent_id, parent_class=parent_class,
            typed_parameters=params, parameters=[p.name for p in params],
            return_type=ret_type,
            signature=f"{name}({', '.join(str(p) for p in params)}){' ' + ret_type if ret_type else ''}",
            is_exported=name[0].isupper() if name else False,
        ))

    def _handle_func(self, node, file_path, repo_id, source, result,
                     module_id, package_name, type_index) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)

        params   = self._extract_go_params(node, source)
        ret_type = self._extract_go_return(node, source)

        is_ctor = name.startswith("New") or name.startswith("new")
        kind    = NodeKind.CONSTRUCTOR if is_ctor else NodeKind.FUNCTION

        node_id = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
        calls   = self._extract_go_calls(node, source)

        result.nodes.append(IRNode(
            id=node_id, name=name, kind=kind,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language="go", parent_id=module_id,
            typed_parameters=params, parameters=[p.name for p in params],
            return_type=ret_type, calls=calls,
            signature=f"func {name}({', '.join(str(p) for p in params)}){' ' + ret_type if ret_type else ''}",
            is_exported=name[0].isupper() if name else False,
        ))
        self._emit_go_call_edges(node, node_id, file_path, source, result)

    def _handle_method(self, node, file_path, repo_id, source, result,
                       module_id, package_name, type_index) -> None:
        name_node     = node.child_by_field_name("name")
        receiver_node = node.child_by_field_name("receiver")
        if name_node is None:
            return

        name = self.node_text(name_node, source)

        receiver_type: Optional[str] = None
        if receiver_node:
            for param in self.find_all(receiver_node, "parameter_declaration"):
                typ = param.child_by_field_name("type")
                if typ:
                    raw = self.node_text(typ, source).strip().lstrip("*")
                    receiver_type = raw.split("[")[0].strip()
                    break

        parent_class = receiver_type
        parent_id    = (type_index.get(receiver_type, module_id)
                        if receiver_type else module_id)

        params   = self._extract_go_params(node, source)
        ret_type = self._extract_go_return(node, source)
        calls    = self._extract_go_calls(node, source)
        qual     = f"{parent_class}.{name}" if parent_class else name
        node_id  = self.make_node_id(repo_id, file_path, qual,
                                      node.start_point[0] + 1)

        recv_str = f"({self.node_text(receiver_node, source).strip()}) " if receiver_node else ""
        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.METHOD,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language="go", parent_id=parent_id, parent_class=parent_class,
            typed_parameters=params, parameters=[p.name for p in params],
            return_type=ret_type, calls=calls,
            signature=f"func {recv_str}{name}({', '.join(str(p) for p in params)}){' ' + ret_type if ret_type else ''}",
            is_exported=name[0].isupper() if name else False,
        ))
        self._emit_go_call_edges(node, node_id, file_path, source, result)

    def _handle_var(self, node, file_path, repo_id, source, result, module_id) -> None:
        for spec in self.find_all(node, "var_spec", "const_spec"):
            name_node = spec.child_by_field_name("name")
            if name_node is None:
                name_node = self.find_first(spec, "identifier")
            if name_node is None:
                continue
            name  = self.node_text(name_node, source)
            value_node = spec.child_by_field_name("value")
            value = (self.node_text(value_node, source).strip()
                     if value_node else None)
            node_id = self.make_node_id(repo_id, file_path, f"var:{name}",
                                        spec.start_point[0] + 1)
            result.nodes.append(IRNode(
                id=node_id, name=name, kind=NodeKind.ASSIGNMENT,
                file_path=file_path,
                start_line=spec.start_point[0] + 1, end_line=spec.end_point[0] + 1,
                start_col=spec.start_point[1], end_col=spec.end_point[1],
                language="go", parent_id=module_id, value=value,
                signature=self.first_line(spec, source),
            ))

    def _extract_go_params(self, node, source: bytes) -> list[Parameter]:
        params: list[Parameter] = []
        params_node = node.child_by_field_name("parameters")
        if params_node is None:
            return params
        for child in params_node.children:
            if child.type == "parameter_declaration":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                if name_node:
                    typ = self.node_text(type_node, source).strip() if type_node else None
                    params.append(Parameter(
                        name=self.node_text(name_node, source).strip(),
                        type=typ,
                    ))
                elif type_node:
                    params.append(Parameter(
                        name="_",
                        type=self.node_text(type_node, source).strip(),
                    ))
            elif child.type == "variadic_parameter_declaration":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                name = self.node_text(name_node, source).strip() if name_node else "..."
                typ  = ("..." + self.node_text(type_node, source).strip()
                        if type_node else "...any")
                params.append(Parameter(name=name, type=typ))
        return params

    def _extract_go_return(self, node, source: bytes) -> Optional[str]:
        result_node = node.child_by_field_name("result")
        if result_node:
            return self.node_text(result_node, source).strip()
        return None

    def _extract_go_calls(self, node, source: bytes) -> list[str]:
        calls: list[str] = []
        body = node.child_by_field_name("body")
        if body is None:
            return calls
        for call in self.find_all(body, "call_expression"):
            func = call.child_by_field_name("function")
            if func is None:
                continue
            raw  = self.node_text(func, source).strip()
            leaf = raw.split(".")[-1].strip()
            if leaf and leaf.lower() not in _NOISY_GO:
                calls.append(raw)
        return list(dict.fromkeys(calls))

    def _emit_go_call_edges(self, node, caller_id, file_path, source, result) -> None:
        body = node.child_by_field_name("body")
        if body is None:
            return
        for call in self.find_all(body, "call_expression"):
            func = call.child_by_field_name("function")
            if func is None:
                continue
            raw  = self.node_text(func, source).strip()
            leaf = raw.split(".")[-1].strip()
            if leaf and leaf.lower() not in _NOISY_GO:
                result.call_edges.append(CallEdge(
                    caller_id=caller_id, callee_name=raw,
                    file_path=file_path,
                    line_number=call.start_point[0] + 1,
                    col_number=call.start_point[1],
                    is_method_call="." in raw,
                ))


def _link_children(nodes: list[IRNode]) -> None:
    id_map = {n.id: n for n in nodes}
    for node in nodes:
        if node.parent_id and node.parent_id in id_map:
            parent = id_map[node.parent_id]
            if node.id not in parent.children:
                parent.children.append(node.id)