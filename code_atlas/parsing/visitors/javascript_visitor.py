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

_FUNCTION_TYPES = frozenset({
    "function_declaration", "function",
    "generator_function_declaration", "generator_function",
})
_ARROW_TYPES    = frozenset({"arrow_function"})
_CLASS_TYPES    = frozenset({"class_declaration", "class"})
_VAR_DECL_TYPES = frozenset({"lexical_declaration", "variable_declaration"})

_NOISY_CALLEES = frozenset({
    "push", "pop", "shift", "unshift", "splice", "slice", "map", "filter",
    "reduce", "forEach", "find", "findIndex", "some", "every", "includes",
    "indexOf", "join", "split", "replace", "trim", "toLowerCase", "toUpperCase",
    "toString", "valueOf", "hasOwnProperty", "keys", "values", "entries",
    "assign", "freeze", "create", "then", "catch", "finally", "resolve", "reject",
    "json", "text", "blob", "arrayBuffer", "formData", "clone",
    "addEventListener", "removeEventListener", "dispatchEvent",
    "setAttribute", "getAttribute", "removeAttribute", "appendChild",
    "querySelector", "querySelectorAll", "getElementById", "getElementsByClassName",
    "preventDefault", "stopPropagation",
    "toFixed", "toLocaleString", "toLocaleDateString",
    "delete", "get", "set", "has", "clear", "size",
    "start", "end", "test", "exec", "match", "search",
    "round", "floor", "ceil", "abs", "max", "min", "random", "sqrt", "pow",
    "now", "parse", "stringify",
    "send", "status", "json", "end", "redirect",
    "emit", "on", "off", "once", "removeListener",
    "setTimeout", "setInterval", "clearTimeout", "clearInterval",
    "requestAnimationFrame", "cancelAnimationFrame",
    "scrollTo", "scrollIntoView", "focus", "blur", "click",
    "entries", "fromEntries", "flat", "flatMap", "fill", "copyWithin",
    "sort", "reverse", "concat",
})


class JavaScriptVisitor(BaseVisitor):
    language_name = "javascript"

    def parse(self, source_code: str, file_path: str, repo_id: str) -> ParseResult:
        lang   = self._resolve_lang(file_path)
        result = ParseResult(file_path=file_path, language=lang)
        parser = get_parser(lang) or get_parser("javascript")

        if parser is None:
            result.success = False
            result.errors.append(f"No tree-sitter grammar for {lang}")
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

        module_id      = self.make_node_id(repo_id, file_path, "__module__", 1)
        module_imports: list[str] = []

        for node in root.children:
            if node.type == "import_statement":
                module_imports.append(self.node_text(node, source_bytes).strip())
            elif node.type in _VAR_DECL_TYPES:
                module_imports.extend(self._extract_require_strings(node, source_bytes))

        result.nodes.append(IRNode(
            id=module_id,
            name=file_path,
            kind=NodeKind.MODULE,
            file_path=file_path,
            start_line=1,
            end_line=root.end_point[0] + 1,
            start_col=0,
            end_col=0,
            language=lang,
            imports=module_imports,
        ))

        for node in root.children:
            if node.type == "import_statement":
                imp_str = self.node_text(node, source_bytes).strip()
                imp_id  = self.make_node_id(repo_id, file_path, imp_str[:40], node.start_point[0] + 1)
                result.nodes.append(IRNode(
                    id=imp_id, name=imp_str, kind=NodeKind.IMPORT,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    language=lang, parent_id=module_id, imports=[imp_str],
                ))
                target = _parse_es_import_target(imp_str)
                if target:
                    result.import_edges.append(ImportEdge(
                        source_file=file_path,
                        target_module=target,
                        line_number=node.start_point[0] + 1,
                    ))

        for node in root.children:
            if node.type in _VAR_DECL_TYPES:
                self._emit_require_nodes(node, file_path, repo_id, source_bytes,
                                         result, module_id, lang)

        for node in root.children:
            if node.type == "expression_statement":
                expr = self.find_first(node, "call_expression")
                if expr and self._is_chained_require(expr, source_bytes):
                    raw    = self.node_text(expr, source_bytes).strip()
                    target = self._chained_require_target(expr, source_bytes)
                    imp_id = self.make_node_id(repo_id, file_path, raw[:40],
                                               node.start_point[0] + 1)
                    result.nodes.append(IRNode(
                        id=imp_id, name=raw, kind=NodeKind.REQUIRE,
                        file_path=file_path,
                        start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                        start_col=node.start_point[1], end_col=node.end_point[1],
                        language=lang, parent_id=module_id, imports=[raw],
                    ))
                    if target:
                        result.import_edges.append(ImportEdge(
                            source_file=file_path, target_module=target,
                            line_number=node.start_point[0] + 1,
                        ))

        for node in root.children:
            if node.type == "interface_declaration":
                self._handle_interface(node, file_path, repo_id, source_bytes, result, module_id)
            elif node.type == "enum_declaration":
                self._handle_enum(node, file_path, repo_id, source_bytes, result, module_id)
        self._walk_statements(root.children, file_path, repo_id, source_bytes, result,
                              parent_class=None, parent_id=module_id)

        _link_children(result.nodes)
        return result


    def _walk_statements(
        self, nodes, file_path, repo_id, source, result,
        parent_class, parent_id,
    ) -> None:
        for node in nodes:
            t = node.type
            if t in _CLASS_TYPES:
                self._handle_class(node, file_path, repo_id, source, result,
                                   parent_id=parent_id)
            elif t in _FUNCTION_TYPES:
                self._handle_function(node, file_path, repo_id, source, result,
                                      parent_class=parent_class, parent_id=parent_id)
            elif t == "export_statement":
                self._handle_export(node, file_path, repo_id, source, result,
                                    parent_id=parent_id)
            elif t in _VAR_DECL_TYPES:
                self._handle_var_decl(node, file_path, repo_id, source, result,
                                      parent_class=parent_class, parent_id=parent_id)
            elif t == "expression_statement":
                self._handle_expr_statement(node, file_path, repo_id, source, result,
                                            parent_id=parent_id)
            elif t == "interface_declaration":
                self._handle_interface(node, file_path, repo_id, source, result, parent_id)
            elif t == "enum_declaration":
                self._handle_enum(node, file_path, repo_id, source, result, parent_id)


    def _handle_class(self, node, file_path, repo_id, source, result,
                      parent_id=None, exported=False) -> None:
        lang = self._resolve_lang(file_path)
        name_node = node.child_by_field_name("name")
        name = self.node_text(name_node, source) if name_node else "<anonymous>"

        bases: list[str] = []
        heritage = self.find_first(node, "class_heritage")
        if heritage:
            for ident in self.find_all(heritage, "identifier", "member_expression"):
                bases.append(self.node_text(ident, source).strip())
                break

        node_id = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.CLASS,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language=lang, parent_id=parent_id,
            bases=bases, signature=self.first_line(node, source), is_exported=exported,
        ))

        for base in bases:
            result.inheritance_edges.append(InheritanceEdge(
                child_id=node_id, parent_name=base, kind="inherits",
            ))

        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "method_definition":
                    self._handle_method(child, file_path, repo_id, source, result,
                                        parent_class=name, parent_id=node_id)

    def _handle_interface(self, node, file_path, repo_id, source, result, parent_id) -> None:
        lang = self._resolve_lang(file_path)
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name    = self.node_text(name_node, source)
        node_id = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.INTERFACE,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language=lang, parent_id=parent_id,
            signature=self.first_line(node, source),
        ))


    def _handle_enum(self, node, file_path, repo_id, source, result, parent_id) -> None:
        lang = self._resolve_lang(file_path)
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name    = self.node_text(name_node, source)
        node_id = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.ENUM,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language=lang, parent_id=parent_id,
            signature=self.first_line(node, source),
        ))


    def _handle_method(self, node, file_path, repo_id, source, result,
                       parent_class, parent_id) -> None:
        lang = self._resolve_lang(file_path)
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)
        kind = NodeKind.CONSTRUCTOR if name == "constructor" else NodeKind.METHOD

        typed_params = self._extract_typed_params(node, source)
        calls        = self._extract_calls(node, source)
        node_id      = self.make_node_id(repo_id, file_path,
                                         f"{parent_class}.{name}", node.start_point[0] + 1)

        result.nodes.append(IRNode(
            id=node_id, name=name, kind=kind,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language=lang, parent_id=parent_id, parent_class=parent_class,
            typed_parameters=typed_params, parameters=[p.name for p in typed_params],
            return_type=self._extract_return_type(node, source),
            signature=self.first_line(node, source), calls=calls,
        ))

        body = node.child_by_field_name("body")
        if body:
            for call_node in self.find_all(body, "call_expression"):
                callee = self._callee_name(call_node, source)
                if callee:
                    result.call_edges.append(CallEdge(
                        caller_id=node_id, callee_name=callee,
                        file_path=file_path,
                        line_number=call_node.start_point[0] + 1,
                        col_number=call_node.start_point[1],
                        is_method_call=True,
                    ))

    def _handle_function(self, node, file_path, repo_id, source, result,
                         parent_class=None, parent_id=None, exported=False,
                         override_name: Optional[str] = None) -> Optional[str]:
        """Emit a FUNCTION/METHOD node and its CallEdges. Returns the node_id."""
        lang = self._resolve_lang(file_path)
        name_node = node.child_by_field_name("name")
        name = override_name or (self.node_text(name_node, source) if name_node else "<anonymous>")
        kind = NodeKind.METHOD if parent_class else NodeKind.FUNCTION

        typed_params = self._extract_typed_params(node, source)
        calls        = self._extract_calls(node, source)
        node_id      = self.make_node_id(
            repo_id, file_path,
            f"{parent_class}.{name}" if parent_class else name,
            node.start_point[0] + 1,
        )

        result.nodes.append(IRNode(
            id=node_id, name=name, kind=kind,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language=lang, parent_id=parent_id, parent_class=parent_class,
            typed_parameters=typed_params, parameters=[p.name for p in typed_params],
            return_type=self._extract_return_type(node, source),
            signature=self.first_line(node, source),
            calls=calls, is_exported=exported,
        ))

        body = node.child_by_field_name("body")
        if body:
            for call_node in self.find_all(body, "call_expression"):
                callee = self._callee_name(call_node, source)
                if callee:
                    result.call_edges.append(CallEdge(
                        caller_id=node_id, callee_name=callee,
                        file_path=file_path,
                        line_number=call_node.start_point[0] + 1,
                        col_number=call_node.start_point[1],
                    ))
        return node_id

    def _handle_arrow(self, node, file_path, repo_id, source, result,
                      name: str, parent_class=None, parent_id=None,
                      exported=False, line_override: Optional[int] = None) -> Optional[str]:
        """Emit a FUNCTION/LAMBDA node for an arrow_function node."""
        lang = self._resolve_lang(file_path)
        kind = NodeKind.LAMBDA if parent_class else NodeKind.FUNCTION

        typed_params = self._extract_typed_params(node, source)
        calls        = self._extract_calls(node, source)
        start_line   = line_override or (node.start_point[0] + 1)
        node_id      = self.make_node_id(
            repo_id, file_path,
            f"{parent_class}.{name}" if parent_class else name,
            start_line,
        )

        result.nodes.append(IRNode(
            id=node_id, name=name, kind=kind,
            file_path=file_path,
            start_line=start_line, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language=lang, parent_id=parent_id, parent_class=parent_class,
            typed_parameters=typed_params, parameters=[p.name for p in typed_params],
            return_type=self._extract_return_type(node, source),
            signature=self.first_line(node, source),
            calls=calls, is_exported=exported,
        ))

        body = node.child_by_field_name("body")
        search_root = body if (body and body.type == "statement_block") else node
        for call_node in self.find_all(search_root, "call_expression"):
            callee = self._callee_name(call_node, source)
            if callee:
                result.call_edges.append(CallEdge(
                    caller_id=node_id, callee_name=callee,
                    file_path=file_path,
                    line_number=call_node.start_point[0] + 1,
                    col_number=call_node.start_point[1],
                ))
        return node_id

    def _handle_var_decl(self, node, file_path, repo_id, source, result,
                         parent_class=None, parent_id=None, exported=False) -> None:
        for declarator in self.find_all(node, "variable_declarator"):
            name_node  = declarator.child_by_field_name("name")
            value_node = declarator.child_by_field_name("value")
            if name_node is None or value_node is None:
                continue
            if self._is_require_call(value_node):
                continue
            name = self.node_text(name_node, source)

            if value_node.type in _ARROW_TYPES:
                self._handle_arrow(value_node, file_path, repo_id, source, result,
                                   name=name, parent_class=parent_class,
                                   parent_id=parent_id, exported=exported,
                                   line_override=node.start_point[0] + 1)
            elif value_node.type in _FUNCTION_TYPES:
                self._handle_function(value_node, file_path, repo_id, source, result,
                                      parent_class=parent_class, parent_id=parent_id,
                                      exported=exported, override_name=name)


    def _handle_export(self, node, file_path, repo_id, source, result, parent_id=None) -> None:
        for child in node.children:
            if child.type in _CLASS_TYPES:
                self._handle_class(child, file_path, repo_id, source, result,
                                   parent_id=parent_id, exported=True)
            elif child.type in _FUNCTION_TYPES:
                self._handle_function(child, file_path, repo_id, source, result,
                                      parent_class=None, parent_id=parent_id, exported=True)
            elif child.type in _VAR_DECL_TYPES:
                self._handle_var_decl(child, file_path, repo_id, source, result,
                                      parent_class=None, parent_id=parent_id, exported=True)
            elif child.type == "interface_declaration":
                self._handle_interface(child, file_path, repo_id, source, result, parent_id)
            elif child.type == "enum_declaration":
                self._handle_enum(child, file_path, repo_id, source, result, parent_id)


    def _handle_expr_statement(self, node, file_path, repo_id, source,
                               result, parent_id=None) -> None:
        for child in node.children:
            if child.type != "assignment_expression":
                continue

            left  = child.child_by_field_name("left")
            right = child.child_by_field_name("right")
            if left is None or right is None:
                continue

            left_text = self.node_text(left, source)

            if left_text.startswith("exports.") and "." in left_text:
                export_name = left_text.split(".", 1)[1].strip()
                if not export_name:
                    continue

                rnode = right
                if rnode.type == "await_expression":
                    rnode = rnode.children[-1] if rnode.children else rnode

                if rnode.type in _ARROW_TYPES:
                    self._handle_arrow(rnode, file_path, repo_id, source, result,
                                       name=export_name, parent_id=parent_id,
                                       exported=True,
                                       line_override=node.start_point[0] + 1)
                elif rnode.type in _FUNCTION_TYPES:
                    self._handle_function(rnode, file_path, repo_id, source, result,
                                          parent_class=None, parent_id=parent_id,
                                          exported=True, override_name=export_name)

            elif "module.exports" in left_text:
                name = None
                if left_text.count(".") >= 2:
                    name = left_text.rsplit(".", 1)[-1].strip() or None

                if right.type in _ARROW_TYPES:
                    self._handle_arrow(right, file_path, repo_id, source, result,
                                       name=name or "<anonymous>", parent_id=parent_id,
                                       exported=True,
                                       line_override=node.start_point[0] + 1)
                elif right.type in _FUNCTION_TYPES:
                    self._handle_function(right, file_path, repo_id, source, result,
                                          parent_class=None, parent_id=parent_id,
                                          exported=True,
                                          override_name=name)
                elif right.type in _CLASS_TYPES:
                    self._handle_class(right, file_path, repo_id, source, result,
                                       parent_id=parent_id, exported=True)

    def _emit_require_nodes(self, node, file_path, repo_id, source,
                            result, module_id, lang) -> None:
        """
        Emit REQUIRE IR nodes for every require() call in a var declaration.
        Handles both:
          const foo = require("./module")           → name = "foo"
          const { a, b } = require("./module")      → name = target module stem (BUG 5 fix)
        """
        for declarator in self.find_all(node, "variable_declarator"):
            name_node  = declarator.child_by_field_name("name")
            value_node = declarator.child_by_field_name("value")
            if name_node is None or value_node is None:
                continue
            if not self._is_require_call(value_node):
                continue

            target  = self._require_target(value_node, source)
            imp_str = self.node_text(node, source).strip()

            if name_node.type == "object_pattern":
                imp_name = target or self.node_text(name_node, source)
            else:
                imp_name = self.node_text(name_node, source)

            imp_id = self.make_node_id(repo_id, file_path, imp_name[:40],
                                       node.start_point[0] + 1)
            result.nodes.append(IRNode(
                id=imp_id, name=imp_name, kind=NodeKind.REQUIRE,
                file_path=file_path,
                start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                start_col=node.start_point[1], end_col=node.end_point[1],
                language=lang, parent_id=module_id,
                imports=[imp_str],
            ))
            if target:
                result.import_edges.append(ImportEdge(
                    source_file=file_path, target_module=target,
                    line_number=node.start_point[0] + 1,
                ))


    def _resolve_lang(self, file_path: str) -> str:
        ext = file_path.rsplit(".", 1)[-1].lower()
        return "typescript" if ext in ("ts", "tsx") else "javascript"

    def _callee_name(self, call_node: ts.Node, source: bytes) -> Optional[str]:
        func = call_node.child_by_field_name("function")
        if func is None:
            return None
        raw = self.node_text(func, source).strip()
        if raw == "require":
            return None
        leaf = raw.split(".")[-1].strip()
        if not leaf or leaf in _NOISY_CALLEES:
            return None
        return raw  
    def _is_require_call(self, node: ts.Node) -> bool:
        if node.type != "call_expression":
            return False
        func = node.child_by_field_name("function")
        return func is not None and func.type == "identifier" and func.text == b"require"

    def _is_chained_require(self, node: ts.Node, source: bytes) -> bool:
        if node.type != "call_expression":
            return False
        func = node.child_by_field_name("function")
        if func and func.type == "member_expression":
            obj = func.child_by_field_name("object")
            if obj and self._is_require_call(obj):
                return True
        return False

    def _chained_require_target(self, node: ts.Node, source: bytes) -> Optional[str]:
        func = node.child_by_field_name("function")
        if func:
            obj = func.child_by_field_name("object")
            if obj:
                return self._require_target(obj, source)
        return None

    def _require_target(self, node: ts.Node, source: bytes) -> Optional[str]:
        args = node.child_by_field_name("arguments")
        if args:
            for child in args.children:
                if child.type == "string":
                    raw = self.node_text(child, source).strip("'\"`")
                    return raw or None
        return None

    def _extract_require_strings(self, var_decl_node: ts.Node, source: bytes) -> list[str]:
        """For module.imports list — raw require() statement strings."""
        result = []
        for declarator in self.find_all(var_decl_node, "variable_declarator"):
            value_node = declarator.child_by_field_name("value")
            if value_node and self._is_require_call(value_node):
                result.append(self.node_text(var_decl_node, source).strip())
        return result

    def _extract_typed_params(self, node: ts.Node, source: bytes) -> list[Parameter]:
        params: list[Parameter] = []
        params_node = (node.child_by_field_name("parameters")
                       or node.child_by_field_name("parameter"))
        if params_node is None:
            return params
        for child in params_node.children:
            ct = child.type
            if ct == "identifier":
                params.append(Parameter(name=self.node_text(child, source)))
            elif ct in ("required_parameter", "optional_parameter"):
                id_node  = self.find_first(child, "identifier")
                typ_node = child.child_by_field_name("type")
                if id_node:
                    typ = self.node_text(typ_node, source).lstrip(":").strip() if typ_node else None
                    params.append(Parameter(name=self.node_text(id_node, source), type=typ))
            elif ct in ("rest_parameter", "assignment_pattern"):
                id_node = self.find_first(child, "identifier")
                if id_node:
                    params.append(Parameter(name=self.node_text(id_node, source)))
        return params

    def _extract_return_type(self, node: ts.Node, source: bytes) -> Optional[str]:
        ret = node.child_by_field_name("return_type")
        if ret:
            return self.node_text(ret, source).lstrip(":").strip()
        return None

    def _extract_calls(self, node: ts.Node, source: bytes) -> list[str]:
        calls: list[str] = []
        body = node.child_by_field_name("body")
        search_root = body if (body and body.type == "statement_block") else node
        for call_node in self.find_all(search_root, "call_expression"):
            callee = self._callee_name(call_node, source)
            if callee:
                calls.append(callee)
        return list(dict.fromkeys(calls))

def _parse_es_import_target(imp_str: str) -> Optional[str]:
    m = re.search(r"""from\s+['"]([^'"]+)['"]""", imp_str)
    if not m:
        return None
    raw = m.group(1)
    if raw.startswith(".") or raw.startswith("/"):
        return re.sub(r"\.\w+$", "", raw) or None
    else:
        return raw.split("/")[0].lower() or None


def _link_children(nodes: list[IRNode]) -> None:
    id_map = {n.id: n for n in nodes}
    for node in nodes:
        if node.parent_id and node.parent_id in id_map:
            parent = id_map[node.parent_id]
            if node.id not in parent.children:
                parent.children.append(node.id)