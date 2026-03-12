from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from code_atlas.core.models import FileRecord, FileStatus, NodeKind


#helpers
def make_file_record(path: str, language: str) -> FileRecord:
    return FileRecord(
        path=path, language=language, sha256="test",
        size_bytes=100, last_modified=datetime.now(timezone.utc),
        status=FileStatus.NEW, line_count=10,
    )


def make_manifest(tmp_path: Path, files: list[tuple[str, str, str]]):
    """
    Create a RepoManifest + matching files on disk.
    files: list of (relative_path, language, source_code)
    """
    from code_atlas.core.models import RepoManifest, IngestionSource

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    records = []
    for rel_path, lang, code in files:
        abs_path = repo_root / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(code, encoding="utf-8")
        records.append(make_file_record(rel_path, lang))

    manifest = RepoManifest(
        repo_id="test-repo",
        source=str(repo_root),
        source_type=IngestionSource.LOCAL_PATH,
        local_path=str(repo_root),
        files=records,
    )
    return manifest, repo_root


 
# grammar_loader

class TestGrammarLoader:

    def test_unsupported_language_returns_none(self):
        from code_atlas.parsing.grammar_loader import get_language
        assert get_language("brainfuck") is None

    def test_python_grammar_loads_if_installed(self):
        from code_atlas.parsing.grammar_loader import get_language
        lang = get_language("python")
        if lang is not None:
            import tree_sitter as ts
            assert isinstance(lang, ts.Language)

    def test_supported_languages_returns_list(self):
        from code_atlas.parsing.grammar_loader import supported_languages
        langs = supported_languages()
        assert isinstance(langs, list)

    def test_get_parser_returns_none_for_unknown(self):
        from code_atlas.parsing.grammar_loader import get_parser
        assert get_parser("cobol") is None


# Python visitor

pytestmark_ts = pytest.mark.skipif(
    __import__("importlib").util.find_spec("tree_sitter_python") is None,
    reason="tree-sitter-python not installed",
)


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("tree_sitter_python") is None,
    reason="tree-sitter-python not installed",
)
class TestPythonVisitor:

    def _parse(self, code: str, path: str = "test.py") -> object:
        from code_atlas.parsing.visitors.python_visitor import PythonVisitor
        return PythonVisitor().parse(code, path, "test-repo")

    def test_extracts_module_node(self):
        result = self._parse("x = 1\n")
        modules = [n for n in result.nodes if n.kind == NodeKind.MODULE]
        assert len(modules) == 1

    def test_extracts_function(self):
        code = "def greet(name):\n    return f'Hello {name}'\n"
        result = self._parse(code)
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "greet"
        assert "name" in funcs[0].parameters

    def test_extracts_class(self):
        code = "class Dog(Animal):\n    pass\n"
        result = self._parse(code)
        classes = [n for n in result.nodes if n.kind == NodeKind.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "Dog"
        assert "Animal" in classes[0].bases

    def test_extracts_method(self):
        code = "class Foo:\n    def bar(self, x):\n        pass\n"
        result = self._parse(code)
        methods = [n for n in result.nodes if n.kind == NodeKind.METHOD]
        assert len(methods) == 1
        assert methods[0].name == "bar"
        assert methods[0].parent_class == "Foo"

    def test_extracts_import(self):
        code = "import os\nfrom pathlib import Path\n"
        result = self._parse(code)
        imports = [n for n in result.nodes if n.kind == NodeKind.IMPORT]
        assert len(imports) == 2

    def test_extracts_call_expressions(self):
        code = "def run():\n    os.path.join('a', 'b')\n    print('done')\n"
        result = self._parse(code)
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert len(funcs) == 1
        calls = funcs[0].calls
        assert any("print" in c for c in calls)

    def test_extracts_return_type_annotation(self):
        code = "def get_name() -> str:\n    return 'Alice'\n"
        result = self._parse(code)
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert funcs[0].return_type == "str"

    def test_extracts_decorator(self):
        code = "@staticmethod\ndef helper():\n    pass\n"
        result = self._parse(code)
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert len(funcs) == 1
        assert "staticmethod" in funcs[0].decorators

    def test_private_function_not_exported(self):
        code = "def _internal():\n    pass\n"
        result = self._parse(code)
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert funcs[0].is_exported is False

    def test_docstring_extraction(self):
        code = 'def foo():\n    """Does something."""\n    pass\n'
        result = self._parse(code)
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert funcs[0].docstring is not None
        assert "Does something" in funcs[0].docstring

    def test_nested_class_methods(self):
        code = (
            "class Outer:\n"
            "    class Inner:\n"
            "        def method(self):\n"
            "            pass\n"
        )
        result = self._parse(code)
        classes = [n for n in result.nodes if n.kind == NodeKind.CLASS]
        assert len(classes) == 2

    def test_parse_result_success_on_valid_code(self):
        result = self._parse("x = 1\n")
        assert result.success is True

    def test_line_numbers_correct(self):
        code = "x = 1\n\ndef foo():\n    pass\n"
        result = self._parse(code)
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert funcs[0].start_line == 3


# JavaScript visitor

@pytest.mark.skipif(
    __import__("importlib").util.find_spec("tree_sitter_javascript") is None,
    reason="tree-sitter-javascript not installed",
)
class TestJavaScriptVisitor:

    def _parse(self, code: str, path: str = "test.js") -> object:
        from code_atlas.parsing.visitors.javascript_visitor import JavaScriptVisitor
        return JavaScriptVisitor().parse(code, path, "test-repo")

    def test_extracts_function_declaration(self):
        code = "function greet(name) { return name; }\n"
        result = self._parse(code)
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert any(f.name == "greet" for f in funcs)

    def test_extracts_arrow_function(self):
        code = "const add = (a, b) => a + b;\n"
        result = self._parse(code)
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert any(f.name == "add" for f in funcs)

    def test_extracts_class(self):
        code = "class Dog extends Animal { }\n"
        result = self._parse(code)
        classes = [n for n in result.nodes if n.kind == NodeKind.CLASS]
        assert len(classes) >= 1
        assert classes[0].name == "Dog"
        assert "Animal" in classes[0].bases

    def test_extracts_method(self):
        code = "class Foo { bar(x) { return x; } }\n"
        result = self._parse(code)
        methods = [n for n in result.nodes if n.kind == NodeKind.METHOD]
        assert any(m.name == "bar" for m in methods)

    def test_extracts_import(self):
        code = "import React from 'react';\n"
        result = self._parse(code)
        imports = [n for n in result.nodes if n.kind == NodeKind.IMPORT]
        assert len(imports) >= 1

    def test_exported_function_marked(self):
        code = "export function hello() { return 'hi'; }\n"
        result = self._parse(code)
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert any(f.is_exported for f in funcs)

    def test_module_node_present(self):
        result = self._parse("const x = 1;\n")
        modules = [n for n in result.nodes if n.kind == NodeKind.MODULE]
        assert len(modules) == 1

#generic visitor
class TestGenericVisitor:

    def _parse(self, code: str, path: str = "test.rb") -> object:
        from code_atlas.parsing.visitors.generic_visitor import GenericVisitor
        return GenericVisitor().parse(code, path, "test-repo")

    def test_extracts_module_node(self):
        result = self._parse("x = 1\n")
        modules = [n for n in result.nodes if n.kind == NodeKind.MODULE]
        assert len(modules) == 1

    def test_extracts_function_via_def(self):
        code = "def hello(name):\n    pass\n"
        result = self._parse(code, "test.py")
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert any(f.name == "hello" for f in funcs)

    def test_extracts_function_via_function_keyword(self):
        code = "function greet(name) { return name; }\n"
        result = self._parse(code, "test.js")
        funcs = [n for n in result.nodes if n.kind == NodeKind.FUNCTION]
        assert any(f.name == "greet" for f in funcs)

    def test_extracts_class(self):
        code = "class MyClass extends Base {}\n"
        result = self._parse(code, "test.js")
        classes = [n for n in result.nodes if n.kind == NodeKind.CLASS]
        assert any(c.name == "MyClass" for c in classes)

    def test_always_succeeds(self):
        result = self._parse("totally invalid %%% code ###")
        assert result.success is True  

# IRStore

class TestIRStore:
    def _make_store(self, tmp_path: Path):
        from code_atlas.parsing.ir_store import IRStore
        return IRStore("test-repo", ir_dir=tmp_path)

    def _make_node(self, name: str = "foo", kind=NodeKind.FUNCTION, file_path: str = "src/a.py"):
        from code_atlas.core.models import IRNode
        return IRNode(
            id=f"test-repo:{file_path}:{name}:1",
            name=name, kind=kind, file_path=file_path,
            start_line=1, end_line=5, language="python",
        )

    def test_empty_on_first_load(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        assert store.load_all() == []

    def test_upsert_and_load(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        node = self._make_node("my_func")
        store.upsert_nodes([node])
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].name == "my_func"

    def test_load_by_file(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        n1 = self._make_node("f1", file_path="src/a.py")
        n2 = self._make_node("f2", file_path="src/b.py")
        store.upsert_nodes([n1, n2])
        result = store.load_by_file("src/a.py")
        assert len(result) == 1
        assert result[0].name == "f1"

    def test_delete_file_removes_nodes(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        store.upsert_nodes([self._make_node("f", file_path="src/a.py")])
        store.delete_file("src/a.py")
        assert store.load_by_file("src/a.py") == []

    def test_upsert_overwrites_existing(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        node = self._make_node("foo")
        store.upsert_nodes([node])
        from code_atlas.core.models import IRNode
        updated = IRNode(
            id=node.id, name="foo_updated", kind=NodeKind.FUNCTION,
            file_path="src/a.py", start_line=1, end_line=5, language="python",
        )
        store.upsert_nodes([updated])
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].name == "foo_updated"

    def test_find_by_name(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        store.upsert_nodes([self._make_node("MyFunc")])
        found = store.find_by_name("myfunc")   
        assert len(found) == 1

    def test_stats(self, tmp_path: Path):
        store = self._make_store(tmp_path)
        store.upsert_nodes([
            self._make_node("f1", NodeKind.FUNCTION),
            self._make_node("C1", NodeKind.CLASS, "src/b.py"),
        ])
        stats = store.stats()
        assert stats["total_nodes"] == 2
        assert "function" in stats["by_kind"]

    def test_json_fields_roundtrip(self, tmp_path: Path):
        from code_atlas.core.models import IRNode
        store = self._make_store(tmp_path)
        node = IRNode(
            id="test-repo:src/a.py:foo:1", name="foo", kind=NodeKind.FUNCTION,
            file_path="src/a.py", start_line=1, end_line=10, language="python",
            parameters=["self", "x", "y"],
            calls=["bar", "baz"],
            decorators=["staticmethod"],
        )
        store.upsert_nodes([node])
        loaded = store.load_all()[0]
        assert loaded.parameters == ["self", "x", "y"]
        assert loaded.calls == ["bar", "baz"]
        assert loaded.decorators == ["staticmethod"]



# Pipeline (integration)

@pytest.mark.skipif(
    __import__("importlib").util.find_spec("tree_sitter_python") is None,
    reason="tree-sitter-python not installed",
)
class TestParsingPipeline:

    def test_full_pipeline_python(self, tmp_path: Path):
        from code_atlas.parsing.pipeline import run_parsing

        py_code = (
            "import os\n"
            "class MyService:\n"
            "    def run(self, x):\n"
            "        return os.path.join(x)\n"
            "def helper():\n"
            "    pass\n"
        )
        manifest, _ = make_manifest(tmp_path, [("src/service.py", "python", py_code)])
        ir_dir = tmp_path / "ir"

        report = run_parsing(manifest, ir_dir=ir_dir)

        assert len(report.results) == 1
        assert report.total_nodes > 0
        assert report.results[0].success is True

        kinds = {n.kind for n in report.all_nodes}
        assert NodeKind.MODULE in kinds
        assert NodeKind.CLASS in kinds
        assert NodeKind.METHOD in kinds
        assert NodeKind.FUNCTION in kinds

    def test_skips_json_files(self, tmp_path: Path):
        from code_atlas.parsing.pipeline import run_parsing

        manifest, _ = make_manifest(tmp_path, [
            ("package.json", "json", '{"name": "test"}'),
            ("src/app.py", "python", "def run(): pass\n"),
        ])
        ir_dir = tmp_path / "ir"
        report = run_parsing(manifest, ir_dir=ir_dir)

        parsed_paths = [r.file_path for r in report.results]
        assert not any("package.json" in p for p in parsed_paths)
        assert any("app.py" in p for p in parsed_paths)

    def test_nodes_persisted_to_ir_store(self, tmp_path: Path):
        from code_atlas.parsing.pipeline import run_parsing
        from code_atlas.parsing.ir_store import IRStore

        manifest, _ = make_manifest(tmp_path, [
            ("src/app.py", "python", "def hello(): pass\n"),
        ])
        ir_dir = tmp_path / "ir"
        run_parsing(manifest, ir_dir=ir_dir)

        store = IRStore("test-repo", ir_dir=ir_dir)
        nodes = store.load_all()
        assert len(nodes) > 0

    def test_incremental_parse_replaces_nodes(self, tmp_path: Path):
        """Re-parsing a modified file should replace its old nodes."""
        from code_atlas.parsing.pipeline import run_parsing
        from code_atlas.parsing.ir_store import IRStore
        from code_atlas.core.models import FileStatus

        manifest, repo_root = make_manifest(tmp_path, [
            ("src/app.py", "python", "def old_func(): pass\n"),
        ])
        ir_dir = tmp_path / "ir"
        run_parsing(manifest, ir_dir=ir_dir)

        (repo_root / "src" / "app.py").write_text("def new_func(): pass\n")
        manifest.files[0].status = FileStatus.MODIFIED

        run_parsing(manifest, ir_dir=ir_dir)

        store = IRStore("test-repo", ir_dir=ir_dir)
        names = [n.name for n in store.load_all()]
        assert "new_func" in names
        assert "old_func" not in names

    def test_failed_parse_still_in_report(self, tmp_path: Path):
        """A file that fails to read should produce a failed ParseResult, not crash."""
        from code_atlas.parsing.pipeline import run_parsing

        manifest, repo_root = make_manifest(tmp_path, [
            ("src/app.py", "python", "def foo(): pass\n"),
        ])
        (repo_root / "src" / "app.py").unlink()
        ir_dir = tmp_path / "ir"

        report = run_parsing(manifest, ir_dir=ir_dir)

        assert len(report.results) == 1
        assert report.results[0].success is False