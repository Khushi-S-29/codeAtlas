# from __future__ import annotations

# import logging
# import re
# from typing import Optional

# import tree_sitter as ts

# from code_atlas.core.models import (
#     IRNode, NodeKind, Parameter, ParseResult,
#     CallEdge, ImportEdge, InheritanceEdge,
# )
# from code_atlas.parsing.visitors.base import BaseVisitor
# from code_atlas.parsing.grammar_loader import get_parser

# logger = logging.getLogger(__name__)

# _FUNCTION_TYPES = frozenset({
#     "function_declaration", "function",
#     "generator_function_declaration", "generator_function",
# })
# _ARROW_TYPES    = frozenset({"arrow_function"})
# _CLASS_TYPES    = frozenset({"class_declaration", "class"})
# _VAR_DECL_TYPES = frozenset({"lexical_declaration", "variable_declaration"})

# _NOISY_CALLEES = frozenset({
#     "push", "pop", "shift", "unshift", "splice", "slice", "map", "filter",
#     "reduce", "forEach", "find", "findIndex", "some", "every", "includes",
#     "indexOf", "join", "split", "replace", "trim", "toLowerCase", "toUpperCase",
#     "toString", "valueOf", "hasOwnProperty", "keys", "values", "entries",
#     "assign", "freeze", "create", "then", "catch", "finally", "resolve", "reject",
#     "json", "text", "blob", "arrayBuffer", "formData", "clone",
#     "addEventListener", "removeEventListener", "dispatchEvent",
#     "setAttribute", "getAttribute", "removeAttribute", "appendChild",
#     "querySelector", "querySelectorAll", "getElementById", "getElementsByClassName",
#     "preventDefault", "stopPropagation",
#     "toFixed", "toLocaleString", "toLocaleDateString",
#     "delete", "get", "set", "has", "clear", "size",
#     "start", "end", "test", "exec", "match", "search",
#     "round", "floor", "ceil", "abs", "max", "min", "random", "sqrt", "pow",
#     "now", "parse", "stringify",
#     "send", "status", "json", "end", "redirect",
#     "emit", "on", "off", "once", "removeListener",
#     "setTimeout", "setInterval", "clearTimeout", "clearInterval",
#     "requestAnimationFrame", "cancelAnimationFrame",
#     "scrollTo", "scrollIntoView", "focus", "blur", "click",
#     "entries", "fromEntries", "flat", "flatMap", "fill", "copyWithin",
#     "sort", "reverse", "concat",
# })


# class JavaScriptVisitor(BaseVisitor):
#     language_name = "javascript"

#     def parse(self, source_code: str, file_path: str, repo_id: str) -> ParseResult:
#         lang   = self._resolve_lang(file_path)
#         result = ParseResult(file_path=file_path, language=lang)
#         parser = get_parser(lang) or get_parser("javascript")

#         if parser is None:
#             result.success = False
#             result.errors.append(f"No tree-sitter grammar for {lang}")
#             return result

#         source_bytes = source_code.encode("utf-8", errors="replace")

#         try:
#             tree = parser.parse(source_bytes)
#         except Exception as exc:
#             result.success = False
#             result.errors.append(f"Parse error: {exc}")
#             return result

#         root = tree.root_node
#         if root.has_error:
#             result.errors.append("Syntax errors present — results may be incomplete")

#         module_id = self.make_node_id(repo_id, file_path, "__module__", 1)
#         module_imports: list[str] = []
#         module_calls = []
#         module_refs = []

#         # Collect module-level calls and refs from TOP-LEVEL scope only.
#         # Do NOT use find_all(root, ...) — that recurses into every function
#         # body and pollutes module_calls/module_refs with inner function names,
#         # creating false CALLS edges from the module entry point to everything.
#         def _walk_toplevel_calls(node):
#             _STOP = _FUNCTION_TYPES | _ARROW_TYPES | _CLASS_TYPES | {
#                 "method_definition"
#             }
#             for child in node.children:
#                 if child.type in _STOP:
#                     continue  # do not descend into function/class bodies
#                 if child.type == "call_expression":
#                     callee = self._callee_name(child, source_bytes)
#                     if self._is_require_call(child):
#                         target = self._require_target(child, source_bytes)
#                         if target:
#                             module_imports.append(target)
#                     if callee:
#                         module_calls.append(callee)
#                     args = child.child_by_field_name("arguments")
#                     if args:
#                         for arg in args.children:
#                             if arg.type == "identifier":
#                                 module_refs.append(
#                                     self.node_text(arg, source_bytes).strip()
#                                 )
#                     _walk_toplevel_calls(child)
#                 else:
#                     _walk_toplevel_calls(child)

#         _walk_toplevel_calls(root)

#         for node in root.children:
#             if node.type == "import_statement":
#                 module_imports.append(self.node_text(node, source_bytes).strip())
#             elif node.type in _VAR_DECL_TYPES:
#                 module_imports.extend(self._extract_require_strings(node, source_bytes))
#                 for declarator in node.children:
#                     if declarator.type != "variable_declarator":
#                         continue
#                     val = declarator.child_by_field_name("value")
#                     if val is not None and val.type == "array":
#                         for element in val.children:
#                             if element.type == "identifier":
#                                 text = self.node_text(element, source_bytes).strip()
#                                 if text:
#                                     module_refs.append(text)

#         result.nodes.append(IRNode(
#             id=module_id,
#             name=file_path,
#             kind=NodeKind.MODULE,
#             file_path=file_path,
#             start_line=1,
#             end_line=root.end_point[0] + 1,
#             language=lang,
#             imports=module_imports,
#             calls=module_calls,
#             references=module_refs,
#         ))

#         for node in root.children:
#             if node.type == "import_statement":
#                 imp_str = self.node_text(node, source_bytes).strip()
#                 imp_id  = self.make_node_id(repo_id, file_path, imp_str[:40], node.start_point[0] + 1)
#                 result.nodes.append(IRNode(
#                     id=imp_id, name=imp_str, kind=NodeKind.IMPORT,
#                     file_path=file_path,
#                     start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
#                     start_col=node.start_point[1], end_col=node.end_point[1],
#                     language=lang, parent_id=module_id, imports=[imp_str],
#                 ))
#                 target = _parse_es_import_target(imp_str)
#                 if target:
#                     result.import_edges.append(ImportEdge(
#                         source_file=file_path,
#                         target_module=target,
#                         line_number=node.start_point[0] + 1,
#                     ))

#         for node in root.children:
#             if node.type in _VAR_DECL_TYPES:
#                 self._emit_require_nodes(node, file_path, repo_id, source_bytes,
#                                          result, module_id, lang)

#         for node in root.children:
#             if node.type == "expression_statement":
#                 expr = self.find_first(node, "call_expression")
#                 if expr and self._is_chained_require(expr, source_bytes):
#                     raw    = self.node_text(expr, source_bytes).strip()
#                     target = self._chained_require_target(expr, source_bytes)
#                     imp_id = self.make_node_id(repo_id, file_path, raw[:40], node.start_point[0] + 1)
                    
#                     result.nodes.append(IRNode(
#                         id=imp_id, name=raw, kind=NodeKind.REQUIRE,
#                         file_path=file_path,
#                         start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
#                         start_col=node.start_point[1], end_col=node.end_point[1],
#                         language=lang, parent_id=module_id, imports=[raw],
#                     ))
#                     if target:
#                         result.import_edges.append(ImportEdge(
#                             source_file=file_path, target_module=target,
#                             line_number=node.start_point[0] + 1,
#                         ))

#         for call in self.find_all(root, "call_expression"):
#             args_node = call.child_by_field_name("arguments")
#             if args_node:
#                 for arg in args_node.children:
#                     if arg.type == "call_expression" and self._is_require_call(arg):
#                         raw_req = self.node_text(arg, source_bytes).strip()
#                         target_req = self._require_target(arg, source_bytes)
#                         req_id = self.make_node_id(repo_id, file_path, raw_req[:40], arg.start_point[0] + 1)

#                         result.nodes.append(IRNode(
#                             id=req_id,
#                             name=raw_req,
#                             kind=NodeKind.REQUIRE,
#                             file_path=file_path,
#                             start_line=arg.start_point[0] + 1,
#                             end_line=arg.end_point[0] + 1,
#                             start_col=arg.start_point[1],
#                             end_col=arg.end_point[1],
#                             language=lang,
#                             parent_id=module_id,
#                             imports=[raw_req],
#                         ))

#                         if target_req:
#                             result.import_edges.append(ImportEdge(
#                                 source_file=file_path,
#                                 target_module=target_req,
#                                 line_number=arg.start_point[0] + 1,
#                             ))

#         for node in root.children:
#             if node.type == "interface_declaration":
#                 self._handle_interface(node, file_path, repo_id, source_bytes, result, module_id)
#             elif node.type == "enum_declaration":
#                 self._handle_enum(node, file_path, repo_id, source_bytes, result, module_id)
#             elif node.type == "type_alias_declaration":
#                 self._handle_type_alias(node, file_path, repo_id, source_bytes, result, module_id)

#         self._walk_statements(root.children, file_path, repo_id, source_bytes, result,
#                               parent_class=None, parent_id=module_id)

#         _link_children(result.nodes)
#         return result   
    
#     def _walk_statements(
#         self, nodes, file_path, repo_id, source, result,
#         parent_class, parent_id,
#     ) -> None:
#         for node in nodes:
#             t = node.type
#             if t in _CLASS_TYPES:
#                 self._handle_class(node, file_path, repo_id, source, result,
#                                    parent_id=parent_id)
#             elif t in _FUNCTION_TYPES:
#                 self._handle_function(node, file_path, repo_id, source, result,
#                                       parent_class=parent_class, parent_id=parent_id)
#             elif t == "export_statement":
#                 self._handle_export(node, file_path, repo_id, source, result,
#                                     parent_id=parent_id)
#             elif t in _VAR_DECL_TYPES:
#                 self._handle_var_decl(node, file_path, repo_id, source, result,
#                                       parent_class=parent_class, parent_id=parent_id)
#             elif t == "expression_statement":
#                 self._handle_expr_statement(node, file_path, repo_id, source, result,
#                                             parent_id=parent_id)
#             elif t == "interface_declaration":
#                 self._handle_interface(node, file_path, repo_id, source, result, parent_id)
#             elif t == "enum_declaration":
#                 self._handle_enum(node, file_path, repo_id, source, result, parent_id)


#     def _handle_class(self, node, file_path, repo_id, source, result,
#                       parent_id=None, exported=False) -> None:
#         lang = self._resolve_lang(file_path)
#         name_node = node.child_by_field_name("name")
#         name = self.node_text(name_node, source) if name_node else "<anonymous>"

#         bases: list[str] = []
#         heritage = self.find_first(node, "class_heritage")
#         if heritage:
#             for ident in self.find_all(heritage, "type_identifier", "identifier",
#                                         "member_expression"):
#                 bases.append(self.node_text(ident, source).strip())
#                 break

#         type_params = self._extract_ts_type_params(node, source)
#         decorators  = self._extract_ts_decorators(node, source)

#         node_id = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
#         base_sig = f"class {name}{type_params}"
#         if bases:
#             base_sig += f" extends {bases[0]}"
#         result.nodes.append(IRNode(
#             id=node_id, name=name, kind=NodeKind.CLASS,
#             file_path=file_path,
#             start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
#             start_col=node.start_point[1], end_col=node.end_point[1],
#             language=lang, parent_id=parent_id,
#             bases=bases, decorators=decorators,
#             signature=base_sig, is_exported=exported,
#         ))

#         for base in bases:
#             result.inheritance_edges.append(InheritanceEdge(
#                 child_id=node_id, parent_name=base, kind="inherits",
#             ))

#         body = node.child_by_field_name("body")
#         if body:
#             for child in body.children:
#                 if child.type == "method_definition":
#                     self._handle_method(child, file_path, repo_id, source, result,
#                                         parent_class=name, parent_id=node_id)


#     def _handle_interface(self, node, file_path, repo_id, source, result, parent_id) -> None:
#         lang = self._resolve_lang(file_path)
#         name_node = node.child_by_field_name("name")
#         if not name_node:
#             return
#         name = self.node_text(name_node, source)

#         type_params = self._extract_ts_type_params(node, source)

#         bases: list[str] = []
#         extends = node.child_by_field_name("extends")
#         if extends:
#             for ident in self.find_all(extends, "type_identifier", "identifier"):
#                 bases.append(self.node_text(ident, source).strip())

#         node_id = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
#         result.nodes.append(IRNode(
#             id=node_id, name=name, kind=NodeKind.INTERFACE,
#             file_path=file_path,
#             start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
#             start_col=node.start_point[1], end_col=node.end_point[1],
#             language=lang, parent_id=parent_id, bases=bases,
#             signature=f"interface {name}{type_params}" + (f" extends {', '.join(bases)}" if bases else ""),
#         ))
#         for base in bases:
#             result.inheritance_edges.append(InheritanceEdge(
#                 child_id=node_id, parent_name=base, kind="inherits",
#             ))


#     def _handle_enum(self, node, file_path, repo_id, source, result, parent_id) -> None:
#         lang = self._resolve_lang(file_path)
#         name_node = node.child_by_field_name("name")
#         if not name_node:
#             return
#         name    = self.node_text(name_node, source)
#         node_id = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
#         result.nodes.append(IRNode(
#             id=node_id, name=name, kind=NodeKind.ENUM,
#             file_path=file_path,
#             start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
#             start_col=node.start_point[1], end_col=node.end_point[1],
#             language=lang, parent_id=parent_id,
#             signature=self.first_line(node, source),
#         ))


#     def _handle_method(self, node, file_path, repo_id, source, result,
#                        parent_class, parent_id) -> None:
#         lang = self._resolve_lang(file_path)
#         name_node = node.child_by_field_name("name")
#         if name_node is None:
#             return
#         name = self.node_text(name_node, source)
#         kind = NodeKind.CONSTRUCTOR if name == "constructor" else NodeKind.METHOD

#         typed_params = self._extract_typed_params(node, source)
#         calls        = self._extract_calls(node, source)
#         node_id      = self.make_node_id(repo_id, file_path,
#                                          f"{parent_class}.{name}", node.start_point[0] + 1)

#         result.nodes.append(IRNode(
#             id=node_id, name=name, kind=kind,
#             file_path=file_path,
#             start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
#             start_col=node.start_point[1], end_col=node.end_point[1],
#             language=lang, parent_id=parent_id, parent_class=parent_class,
#             typed_parameters=typed_params, parameters=[p.name for p in typed_params],
#             return_type=self._extract_return_type(node, source),
#             signature=self.first_line(node, source), calls=calls,
#         ))

#         body = node.child_by_field_name("body")
#         if body:
#             for call_node in self.find_all(body, "call_expression"):
#                 callee = self._callee_name(call_node, source)
#                 if callee:
#                     result.call_edges.append(CallEdge(
#                         caller_id=node_id, callee_name=callee,
#                         file_path=file_path,
#                         line_number=call_node.start_point[0] + 1,
#                         col_number=call_node.start_point[1],
#                         is_method_call=True,
#                     ))


#     def _handle_function(self, node, file_path, repo_id, source, result,
#                          parent_class=None, parent_id=None, exported=False,
#                          override_name: Optional[str] = None) -> Optional[str]:
#         lang = self._resolve_lang(file_path)
#         name_node = node.child_by_field_name("name")
#         name = override_name or (self.node_text(name_node, source) if name_node else "<anonymous>")
#         kind = NodeKind.METHOD if parent_class else NodeKind.FUNCTION

#         typed_params = self._extract_typed_params(node, source)
#         calls        = self._extract_calls(node, source)
#         refs         = self._extract_references(node, source)
#         node_id      = self.make_node_id(
#             repo_id, file_path,
#             f"{parent_class}.{name}" if parent_class else name,
#             node.start_point[0] + 1,
#         )

#         result.nodes.append(IRNode(
#             id=node_id, name=name, kind=kind,
#             file_path=file_path,
#             start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
#             start_col=node.start_point[1], end_col=node.end_point[1],
#             language=lang, parent_id=parent_id, parent_class=parent_class,
#             typed_parameters=typed_params, parameters=[p.name for p in typed_params],
#             return_type=self._extract_return_type(node, source),
#             signature=self.first_line(node, source),
#             calls=calls, references=refs, is_exported=exported,
#         ))

#         body = node.child_by_field_name("body")
#         if body:
#             for call_node in self.find_all(body, "call_expression"):
#                 callee = self._callee_name(call_node, source)
#                 if callee:
#                     result.call_edges.append(CallEdge(
#                         caller_id=node_id, callee_name=callee,
#                         file_path=file_path,
#                         line_number=call_node.start_point[0] + 1,
#                         col_number=call_node.start_point[1],
#                     ))
#             if body.type == "statement_block":
#                 self._walk_statements(body.children, file_path, repo_id, source, result,
#                                       parent_class=parent_class, parent_id=node_id)
#         return node_id


#     def _handle_arrow(self, node, file_path, repo_id, source, result,
#                       name: str, parent_class=None, parent_id=None,
#                       exported=False, line_override: Optional[int] = None) -> Optional[str]:
#         lang = self._resolve_lang(file_path)
#         kind = NodeKind.LAMBDA if parent_class else NodeKind.FUNCTION

#         typed_params = self._extract_typed_params(node, source)
#         calls        = self._extract_calls(node, source)
#         refs         = self._extract_references(node, source)
#         start_line   = line_override or (node.start_point[0] + 1)
#         node_id      = self.make_node_id(
#             repo_id, file_path,
#             f"{parent_class}.{name}" if parent_class else name,
#             start_line,
#         )

#         result.nodes.append(IRNode(
#             id=node_id, name=name, kind=kind,
#             file_path=file_path,
#             start_line=start_line, end_line=node.end_point[0] + 1,
#             start_col=node.start_point[1], end_col=node.end_point[1],
#             language=lang, parent_id=parent_id, parent_class=parent_class,
#             typed_parameters=typed_params, parameters=[p.name for p in typed_params],
#             return_type=self._extract_return_type(node, source),
#             signature=self.first_line(node, source),
#             calls=calls, references=refs, is_exported=exported,
#         ))

#         body = node.child_by_field_name("body")
#         search_root = body if (body and body.type == "statement_block") else node
#         for call_node in self.find_all(search_root, "call_expression"):
#             callee = self._callee_name(call_node, source)
#             if callee:
#                 result.call_edges.append(CallEdge(
#                     caller_id=node_id, callee_name=callee,
#                     file_path=file_path,
#                     line_number=call_node.start_point[0] + 1,
#                     col_number=call_node.start_point[1],
#                 ))
#         if body and body.type == "statement_block":
#             self._walk_statements(body.children, file_path, repo_id, source, result,
#                                   parent_class=parent_class, parent_id=node_id)
#         return node_id


#     def _handle_var_decl(self, node, file_path, repo_id, source, result,
#                          parent_class=None, parent_id=None, exported=False) -> None:
#         for declarator in node.children:
#             if declarator.type != "variable_declarator":
#                 continue
#             name_node  = declarator.child_by_field_name("name")
#             value_node = declarator.child_by_field_name("value")
#             if name_node is None or value_node is None:
#                 continue
#             if self._is_require_call(value_node):
#                 continue
#             name = self.node_text(name_node, source)

#             if value_node.type in _ARROW_TYPES:
#                 self._handle_arrow(value_node, file_path, repo_id, source, result,
#                                    name=name, parent_class=parent_class,
#                                    parent_id=parent_id, exported=exported,
#                                    line_override=node.start_point[0] + 1)
#             elif value_node.type in _FUNCTION_TYPES:
#                 self._handle_function(value_node, file_path, repo_id, source, result,
#                                       parent_class=parent_class, parent_id=parent_id,
#                                       exported=exported, override_name=name)
#             elif value_node.type == "array":
#                 lang    = self._resolve_lang(file_path)
#                 node_id = self.make_node_id(repo_id, file_path, name,
#                                             node.start_point[0] + 1)

#                 _SKIP_IDENTS = frozenset({
#                     "true", "false", "null", "undefined", "this",
#                     "const", "let", "var",
#                 })
#                 array_refs: list[str] = []
#                 for element in value_node.children:
#                     if element.type == "identifier":
#                         text = self.node_text(element, source).strip()
#                         if text and text not in _SKIP_IDENTS:
#                             array_refs.append(text)

#                 result.nodes.append(IRNode(
#                     id=node_id, name=name, kind=NodeKind.ASSIGNMENT,
#                     file_path=file_path,
#                     start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
#                     start_col=node.start_point[1],       end_col=node.end_point[1],
#                     language=lang, parent_id=parent_id,
#                     signature=self.first_line(node, source),
#                     references=array_refs,
#                     is_exported=exported,
#                 ))


#     def _handle_export(self, node, file_path, repo_id, source, result, parent_id=None) -> None:
  
#         exported_names: list[str] = []

#         for child in node.children:
#             if child.type in _CLASS_TYPES:
#                 self._handle_class(child, file_path, repo_id, source, result,
#                                    parent_id=parent_id, exported=True)

#             elif child.type in _FUNCTION_TYPES:
#                 self._handle_function(child, file_path, repo_id, source, result,
#                                       parent_class=None, parent_id=parent_id, exported=True)

#             elif child.type in _VAR_DECL_TYPES:
#                 self._handle_var_decl_exported(child, file_path, repo_id, source, result,
#                                                parent_id=parent_id)

#             elif child.type == "interface_declaration":
#                 self._handle_interface(child, file_path, repo_id, source, result, parent_id)

#             elif child.type == "enum_declaration":
#                 self._handle_enum(child, file_path, repo_id, source, result, parent_id)

#             elif child.type == "identifier":
#                 name = self.node_text(child, source).strip()
#                 if name and name not in ("default",):
#                     exported_names.append(name)

#             elif child.type == "call_expression":
#                 self._handle_wrapped_component(child, file_path, repo_id, source,
#                                                result, parent_id)

#             elif child.type == "type_alias_declaration":
#                 self._handle_type_alias(child, file_path, repo_id, source, result, parent_id)

#         if exported_names:
#             for n in result.nodes:
#                 if n.name in exported_names and n.file_path == file_path:
#                     n.is_exported = True

#     def _handle_var_decl_exported(self, node, file_path, repo_id, source,
#                                    result, parent_id=None) -> None:
#         for declarator in node.children:
#             if declarator.type != "variable_declarator":
#                 continue
#             name_node  = declarator.child_by_field_name("name")
#             value_node = declarator.child_by_field_name("value")
#             if name_node is None or value_node is None:
#                 continue
#             if self._is_require_call(value_node):
#                 continue
#             name = self.node_text(name_node, source).strip()
#             if not name or name == "{":
#                 continue
#                 self._handle_arrow(value_node, file_path, repo_id, source, result,
#                                    name=name, parent_id=parent_id, exported=True,
#                                    line_override=node.start_point[0] + 1)

#             elif value_node.type in _FUNCTION_TYPES:
#                 self._handle_function(value_node, file_path, repo_id, source, result,
#                                       parent_class=None, parent_id=parent_id,
#                                       exported=True, override_name=name)

#             elif value_node.type == "call_expression":
#                 inner = self._unwrap_component_call(value_node, source)
#                 if inner is not None:
#                     if inner.type in _ARROW_TYPES:
#                         self._handle_arrow(inner, file_path, repo_id, source, result,
#                                            name=name, parent_id=parent_id, exported=True,
#                                            line_override=node.start_point[0] + 1)
#                     elif inner.type in _FUNCTION_TYPES:
#                         self._handle_function(inner, file_path, repo_id, source, result,
#                                               parent_class=None, parent_id=parent_id,
#                                               exported=True, override_name=name)
#                     else:
#                         self._emit_component_stub(name, file_path, repo_id, source,
#                                                    node, result, parent_id, exported=True)
#                 else:
#                     self._emit_component_stub(name, file_path, repo_id, source,
#                                                node, result, parent_id, exported=True)

#     def _handle_wrapped_component(self, call_node, file_path, repo_id, source,
#                                    result, parent_id) -> None:
    
#         inner = self._unwrap_component_call(call_node, source)
#         if inner is None:
#             return

#         if inner.type in _ARROW_TYPES:
#             self._handle_arrow(inner, file_path, repo_id, source, result,
#                                name="<default>", parent_id=parent_id, exported=True,
#                                line_override=call_node.start_point[0] + 1)

#         elif inner.type in _FUNCTION_TYPES:
#             fn_name_node = inner.child_by_field_name("name")
#             name = self.node_text(fn_name_node, source).strip() if fn_name_node else "<default>"
#             self._handle_function(inner, file_path, repo_id, source, result,
#                                   parent_class=None, parent_id=parent_id,
#                                   exported=True, override_name=name)

#         elif inner.type == "identifier":
#             name = self.node_text(inner, source).strip()
#             for n in result.nodes:
#                 if n.name == name and n.file_path == file_path:
#                     n.is_exported = True

#     def _unwrap_component_call(self, call_node, source: bytes):
    
#         args = call_node.child_by_field_name("arguments")
#         if args is None:
#             return None

#         arg_nodes = [c for c in args.children
#                      if c.type not in (",", "(", ")", "comment")]
#         if not arg_nodes:
#             return None

#         first_arg = arg_nodes[0]

#         if first_arg.type in _ARROW_TYPES | _FUNCTION_TYPES:
#             return first_arg

#         if first_arg.type == "identifier":
#             return first_arg

#         if first_arg.type == "call_expression":
#             return self._unwrap_component_call(first_arg, source)

#         func = call_node.child_by_field_name("function")
#         if func and func.type == "call_expression":
#             if first_arg.type in _ARROW_TYPES | _FUNCTION_TYPES | {"identifier"}:
#                 return first_arg

#         return None

#     def _emit_component_stub(self, name, file_path, repo_id, source,
#                               decl_node, result, parent_id, exported=True) -> None:
#         lang    = self._resolve_lang(file_path)
#         node_id = self.make_node_id(repo_id, file_path, name, decl_node.start_point[0] + 1)
#         result.nodes.append(IRNode(
#             id=node_id, name=name, kind=NodeKind.FUNCTION,
#             file_path=file_path,
#             start_line=decl_node.start_point[0] + 1,
#             end_line=decl_node.end_point[0] + 1,
#             start_col=decl_node.start_point[1],
#             end_col=decl_node.end_point[1],
#             language=lang, parent_id=parent_id,
#             signature=self.node_text(decl_node, source)[:120].split("\n")[0],
#             is_exported=exported,
#         ))


#     def _handle_expr_statement(self, node, file_path, repo_id, source,
#                                result, parent_id=None) -> None:
#         for child in node.children:
#             if child.type != "assignment_expression":
#                 continue

#             left  = child.child_by_field_name("left")
#             right = child.child_by_field_name("right")
#             if left is None or right is None:
#                 continue

#             left_text = self.node_text(left, source)

#             if left_text.startswith("exports.") and "." in left_text:
#                 export_name = left_text.split(".", 1)[1].strip()
#                 if not export_name:
#                     continue

#                 rnode = right
#                 if rnode.type == "await_expression":
#                     rnode = rnode.children[-1] if rnode.children else rnode

#                 if rnode.type in _ARROW_TYPES:
#                     self._handle_arrow(rnode, file_path, repo_id, source, result,
#                                        name=export_name, parent_id=parent_id,
#                                        exported=True,
#                                        line_override=node.start_point[0] + 1)
#                 elif rnode.type in _FUNCTION_TYPES:
#                     self._handle_function(rnode, file_path, repo_id, source, result,
#                                           parent_class=None, parent_id=parent_id,
#                                           exported=True, override_name=export_name)

#             elif "module.exports" in left_text:
#                 name = None
#                 if right.type == "identifier":
#                     export_name = self.node_text(right, source).strip()
#                     for n in result.nodes:
#                         if n.name == export_name and n.file_path == file_path:
#                             n.is_exported = True
#                 if left_text.count(".") >= 2:
#                     name = left_text.rsplit(".", 1)[-1].strip() or None

#                 if right.type in _ARROW_TYPES:
#                     self._handle_arrow(right, file_path, repo_id, source, result,
#                                        name=name or "<anonymous>", parent_id=parent_id,
#                                        exported=True,
#                                        line_override=node.start_point[0] + 1)
#                 elif right.type in _FUNCTION_TYPES:
#                     self._handle_function(right, file_path, repo_id, source, result,
#                                           parent_class=None, parent_id=parent_id,
#                                           exported=True,
#                                           override_name=name)
#                 elif right.type in _CLASS_TYPES:
#                     self._handle_class(right, file_path, repo_id, source, result,
#                                        parent_id=parent_id, exported=True)
#         for call_node in self.find_all(node, "call_expression"):
#             callee = self._callee_name(call_node, source)
#             if callee:
#                result.call_edges.append(CallEdge(
#                     caller_id=parent_id,   
#                     callee_name=callee,
#                     file_path=file_path,
#                     line_number=call_node.start_point[0] + 1,
#                     col_number=call_node.start_point[1],
#                 ))


#     def _emit_require_nodes(self, node, file_path, repo_id, source,
#                             result, module_id, lang) -> None:
     
#         for declarator in node.children:
#             if declarator.type != "variable_declarator":
#                 continue
#             name_node  = declarator.child_by_field_name("name")
#             value_node = declarator.child_by_field_name("value")
#             if name_node is None or value_node is None:
#                 continue
#             if not self._is_require_call(value_node):
#                 continue

#             target  = self._require_target(value_node, source)
#             imp_str = self.node_text(node, source).strip()

#             if name_node.type == "object_pattern":
#                 imp_name = target or self.node_text(name_node, source)
#             else:
#                 imp_name = self.node_text(name_node, source)

#             imp_id = self.make_node_id(repo_id, file_path, imp_name[:40],
#                                        node.start_point[0] + 1)
#             result.nodes.append(IRNode(
#                 id=imp_id, name=imp_name, kind=NodeKind.REQUIRE,
#                 file_path=file_path,
#                 start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
#                 start_col=node.start_point[1], end_col=node.end_point[1],
#                 language=lang, parent_id=module_id,
#                 imports=[imp_str],
#             ))
#             if target:
#                 result.import_edges.append(ImportEdge(
#                     source_file=file_path, target_module=target,
#                     line_number=node.start_point[0] + 1,
#                 ))


#     def _resolve_lang(self, file_path: str) -> str:
#         ext = file_path.rsplit(".", 1)[-1].lower()
#         return "typescript" if ext in ("ts", "tsx") else "javascript"

#     def _callee_name(self, call_node: ts.Node, source: bytes) -> Optional[str]:
#         func = call_node.child_by_field_name("function")
#         if func is None:
#             return None
#         raw = self.node_text(func, source).strip()
#         if raw == "require":
#             return None
#         leaf = raw.split(".")[-1].strip()
#         if not leaf or leaf in _NOISY_CALLEES:
#             return None
#         return raw  
    
#     def _is_require_call(self, node: ts.Node) -> bool:
#         if node.type != "call_expression":
#             return False
#         func = node.child_by_field_name("function")
#         return func is not None and func.type == "identifier" and func.text == b"require"

#     def _is_chained_require(self, node: ts.Node, source: bytes) -> bool:
#         if node.type != "call_expression":
#             return False
#         func = node.child_by_field_name("function")
#         if func and func.type == "member_expression":
#             obj = func.child_by_field_name("object")
#             if obj and self._is_require_call(obj):
#                 return True
#         return False

#     def _chained_require_target(self, node: ts.Node, source: bytes) -> Optional[str]:
#         func = node.child_by_field_name("function")
#         if func:
#             obj = func.child_by_field_name("object")
#             if obj:
#                 return self._require_target(obj, source)
#         return None

#     def _require_target(self, node: ts.Node, source: bytes) -> Optional[str]:
#         args = node.child_by_field_name("arguments")
#         if args:
#             for child in args.children:
#                 if child.type == "string":
#                     raw = self.node_text(child, source).strip("'\"`")
#                     return raw or None
#         return None

#     def _extract_require_strings(self, var_decl_node: ts.Node, source: bytes) -> list[str]:
#         result = []
#         for declarator in var_decl_node.children:
#             if declarator.type != "variable_declarator":
#                 continue
#             value_node = declarator.child_by_field_name("value")
#             if value_node and self._is_require_call(value_node):
#                 result.append(self.node_text(var_decl_node, source).strip())
#         return result

#     def _extract_typed_params(self, node: ts.Node, source: bytes) -> list[Parameter]:
#         params: list[Parameter] = []
#         params_node = (node.child_by_field_name("parameters")
#                        or node.child_by_field_name("parameter"))
#         if params_node is None:
#             return params
#         for child in params_node.children:
#             ct = child.type
#             if ct == "identifier":
#                 params.append(Parameter(name=self.node_text(child, source)))

#             elif ct in ("required_parameter", "optional_parameter"):
#                 id_node  = self.find_first(child, "identifier")
#                 typ_node = child.child_by_field_name("type")
#                 if id_node:
#                     typ = self.node_text(typ_node, source).lstrip(":").strip() if typ_node else None
#                     params.append(Parameter(name=self.node_text(id_node, source), type=typ))

#             elif ct in ("rest_parameter", "assignment_pattern"):
#                 id_node = self.find_first(child, "identifier")
#                 if id_node:
#                     params.append(Parameter(name=self.node_text(id_node, source)))

#             elif ct == "object_pattern":
#                 pattern_text = self.node_text(child, source).strip()
#                 params.append(Parameter(name=pattern_text, type="object"))

#             elif ct == "array_pattern":
#                 pattern_text = self.node_text(child, source).strip()
#                 params.append(Parameter(name=pattern_text, type="array"))

#         return params

#     def _extract_return_type(self, node: ts.Node, source: bytes) -> Optional[str]:
#         ret = node.child_by_field_name("return_type")
#         if ret:
#             return self.node_text(ret, source).lstrip(":").strip()
#         return None

#     def _extract_calls(self, node: ts.Node, source: bytes) -> list[str]:
    
#         calls: list[str] = []
#         body = node.child_by_field_name("body")
#         if body is None:
#             return calls

#         _NESTED_FN = _ARROW_TYPES | _FUNCTION_TYPES
#         stack = list(body.children)
#         while stack:
#             n = stack.pop()
#             if n.type == "call_expression":
#                 callee = self._callee_name(n, source)
#                 if callee:
#                     calls.append(callee)
#                 if callee in ("useEffect", "useCallback", "useMemo"):
#                     args = n.child_by_field_name("arguments")
#                     if args:
#                         for nested_call in self.find_all(args, "call_expression"):
#                                 inner_callee = self._callee_name(nested_call, source)
#                                 if inner_callee:
#                                     calls.append(inner_callee)
#                 for child in n.children:
#                     if child.type not in _NESTED_FN:
#                         stack.append(child)
#             elif n.type not in _NESTED_FN:
#                 stack.extend(n.children)

#         return list(dict.fromkeys(calls))

#     def _extract_references(self, node: ts.Node, source: bytes) -> list[str]:
#         refs: set[str] = set()
#         body = node.child_by_field_name("body")
#         search_root = body if (body and body.type == "statement_block") else node

#         def _collect(n: ts.Node) -> None:
#             t = n.type

#             if t == "jsx_expression":
#                 for child in self.find_all(n, "identifier", "call_expression"):
#                     if child.type == "identifier":
#                         refs.add(self.node_text(child, source).strip())
#                     elif child.type == "call_expression":
#                         callee = self._callee_name(child, source)
#                         if callee:
#                             refs.add(callee.split(".")[-1].strip())

#             elif t == "jsx_opening_element":
#                 name_node = n.child_by_field_name("name")
#                 if name_node:
#                     for ident in self.find_all(name_node, "identifier"):
#                         raw = self.node_text(ident, source).strip()
#                         if raw and raw[0].isupper():
#                             refs.add(raw)
#                 # Also capture component names in JSX attributes:
#                 # <Route element={<Login />} />  →  Login
#                 # <Suspense fallback={<Spinner />} />  →  Spinner
#                 for attr in self.find_all(n, "jsx_attribute"):
#                     attr_val = attr.child_by_field_name("value")
#                     if attr_val is None:
#                         continue
#                     # value is a JSX expression container: {<Login />}
#                     for jsx_elem in self.find_all(attr_val,
#                                                    "jsx_element",
#                                                    "jsx_self_closing_element"):
#                         # get the opening tag name
#                         open_tag = (
#                             jsx_elem.child_by_field_name("open_tag")
#                             or jsx_elem  # self-closing
#                         )
#                         tag_name_node = open_tag.child_by_field_name("name")
#                         if tag_name_node:
#                             raw = self.node_text(tag_name_node, source).strip()
#                             if raw and raw[0].isupper():
#                                 refs.add(raw)

#             elif t == "jsx_self_closing_element":
#                 name_node = n.child_by_field_name("name")
#                 if name_node:
#                     raw = self.node_text(name_node, source).strip()
#                     if raw and raw[0].isupper():
#                         refs.add(raw)
#                 # Same attribute scan for self-closing elements
#                 for attr in self.find_all(n, "jsx_attribute"):
#                     attr_val = attr.child_by_field_name("value")
#                     if attr_val is None:
#                         continue
#                     for jsx_elem in self.find_all(attr_val,
#                                                    "jsx_element",
#                                                    "jsx_self_closing_element"):
#                         open_tag = (
#                             jsx_elem.child_by_field_name("open_tag")
#                             or jsx_elem
#                         )
#                         tag_name_node = open_tag.child_by_field_name("name")
#                         if tag_name_node:
#                             raw = self.node_text(tag_name_node, source).strip()
#                             if raw and raw[0].isupper():
#                                 refs.add(raw)

#             elif t == "arguments":
#                 for ident in self.find_all(n, "identifier"):
#                     refs.add(self.node_text(ident, source).strip())
#                 for call in self.find_all(n, "call_expression"):
#                     callee = self._callee_name(call, source)
#                     if callee:
#                         refs.add(callee.split(".")[-1].strip())

#             elif t in ("array", "pair", "return_statement", "ternary_expression", "variable_declarator"):
#                 for ident in self.find_all(n, "identifier"):
#                     if t == "pair" and ident == n.child_by_field_name("key"):
#                         continue
#                     refs.add(self.node_text(ident, source).strip())
#             _NESTED_FN = _ARROW_TYPES | _FUNCTION_TYPES
#             for child in n.children:
#                 if child.type not in _NESTED_FN:
#                     _collect(child)

#         _collect(search_root)
#         _SKIP = frozenset({
#             "true", "false", "null", "undefined", "this", "super",
#             "arguments", "void", "typeof", "instanceof", "new",
#             "return", "if", "else", "for", "while", "do", "switch",
#             "case", "break", "continue", "throw", "try", "catch", "finally",
#             "const", "let", "var", "function", "class", "import", "export",
#             "default", "from", "of", "in", "async", "await", "yield",
#             "static", "extends", "implements", "interface",
#             "type", "enum", "namespace", "module", "declare",
#         })
#         return [r for r in refs if len(r) > 1 and r not in _SKIP]    
#     def _handle_type_alias(self, node, file_path, repo_id, source, result, parent_id) -> None:
#         lang = self._resolve_lang(file_path)
#         name_node = node.child_by_field_name("name")
#         if not name_node:
#             return
#         name        = self.node_text(name_node, source)
#         type_params = self._extract_ts_type_params(node, source)
#         value_node  = node.child_by_field_name("value")
#         value_text  = self.node_text(value_node, source).strip() if value_node else None
#         node_id     = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
#         result.nodes.append(IRNode(
#             id=node_id, name=name, kind=NodeKind.TYPE_ANNOTATION,
#             file_path=file_path,
#             start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
#             start_col=node.start_point[1], end_col=node.end_point[1],
#             language=lang, parent_id=parent_id,
#             value=value_text,
#             signature=f"type {name}{type_params} = {value_text or ''}".strip(),
#         ))

#     def _extract_ts_type_params(self, node, source: bytes) -> str:
#         tp = node.child_by_field_name("type_parameters")
#         if tp:
#             return self.node_text(tp, source).strip()
#         return ""

#     def _extract_ts_decorators(self, node, source: bytes) -> list[str]:
#         decorators: list[str] = []
#         for child in node.children:
#             if child.type == "decorator":
#                 decorators.append(self.node_text(child, source).strip())
#             elif child.type not in ("comment", "\n"):
#                 break 
#         return decorators



# def _parse_es_import_target(imp_str: str) -> Optional[str]:
#     m = re.search(r"""from\s+['"]([^'"]+)['"]""", imp_str)
#     if not m:
#         return None
#     raw = m.group(1)
#     if raw.startswith(".") or raw.startswith("/"):
#         return re.sub(r"\.\w+$", "", raw) or None
#     else:
#         return raw.split("/")[0].lower() or None


# def _link_children(nodes: list[IRNode]) -> None:
#     id_map = {n.id: n for n in nodes}
#     for node in nodes:
#         if node.parent_id and node.parent_id in id_map:
#             parent = id_map[node.parent_id]
#             if node.id not in parent.children:
#                 parent.children.append(node.id)


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

        module_id = self.make_node_id(repo_id, file_path, "__module__", 1)
        module_imports: list[str] = []
        module_calls = []
        module_refs = []

        # Collect module-level calls and refs from TOP-LEVEL scope only.
        # Do NOT use find_all(root, ...) — that recurses into every function
        # body and pollutes module_calls/module_refs with inner function names,
        # creating false CALLS edges from the module entry point to everything.
        def _walk_toplevel_calls(node):
            _STOP = _FUNCTION_TYPES | _ARROW_TYPES | _CLASS_TYPES | {
                "method_definition"
            }
            for child in node.children:
                if child.type in _STOP:
                    continue  # do not descend into function/class bodies
                if child.type == "call_expression":
                    callee = self._callee_name(child, source_bytes)
                    if self._is_require_call(child):
                        target = self._require_target(child, source_bytes)
                        if target:
                            module_imports.append(target)
                    if callee:
                        module_calls.append(callee)
                    args = child.child_by_field_name("arguments")
                    if args:
                        for arg in args.children:
                            if arg.type == "identifier":
                                module_refs.append(
                                    self.node_text(arg, source_bytes).strip()
                                )
                    _walk_toplevel_calls(child)
                else:
                    _walk_toplevel_calls(child)

        _walk_toplevel_calls(root)

        for node in root.children:
            if node.type == "import_statement":
                module_imports.append(self.node_text(node, source_bytes).strip())
            elif node.type in _VAR_DECL_TYPES:
                module_imports.extend(self._extract_require_strings(node, source_bytes))
                for declarator in node.children:
                    if declarator.type != "variable_declarator":
                        continue
                    val = declarator.child_by_field_name("value")
                    if val is not None and val.type == "array":
                        for element in val.children:
                            if element.type == "identifier":
                                text = self.node_text(element, source_bytes).strip()
                                if text:
                                    module_refs.append(text)

        result.nodes.append(IRNode(
            id=module_id,
            name=file_path,
            kind=NodeKind.MODULE,
            file_path=file_path,
            start_line=1,
            end_line=root.end_point[0] + 1,
            language=lang,
            imports=module_imports,
            calls=module_calls,
            references=module_refs,
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
                    imp_id = self.make_node_id(repo_id, file_path, raw[:40], node.start_point[0] + 1)
                    
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

        for call in self.find_all(root, "call_expression"):
            args_node = call.child_by_field_name("arguments")
            if args_node:
                for arg in args_node.children:
                    if arg.type == "call_expression" and self._is_require_call(arg):
                        raw_req = self.node_text(arg, source_bytes).strip()
                        target_req = self._require_target(arg, source_bytes)
                        req_id = self.make_node_id(repo_id, file_path, raw_req[:40], arg.start_point[0] + 1)

                        result.nodes.append(IRNode(
                            id=req_id,
                            name=raw_req,
                            kind=NodeKind.REQUIRE,
                            file_path=file_path,
                            start_line=arg.start_point[0] + 1,
                            end_line=arg.end_point[0] + 1,
                            start_col=arg.start_point[1],
                            end_col=arg.end_point[1],
                            language=lang,
                            parent_id=module_id,
                            imports=[raw_req],
                        ))

                        if target_req:
                            result.import_edges.append(ImportEdge(
                                source_file=file_path,
                                target_module=target_req,
                                line_number=arg.start_point[0] + 1,
                            ))

        for node in root.children:
            if node.type == "interface_declaration":
                self._handle_interface(node, file_path, repo_id, source_bytes, result, module_id)
            elif node.type == "enum_declaration":
                self._handle_enum(node, file_path, repo_id, source_bytes, result, module_id)
            elif node.type == "type_alias_declaration":
                self._handle_type_alias(node, file_path, repo_id, source_bytes, result, module_id)

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
            for ident in self.find_all(heritage, "type_identifier", "identifier",
                                        "member_expression"):
                bases.append(self.node_text(ident, source).strip())
                break

        type_params = self._extract_ts_type_params(node, source)
        decorators  = self._extract_ts_decorators(node, source)

        node_id = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
        base_sig = f"class {name}{type_params}"
        if bases:
            base_sig += f" extends {bases[0]}"
        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.CLASS,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language=lang, parent_id=parent_id,
            bases=bases, decorators=decorators,
            signature=base_sig, is_exported=exported,
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
        name = self.node_text(name_node, source)

        type_params = self._extract_ts_type_params(node, source)

        bases: list[str] = []
        extends = node.child_by_field_name("extends")
        if extends:
            for ident in self.find_all(extends, "type_identifier", "identifier"):
                bases.append(self.node_text(ident, source).strip())

        node_id = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.INTERFACE,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language=lang, parent_id=parent_id, bases=bases,
            signature=f"interface {name}{type_params}" + (f" extends {', '.join(bases)}" if bases else ""),
        ))
        for base in bases:
            result.inheritance_edges.append(InheritanceEdge(
                child_id=node_id, parent_name=base, kind="inherits",
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
        lang = self._resolve_lang(file_path)
        name_node = node.child_by_field_name("name")
        name = override_name or (self.node_text(name_node, source) if name_node else "<anonymous>")
        kind = NodeKind.METHOD if parent_class else NodeKind.FUNCTION

        typed_params = self._extract_typed_params(node, source)
        calls        = self._extract_calls(node, source)
        refs         = self._extract_references(node, source)
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
            calls=calls, references=refs, is_exported=exported,
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
            if body.type == "statement_block":
                self._walk_statements(body.children, file_path, repo_id, source, result,
                                      parent_class=parent_class, parent_id=node_id)
        return node_id


    def _handle_arrow(self, node, file_path, repo_id, source, result,
                      name: str, parent_class=None, parent_id=None,
                      exported=False, line_override: Optional[int] = None) -> Optional[str]:
        lang = self._resolve_lang(file_path)
        kind = NodeKind.LAMBDA if parent_class else NodeKind.FUNCTION

        typed_params = self._extract_typed_params(node, source)
        calls        = self._extract_calls(node, source)
        refs         = self._extract_references(node, source)
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
            calls=calls, references=refs, is_exported=exported,
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
        if body and body.type == "statement_block":
            self._walk_statements(body.children, file_path, repo_id, source, result,
                                  parent_class=parent_class, parent_id=node_id)
        return node_id


    def _handle_var_decl(self, node, file_path, repo_id, source, result,
                         parent_class=None, parent_id=None, exported=False) -> None:
        for declarator in node.children:
            if declarator.type != "variable_declarator":
                continue
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
            elif value_node.type == "array":
                lang    = self._resolve_lang(file_path)
                node_id = self.make_node_id(repo_id, file_path, name,
                                            node.start_point[0] + 1)

                _SKIP_IDENTS = frozenset({
                    "true", "false", "null", "undefined", "this",
                    "const", "let", "var",
                })
                array_refs: list[str] = []
                for element in value_node.children:
                    if element.type == "identifier":
                        text = self.node_text(element, source).strip()
                        if text and text not in _SKIP_IDENTS:
                            array_refs.append(text)

                result.nodes.append(IRNode(
                    id=node_id, name=name, kind=NodeKind.ASSIGNMENT,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                    start_col=node.start_point[1],       end_col=node.end_point[1],
                    language=lang, parent_id=parent_id,
                    signature=self.first_line(node, source),
                    references=array_refs,
                    is_exported=exported,
                ))


    def _handle_export(self, node, file_path, repo_id, source, result, parent_id=None) -> None:
  
        exported_names: list[str] = []

        for child in node.children:
            if child.type in _CLASS_TYPES:
                self._handle_class(child, file_path, repo_id, source, result,
                                   parent_id=parent_id, exported=True)

            elif child.type in _FUNCTION_TYPES:
                self._handle_function(child, file_path, repo_id, source, result,
                                      parent_class=None, parent_id=parent_id, exported=True)

            elif child.type in _VAR_DECL_TYPES:
                self._handle_var_decl_exported(child, file_path, repo_id, source, result,
                                               parent_id=parent_id)

            elif child.type == "interface_declaration":
                self._handle_interface(child, file_path, repo_id, source, result, parent_id)

            elif child.type == "enum_declaration":
                self._handle_enum(child, file_path, repo_id, source, result, parent_id)

            elif child.type == "identifier":
                name = self.node_text(child, source).strip()
                if name and name not in ("default",):
                    exported_names.append(name)

            elif child.type == "call_expression":
                self._handle_wrapped_component(child, file_path, repo_id, source,
                                               result, parent_id)

            elif child.type == "type_alias_declaration":
                self._handle_type_alias(child, file_path, repo_id, source, result, parent_id)

        if exported_names:
            for n in result.nodes:
                if n.name in exported_names and n.file_path == file_path:
                    n.is_exported = True

    def _handle_var_decl_exported(self, node, file_path, repo_id, source,
                                   result, parent_id=None) -> None:
        for declarator in node.children:
            if declarator.type != "variable_declarator":
                continue
            name_node  = declarator.child_by_field_name("name")
            value_node = declarator.child_by_field_name("value")
            if name_node is None or value_node is None:
                continue
            if self._is_require_call(value_node):
                continue
            name = self.node_text(name_node, source).strip()
            if not name or name == "{":
                continue
                self._handle_arrow(value_node, file_path, repo_id, source, result,
                                   name=name, parent_id=parent_id, exported=True,
                                   line_override=node.start_point[0] + 1)

            elif value_node.type in _FUNCTION_TYPES:
                self._handle_function(value_node, file_path, repo_id, source, result,
                                      parent_class=None, parent_id=parent_id,
                                      exported=True, override_name=name)

            elif value_node.type == "call_expression":
                inner = self._unwrap_component_call(value_node, source)
                if inner is not None:
                    if inner.type in _ARROW_TYPES:
                        self._handle_arrow(inner, file_path, repo_id, source, result,
                                           name=name, parent_id=parent_id, exported=True,
                                           line_override=node.start_point[0] + 1)
                    elif inner.type in _FUNCTION_TYPES:
                        self._handle_function(inner, file_path, repo_id, source, result,
                                              parent_class=None, parent_id=parent_id,
                                              exported=True, override_name=name)
                    else:
                        self._emit_component_stub(name, file_path, repo_id, source,
                                                   node, result, parent_id, exported=True)
                else:
                    self._emit_component_stub(name, file_path, repo_id, source,
                                               node, result, parent_id, exported=True)

    def _handle_wrapped_component(self, call_node, file_path, repo_id, source,
                                   result, parent_id) -> None:
    
        inner = self._unwrap_component_call(call_node, source)
        if inner is None:
            return

        if inner.type in _ARROW_TYPES:
            self._handle_arrow(inner, file_path, repo_id, source, result,
                               name="<default>", parent_id=parent_id, exported=True,
                               line_override=call_node.start_point[0] + 1)

        elif inner.type in _FUNCTION_TYPES:
            fn_name_node = inner.child_by_field_name("name")
            name = self.node_text(fn_name_node, source).strip() if fn_name_node else "<default>"
            self._handle_function(inner, file_path, repo_id, source, result,
                                  parent_class=None, parent_id=parent_id,
                                  exported=True, override_name=name)

        elif inner.type == "identifier":
            name = self.node_text(inner, source).strip()
            for n in result.nodes:
                if n.name == name and n.file_path == file_path:
                    n.is_exported = True

    def _unwrap_component_call(self, call_node, source: bytes):
    
        args = call_node.child_by_field_name("arguments")
        if args is None:
            return None

        arg_nodes = [c for c in args.children
                     if c.type not in (",", "(", ")", "comment")]
        if not arg_nodes:
            return None

        first_arg = arg_nodes[0]

        if first_arg.type in _ARROW_TYPES | _FUNCTION_TYPES:
            return first_arg

        if first_arg.type == "identifier":
            return first_arg

        if first_arg.type == "call_expression":
            return self._unwrap_component_call(first_arg, source)

        func = call_node.child_by_field_name("function")
        if func and func.type == "call_expression":
            if first_arg.type in _ARROW_TYPES | _FUNCTION_TYPES | {"identifier"}:
                return first_arg

        return None

    def _emit_component_stub(self, name, file_path, repo_id, source,
                              decl_node, result, parent_id, exported=True) -> None:
        lang    = self._resolve_lang(file_path)
        node_id = self.make_node_id(repo_id, file_path, name, decl_node.start_point[0] + 1)
        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.FUNCTION,
            file_path=file_path,
            start_line=decl_node.start_point[0] + 1,
            end_line=decl_node.end_point[0] + 1,
            start_col=decl_node.start_point[1],
            end_col=decl_node.end_point[1],
            language=lang, parent_id=parent_id,
            signature=self.node_text(decl_node, source)[:120].split("\n")[0],
            is_exported=exported,
        ))


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
                if right.type == "identifier":
                    export_name = self.node_text(right, source).strip()
                    for n in result.nodes:
                        if n.name == export_name and n.file_path == file_path:
                            n.is_exported = True
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
        for call_node in self.find_all(node, "call_expression"):
            callee = self._callee_name(call_node, source)
            if callee:
               result.call_edges.append(CallEdge(
                    caller_id=parent_id,   
                    callee_name=callee,
                    file_path=file_path,
                    line_number=call_node.start_point[0] + 1,
                    col_number=call_node.start_point[1],
                ))


    def _emit_require_nodes(self, node, file_path, repo_id, source,
                            result, module_id, lang) -> None:
     
        for declarator in node.children:
            if declarator.type != "variable_declarator":
                continue
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
        result = []
        for declarator in var_decl_node.children:
            if declarator.type != "variable_declarator":
                continue
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

            elif ct == "object_pattern":
                pattern_text = self.node_text(child, source).strip()
                params.append(Parameter(name=pattern_text, type="object"))

            elif ct == "array_pattern":
                pattern_text = self.node_text(child, source).strip()
                params.append(Parameter(name=pattern_text, type="array"))

        return params

    def _extract_return_type(self, node: ts.Node, source: bytes) -> Optional[str]:
        ret = node.child_by_field_name("return_type")
        if ret:
            return self.node_text(ret, source).lstrip(":").strip()
        return None

    def _extract_calls(self, node: ts.Node, source: bytes) -> list[str]:
    
        calls: list[str] = []
        body = node.child_by_field_name("body")
        if body is None:
            return calls

        _NESTED_FN = _ARROW_TYPES | _FUNCTION_TYPES
        stack = list(body.children)
        while stack:
            n = stack.pop()
            if n.type == "call_expression":
                callee = self._callee_name(n, source)
                if callee:
                    calls.append(callee)
                if callee in ("useEffect", "useCallback", "useMemo"):
                    args = n.child_by_field_name("arguments")
                    if args:
                        for nested_call in self.find_all(args, "call_expression"):
                                inner_callee = self._callee_name(nested_call, source)
                                if inner_callee:
                                    calls.append(inner_callee)
                for child in n.children:
                    if child.type not in _NESTED_FN:
                        stack.append(child)
            elif n.type not in _NESTED_FN:
                stack.extend(n.children)

        return list(dict.fromkeys(calls))

    def _extract_references(self, node: ts.Node, source: bytes) -> list[str]:
        refs: set[str] = set()
        body = node.child_by_field_name("body")
        search_root = body if (body and body.type == "statement_block") else node

        def _collect(n: ts.Node) -> None:
            t = n.type

            if t == "jsx_expression":
                for child in self.find_all(n, "identifier", "call_expression"):
                    if child.type == "identifier":
                        refs.add(self.node_text(child, source).strip())
                    elif child.type == "call_expression":
                        callee = self._callee_name(child, source)
                        if callee:
                            refs.add(callee.split(".")[-1].strip())

            elif t == "jsx_opening_element":
                name_node = n.child_by_field_name("name")
                if name_node:
                    for ident in self.find_all(name_node, "identifier"):
                        raw = self.node_text(ident, source).strip()
                        if raw and raw[0].isupper():
                            refs.add(raw)
                # Also capture component names in JSX attributes:
                # <Route element={<Login />} />  →  Login
                # <Suspense fallback={<Spinner />} />  →  Spinner
                for attr in self.find_all(n, "jsx_attribute"):
                    attr_val = attr.child_by_field_name("value")
                    if attr_val is None:
                        continue
                    # value is a JSX expression container: {<Login />}
                    for jsx_elem in self.find_all(attr_val,
                                                   "jsx_element",
                                                   "jsx_self_closing_element"):
                        # get the opening tag name
                        open_tag = (
                            jsx_elem.child_by_field_name("open_tag")
                            or jsx_elem  # self-closing
                        )
                        tag_name_node = open_tag.child_by_field_name("name")
                        if tag_name_node:
                            raw = self.node_text(tag_name_node, source).strip()
                            if raw and raw[0].isupper():
                                refs.add(raw)

            elif t == "jsx_self_closing_element":
                name_node = n.child_by_field_name("name")
                if name_node:
                    raw = self.node_text(name_node, source).strip()
                    if raw and raw[0].isupper():
                        refs.add(raw)
                # Same attribute scan for self-closing elements
                for attr in self.find_all(n, "jsx_attribute"):
                    attr_val = attr.child_by_field_name("value")
                    if attr_val is None:
                        continue
                    for jsx_elem in self.find_all(attr_val,
                                                   "jsx_element",
                                                   "jsx_self_closing_element"):
                        open_tag = (
                            jsx_elem.child_by_field_name("open_tag")
                            or jsx_elem
                        )
                        tag_name_node = open_tag.child_by_field_name("name")
                        if tag_name_node:
                            raw = self.node_text(tag_name_node, source).strip()
                            if raw and raw[0].isupper():
                                refs.add(raw)

            elif t == "arguments":
                for ident in self.find_all(n, "identifier"):
                    refs.add(self.node_text(ident, source).strip())
                for call in self.find_all(n, "call_expression"):
                    callee = self._callee_name(call, source)
                    if callee:
                        refs.add(callee.split(".")[-1].strip())

            elif t in ("array", "pair", "return_statement", "ternary_expression", "variable_declarator"):
                for ident in self.find_all(n, "identifier"):
                    if t == "pair" and ident == n.child_by_field_name("key"):
                        continue
                    refs.add(self.node_text(ident, source).strip())
            _NESTED_FN = _ARROW_TYPES | _FUNCTION_TYPES
            for child in n.children:
                if child.type not in _NESTED_FN:
                    _collect(child)

        _collect(search_root)
        _SKIP = frozenset({
            "true", "false", "null", "undefined", "this", "super",
            "arguments", "void", "typeof", "instanceof", "new",
            "return", "if", "else", "for", "while", "do", "switch",
            "case", "break", "continue", "throw", "try", "catch", "finally",
            "const", "let", "var", "function", "class", "import", "export",
            "default", "from", "of", "in", "async", "await", "yield",
            "static", "extends", "implements", "interface",
            "type", "enum", "namespace", "module", "declare",
        })
        return [r for r in refs if len(r) > 1 and r not in _SKIP]    
    def _handle_type_alias(self, node, file_path, repo_id, source, result, parent_id) -> None:
        lang = self._resolve_lang(file_path)
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name        = self.node_text(name_node, source)
        type_params = self._extract_ts_type_params(node, source)
        value_node  = node.child_by_field_name("value")
        value_text  = self.node_text(value_node, source).strip() if value_node else None
        node_id     = self.make_node_id(repo_id, file_path, name, node.start_point[0] + 1)
        result.nodes.append(IRNode(
            id=node_id, name=name, kind=NodeKind.TYPE_ANNOTATION,
            file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            start_col=node.start_point[1], end_col=node.end_point[1],
            language=lang, parent_id=parent_id,
            value=value_text,
            signature=f"type {name}{type_params} = {value_text or ''}".strip(),
        ))

    def _extract_ts_type_params(self, node, source: bytes) -> str:
        tp = node.child_by_field_name("type_parameters")
        if tp:
            return self.node_text(tp, source).strip()
        return ""

    def _extract_ts_decorators(self, node, source: bytes) -> list[str]:
        decorators: list[str] = []
        for child in node.children:
            if child.type == "decorator":
                decorators.append(self.node_text(child, source).strip())
            elif child.type not in ("comment", "\n"):
                break 
        return decorators



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