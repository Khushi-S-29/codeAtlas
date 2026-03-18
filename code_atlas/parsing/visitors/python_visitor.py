from __future__ import annotations

import logging
from typing import Optional

import tree_sitter as ts

from code_atlas.core.models import (
    IRNode, NodeKind, Parameter, ParseResult,
    CallEdge, ImportEdge, InheritanceEdge,
)
from code_atlas.parsing.visitors.base import BaseVisitor
from code_atlas.parsing.grammar_loader import get_parser

logger = logging.getLogger(__name__)

_ENUM_BASES     = frozenset({"enum", "intenum", "strenum", "flag", "intflag"})
_PROTOCOL_BASES = frozenset({"protocol"})

_BLOCK_TYPES = frozenset({
    "if_statement", "elif_clause", "else_clause",
    "for_statement", "while_statement",
    "with_statement",
    "try_statement", "except_clause", "finally_clause",
    "match_statement", "case_clause",
})

_PY_BUILTINS = frozenset({
    "print", "len", "range", "str", "int", "float", "bool", "list",
    "dict", "set", "tuple", "type", "super", "isinstance", "issubclass",
    "hasattr", "getattr", "setattr", "delattr", "callable",
    "map", "filter", "zip", "enumerate", "sorted", "reversed",
    "any", "all", "sum", "min", "max", "abs", "round", "pow",
    "open", "input", "format", "repr", "id", "hash", "iter", "next",
    "vars", "dir", "help", "object", "property", "staticmethod", "classmethod",
    "append", "extend", "insert", "remove", "pop", "clear", "copy",
    "update", "keys", "values", "items", "get", "setdefault",
    "add", "discard", "union", "intersection", "difference",
    "strip", "split", "join", "replace", "find", "count", "startswith", "endswith",
    "upper", "lower", "title", "encode", "decode", "format_map",
    "read", "write", "readline", "readlines", "close", "seek", "tell",
    "connect", "cursor", "execute", "fetchall", "fetchone", "commit", "rollback",
    "logging", "logger", "warning", "error", "debug", "info", "critical",
    "assertequal", "asserttrue", "assertfalse", "assertraises", "assertin",
    "assertnotin", "assertisnone", "assertisnotnone",
})


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
            result.errors.append("Syntax errors present — partial parse may be incomplete")

        #  Module node 
        module_id = self.make_node_id(repo_id, file_path, "__module__", 1)
        module_imports: list[str] = []

        for node in root.children:
            if node.type in ("import_statement", "import_from_statement"):
                imp_str = self.node_text(node, source_bytes).strip()
                module_imports.append(imp_str)

                imp_id = self.make_node_id(repo_id, file_path, imp_str[:40],
                                           node.start_point[0] + 1)
                result.nodes.append(IRNode(
                    id=imp_id, name=imp_str, kind=NodeKind.IMPORT,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1], end_col=node.end_point[1],
                    language="python", parent_id=module_id, imports=[imp_str],
                ))

                target = _parse_python_import_target(imp_str)
                if target:
                    result.import_edges.append(ImportEdge(
                        source_file=file_path, target_module=target,
                        line_number=node.start_point[0] + 1,
                    ))

        result.nodes.append(IRNode(
            id=module_id, name=file_path, kind=NodeKind.MODULE,
            file_path=file_path,
            start_line=1, end_line=root.end_point[0] + 1,
            start_col=0, end_col=0,
            language="python", imports=module_imports,
        ))

        self._walk_body(root, file_path, repo_id, source_bytes, result,
                        parent_class=None, parent_id=module_id, depth=0)
        _link_children(result.nodes)
        return result

    def _walk_body(
        self,
        body_node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        parent_class: Optional[str],
        parent_id: Optional[str],
        depth: int = 0,
    ) -> None:
        for node in body_node.children:
            t = node.type

            if t == "class_definition":
                self._handle_class(node, file_path, repo_id, source, result, parent_id)

            elif t == "function_definition":
                self._handle_function(node, file_path, repo_id, source, result,
                                      parent_class=parent_class, parent_id=parent_id)

            elif t == "decorated_definition":
                inner = self.find_first(node, "function_definition", "class_definition")
                decs  = self._get_decorators(node, source)
                if inner:
                    if inner.type == "class_definition":
                        self._handle_class(inner, file_path, repo_id, source, result,
                                           parent_id, decorators=decs)
                    else:
                        self._handle_function(inner, file_path, repo_id, source, result,
                                              parent_class=parent_class, parent_id=parent_id,
                                              decorators=decs)

            elif t == "expression_statement" and parent_id:
                expr = self.find_first(node, "assignment")
                if expr:
                    self._handle_assignment(expr, file_path, repo_id, source, result, parent_id)

            elif t == "type_alias_statement":
                self._handle_type_alias(node, file_path, repo_id, source, result, parent_id)

            elif t in _BLOCK_TYPES and depth < 4:
                self._walk_body(node, file_path, repo_id, source, result,
                                parent_class=parent_class, parent_id=parent_id,
                                depth=depth + 1)

            elif t == "block" and depth < 4:
                self._walk_body(node, file_path, repo_id, source, result,
                                parent_class=parent_class, parent_id=parent_id,
                                depth=depth + 1)

    def _handle_class(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        parent_id: Optional[str],
        decorators: Optional[list[str]] = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)

        bases: list[str] = []
        args = node.child_by_field_name("superclasses")
        if args:
            for child in args.children:
                if child.type in ("identifier", "attribute"):
                    bases.append(self.node_text(child, source).strip())

        base_lower = [b.split(".")[-1].lower() for b in bases]
        if any(b in _ENUM_BASES for b in base_lower):
            kind = NodeKind.ENUM
        elif any(b in _PROTOCOL_BASES for b in base_lower):
            kind = NodeKind.INTERFACE
        else:
            kind = NodeKind.CLASS

        node_id = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)

        result.nodes.append(IRNode(
            id=node_id, name=name, kind=kind,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language="python", parent_id=parent_id,
            bases=bases, decorators=decorators or [],
            signature=self.first_line(node, source),
            docstring=self._extract_docstring(node, source),
        ))

        for base in bases:
            result.inheritance_edges.append(InheritanceEdge(
                child_id=node_id, parent_name=base,
                kind="implements" if kind == NodeKind.INTERFACE else "inherits",
            ))

        body = node.child_by_field_name("body")
        if body:
            self._walk_body(body, file_path, repo_id, source, result,
                            parent_class=name, parent_id=node_id, depth=0)

    def _handle_function(
        self,
        node: ts.Node,
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        parent_class: Optional[str],
        parent_id: Optional[str],
        decorators: Optional[list[str]] = None,
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.node_text(name_node, source)

        if name == "__init__":
            kind = NodeKind.CONSTRUCTOR
        elif parent_class:
            kind = NodeKind.METHOD
        else:
            kind = NodeKind.FUNCTION

        typed_params = self._extract_typed_params(node, source)
        calls        = self._extract_calls(node, source)
        refs         = self._extract_references(node, source)
        decs         = decorators or self._get_decorators(node, source)

        node_id = self.make_node_id(
            repo_id, file_path,
            f"{parent_class}.{name}" if parent_class else name,
            node.start_point[0] + 1,
        )

        result.nodes.append(IRNode(
            id=node_id, name=name, kind=kind,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language="python", parent_id=parent_id, parent_class=parent_class,
            typed_parameters=typed_params, parameters=[p.name for p in typed_params],
            return_type=self._extract_return_type(node, source),
            docstring=self._extract_docstring(node, source),
            signature=self.first_line(node, source),
            calls=calls, references=refs, decorators=decs,
            is_exported=not name.startswith("_"),
        ))

        body = node.child_by_field_name("body")
        if body:
            for call_node in self.find_all(body, "call"):
                func = call_node.child_by_field_name("function")
                if func:
                    callee_raw = self.node_text(func, source).strip()
                    callee     = self._clean_callee(callee_raw, parent_class)
                    if callee:
                        result.call_edges.append(CallEdge(
                            caller_id=node_id, callee_name=callee_raw,
                            file_path=file_path,
                            line_number=call_node.start_point[0] + 1,
                            col_number=call_node.start_point[1],
                        ))

        if body:
            for lambda_node in self.find_all(body, "lambda"):
                self._handle_lambda(lambda_node, file_path, repo_id, source, result, node_id)

        # Nested defs (already handled by _walk_body recursion from _handle_class,
        # but also needed for nested functions inside free functions)
        if body:
            self._walk_body(body, file_path, repo_id, source, result,
                            parent_class=parent_class, parent_id=node_id, depth=0)

    def _handle_lambda(
        self, node: ts.Node, file_path: str, repo_id: str,
        source: bytes, result: ParseResult, parent_id: Optional[str],
    ) -> None:
        start_line = node.start_point[0] + 1
        node_id    = self.make_node_id(repo_id, file_path, "__lambda__", start_line)
        params     = self._extract_lambda_params(node, source)
        calls      = self._extract_calls(node, source)

        result.nodes.append(IRNode(
            id=node_id, name="<lambda>", kind=NodeKind.LAMBDA,
            file_path=file_path,
            start_line=start_line, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language="python", parent_id=parent_id,
            typed_parameters=params, parameters=[p.name for p in params],
            signature=self.node_text(node, source)[:80].strip(),
            calls=calls,
        ))

    def _handle_assignment(
        self, node: ts.Node, file_path: str, repo_id: str,
        source: bytes, result: ParseResult, parent_id: str,
    ) -> None:
        left  = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None:
            return
        name    = self.node_text(left, source).strip()
        value   = self.node_text(right, source).strip() if right else None
        typ     = node.child_by_field_name("type")
        type_an = self.node_text(typ, source).strip() if typ else None
        node_id = self.make_node_id(repo_id, file_path,
                                    f"assign:{name}", node.start_point[0] + 1)

        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.ASSIGNMENT,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language="python", parent_id=parent_id,
            value=value, return_type=type_an,
            signature=self.node_text(node, source)[:120].strip(),
        ))

    def _clean_callee(self, raw: str, parent_class: Optional[str]) -> Optional[str]:
        if raw.startswith("self.") or raw.startswith("cls."):
            method = raw.split(".", 1)[1]
            leaf   = method.split(".")[-1].lower()
            return None if leaf in _PY_BUILTINS else raw
        leaf = raw.split(".")[-1].lower()
        return None if (not leaf or leaf in _PY_BUILTINS) else raw

    def _extract_typed_params(self, node: ts.Node, source: bytes) -> list[Parameter]:
        params: list[Parameter] = []
        params_node = node.child_by_field_name("parameters")
        if params_node is None:
            return params

        for child in params_node.children:
            ct = child.type
            if ct == "identifier":
                name = self.node_text(child, source)
                if name not in ("self", "cls"):
                    params.append(Parameter(name=name))
            elif ct in ("typed_parameter", "typed_default_parameter"):
                id_node  = self.find_first(child, "identifier")
                typ_node = child.child_by_field_name("type")
                if id_node:
                    name = self.node_text(id_node, source)
                    if name not in ("self", "cls"):
                        typ = self.node_text(typ_node, source).strip() if typ_node else None
                        params.append(Parameter(name=name, type=typ))
            elif ct == "default_parameter":
                id_node = self.find_first(child, "identifier")
                if id_node:
                    name = self.node_text(id_node, source)
                    if name not in ("self", "cls"):
                        params.append(Parameter(name=name))
            elif ct in ("list_splat_pattern", "dictionary_splat_pattern"):
                id_node = self.find_first(child, "identifier")
                if id_node:
                    params.append(Parameter(name=self.node_text(id_node, source)))
        return params

    def _extract_lambda_params(self, node: ts.Node, source: bytes) -> list[Parameter]:
        params: list[Parameter] = []
        p = node.child_by_field_name("parameters")
        if p:
            for child in p.children:
                if child.type == "identifier":
                    params.append(Parameter(name=self.node_text(child, source)))
        return params

    def _extract_return_type(self, node: ts.Node, source: bytes) -> Optional[str]:
        ret = node.child_by_field_name("return_type")
        if ret:
            return self.node_text(ret, source).lstrip("->").strip()
        return None

    def _extract_docstring(self, node: ts.Node, source: bytes) -> Optional[str]:
        body = node.child_by_field_name("body")
        if body is None:
            return None
        for child in body.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        raw = self.node_text(sub, source).strip()
                        return raw.strip('"""').strip("'''").strip('"').strip("'").strip()
        return None

    def _extract_calls(self, node: ts.Node, source: bytes) -> list[str]:
        """Return deduplicated callee name strings for node.calls."""
        calls: list[str] = []
        body = node.child_by_field_name("body")
        if body is None:
            body = node
        for call_node in self.find_all(body, "call"):
            func = call_node.child_by_field_name("function")
            if func:
                raw    = self.node_text(func, source).strip()
                callee = self._clean_callee(raw, None)
                if callee:
                    calls.append(raw)
        return list(dict.fromkeys(calls))

    def _extract_references(self, node: ts.Node, source: bytes) -> list[str]:
        """
        Extract identifier references that are NOT call expressions.
        Python equivalents of the JSX/callback patterns:

          Callback args      : sorted(items, key=my_func)  → key=my_func
          Higher-order calls : map(fn, items)              → fn as argument
          Decorator targets  : @app.route → 'route'
          Return bare ident  : return my_validator
          Conditional        : x if condition else fallback_fn
          Assignment rhs     : handler = my_func  (non-call rhs)
          List/tuple items   : validators = [check_a, check_b]
          Dict values        : routes = {"path": view_fn}
          Signal connect     : signal.connect(handler)  → identifier arg
        """
        refs: set[str] = set()
        body = node.child_by_field_name("body")
        search_root = body if body else node

        _SKIP = frozenset({
            "True", "False", "None", "self", "cls",
            "int", "str", "float", "bool", "list", "dict", "set",
            "tuple", "type", "object", "super",
        })

        def _collect(n: ts.Node) -> None:
            t = n.type

            if t == "keyword_argument":
                val = n.child_by_field_name("value")
                if val and val.type == "identifier":
                    refs.add(self.node_text(val, source).strip())

            elif t == "argument_list":
                for child in n.children:
                    if child.type == "identifier":
                        refs.add(self.node_text(child, source).strip())

            elif t == "return_statement":
                for child in n.children:
                    if child.type == "identifier":
                        refs.add(self.node_text(child, source).strip())

            elif t == "conditional_expression":
                for child in n.children:
                    if child.type == "identifier":
                        refs.add(self.node_text(child, source).strip())

            elif t in ("list", "tuple", "set"):
                for child in n.children:
                    if child.type == "identifier":
                        refs.add(self.node_text(child, source).strip())

            # Dict value: {"key": fn_ref}
            elif t == "pair":
                val = n.child_by_field_name("value")
                if val and val.type == "identifier":
                    refs.add(self.node_text(val, source).strip())

            elif t == "assignment":
                right = n.child_by_field_name("right")
                if right and right.type == "identifier":
                    refs.add(self.node_text(right, source).strip())

            for child in n.children:
                if child.type != "call":
                    _collect(child)

        _collect(search_root)
        return [r for r in refs if len(r) > 1 and r not in _SKIP]

    def _handle_type_alias(
        self,
        node: ts.Node,   
        file_path: str,
        repo_id: str,
        source: bytes,
        result: ParseResult,
        parent_id: Optional[str],
    ) -> None:
        """Handle Python 3.12+ `type Foo = Bar` syntax → TYPE_ANNOTATION node."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name     = self.node_text(name_node, source).strip()
        val_node = node.child_by_field_name("value")
        val_text = self.node_text(val_node, source).strip() if val_node else None
        node_id  = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.TYPE_ANNOTATION,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language="python", parent_id=parent_id,
            value=val_text,
            signature=f"type {name} = {val_text or ''}".strip(),
        ))

    def _get_decorators(self, node: ts.Node, source: bytes) -> list[str]:
        return [
            self.node_text(d, source).strip()
            for d in self.get_children_of_type(node, "decorator")
        ]


# Module helpers 

def _parse_python_import_target(imp_str: str) -> Optional[str]:
    import re
    m = re.match(r"from\s+(\.*\S+)\s+import", imp_str)
    if m:
        mod = m.group(1).lstrip(".")
        return mod.split(".")[0] or None
    m = re.match(r"import\s+(\S+)", imp_str)
    if m:
        return m.group(1).split(".")[0] or None
    return None


def _link_children(nodes: list[IRNode]) -> None:
    id_map = {n.id: n for n in nodes}
    for node in nodes:
        if node.parent_id and node.parent_id in id_map:
            parent = id_map[node.parent_id]
            if node.id not in parent.children:
                parent.children.append(node.id)