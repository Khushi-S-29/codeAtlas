from __future__ import annotations

import re
import logging

from code_atlas.core.models import IRNode, NodeKind, Parameter, ParseResult
from code_atlas.parsing.visitors.base import BaseVisitor

logger = logging.getLogger(__name__)

_PY_STYLE_DEF  = re.compile(r"^[ \t]*(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)", re.M)
_JS_STYLE_FUNC = re.compile(r"(?:^|\s)function\s+(\w+)\s*\(([^)]*)\)", re.M)
_ARROW_FUNC    = re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", re.M)
_CLASS_DEF     = re.compile(r"^[ \t]*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", re.M)
_IMPORT_PY     = re.compile(r"^[ \t]*(?:import|from)\s+\S+", re.M)
_IMPORT_JS     = re.compile(r"^[ \t]*import\s+.+\s+from\s+['\"]", re.M)
_IMPORT_JAVA   = re.compile(r"^[ \t]*import\s+[\w.]+;", re.M)
_IMPORT_GO     = re.compile(r'^[ \t]*import\s+"[\w./]+"', re.M)


class GenericVisitor(BaseVisitor):
    language_name = "generic"

    def parse(self, source_code: str, file_path: str, repo_id: str) -> ParseResult:
        lang   = self._guess_language(file_path)
        result = ParseResult(file_path=file_path, language=lang)
        result.errors.append(
            f"Using generic regex visitor for {lang} — structural accuracy is limited"
        )
        lines = source_code.splitlines()

        module_id = self.make_node_id(repo_id, file_path, "__module__", 1)
        imports   = self._extract_imports(source_code, lang)

        result.nodes.append(IRNode(
            id=module_id,
            name=file_path,
            kind=NodeKind.MODULE,
            file_path=file_path,
            start_line=1,
            end_line=len(lines),
            start_col=0,
            end_col=0,
            language=lang,
            imports=imports,
        ))

        for imp in imports:
            line_no = self._find_line(lines, imp)
            col     = self._find_col(lines, line_no, imp)
            imp_id  = self.make_node_id(repo_id, file_path, imp[:40], line_no)
            result.nodes.append(IRNode(
                id=imp_id,
                name=imp,
                kind=NodeKind.IMPORT,
                file_path=file_path,
                start_line=line_no,
                end_line=line_no,
                start_col=col,
                end_col=col + len(imp),
                language=lang,
                parent_id=module_id,
                imports=[imp],
            ))

        class_ids: dict[str, str] = {}
        for m in _CLASS_DEF.finditer(source_code):
            name    = m.group(1)
            line_no = source_code[: m.start()].count("\n") + 1
            col     = len(source_code[: m.start()].rsplit("\n", 1)[-1])
            node_id = self.make_node_id(repo_id, file_path, name, line_no)
            class_ids[name] = node_id
            result.nodes.append(IRNode(
                id=node_id,
                name=name,
                kind=NodeKind.CLASS,
                file_path=file_path,
                start_line=line_no,
                end_line=line_no,
                start_col=col,
                end_col=col + len(lines[line_no - 1]) if line_no <= len(lines) else col,
                language=lang,
                parent_id=module_id,
                signature=lines[line_no - 1].strip() if line_no <= len(lines) else "",
            ))

        seen: set[str] = set()
        for pattern in (_PY_STYLE_DEF, _JS_STYLE_FUNC, _ARROW_FUNC):
            for m in pattern.finditer(source_code):
                name      = m.group(1)
                params_raw = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
                line_no   = source_code[: m.start()].count("\n") + 1
                col       = len(source_code[: m.start()].rsplit("\n", 1)[-1])
                key       = f"{name}:{line_no}"
                if key in seen:
                    continue
                seen.add(key)

                typed_params = [
                    Parameter(name=p.strip().split(":")[0].split("=")[0].strip())
                    for p in params_raw.split(",")
                    if p.strip()
                ]
                param_names = [p.name for p in typed_params]

                kind = NodeKind.CONSTRUCTOR if name in ("__init__", "constructor") else NodeKind.FUNCTION
                node_id = self.make_node_id(repo_id, file_path, name, line_no)

                result.nodes.append(IRNode(
                    id=node_id,
                    name=name,
                    kind=kind,
                    file_path=file_path,
                    start_line=line_no,
                    end_line=line_no,
                    start_col=col,
                    end_col=col + len(lines[line_no - 1]) if line_no <= len(lines) else col,
                    language=lang,
                    parent_id=module_id,
                    typed_parameters=typed_params,
                    parameters=param_names,
                    signature=lines[line_no - 1].strip() if line_no <= len(lines) else "",
                ))

        _link_children(result.nodes)
        return result

    def _extract_imports(self, source_code: str, lang: str) -> list[str]:
        imports: list[str] = []
        for pattern in (_IMPORT_PY, _IMPORT_JS, _IMPORT_JAVA, _IMPORT_GO):
            for m in pattern.finditer(source_code):
                imports.append(m.group(0).strip())
        return list(dict.fromkeys(imports))

    def _guess_language(self, file_path: str) -> str:
        return file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "unknown"

    def _find_line(self, lines: list[str], text: str) -> int:
        for i, line in enumerate(lines, 1):
            if text.strip() in line:
                return i
        return 1

    def _find_col(self, lines: list[str], line_no: int, text: str) -> int:
        if 1 <= line_no <= len(lines):
            idx = lines[line_no - 1].find(text.strip())
            return max(0, idx)
        return 0


def _link_children(nodes: list[IRNode]) -> None:
    id_map = {n.id: n for n in nodes}
    for node in nodes:
        if node.parent_id and node.parent_id in id_map:
            parent = id_map[node.parent_id]
            if node.id not in parent.children:
                parent.children.append(node.id)