from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    # Create a minimal fake repository on disk with a predictable structure.
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "node_modules").mkdir() #excluded dir
    (tmp_path / "build").mkdir()  #excluded dir
    (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42\n")
    (tmp_path / "src" / "auth" / "login.py").write_text("class LoginView:\n    pass\n")
    (tmp_path / "tests" / "test_main.py").write_text("def test_main():\n    assert True\n")
    (tmp_path / "README.md").write_text("# My Repo\n")
    (tmp_path / "node_modules" / "something.js").write_text("module.exports = {}")
    (tmp_path / "build" / "output.js").write_text("var x = 1;")

    return tmp_path


class TestLanguageDetector:

    def test_python_by_extension(self, tmp_path: Path):
        from code_atlas.ingestion.language_detector import detect_language
        f = tmp_path / "script.py"
        f.write_text("x = 1")
        assert detect_language(f) == "python"

    def test_typescript_by_extension(self, tmp_path: Path):
        from code_atlas.ingestion.language_detector import detect_language
        f = tmp_path / "app.ts"
        f.write_text("const x: number = 1;")
        assert detect_language(f) == "typescript"

    def test_shebang_python(self, tmp_path: Path):
        from code_atlas.ingestion.language_detector import detect_language
        f = tmp_path / "myscript"  
        f.write_text("#!/usr/bin/env python3\nprint('hello')\n")
        assert detect_language(f) == "python"

    def test_shebang_bash(self, tmp_path: Path):
        from code_atlas.ingestion.language_detector import detect_language
        f = tmp_path / "deploy"
        f.write_text("#!/bin/bash\necho hi\n")
        assert detect_language(f) == "shell"

    def test_unknown_extension_returns_none(self, tmp_path: Path):
        from code_atlas.ingestion.language_detector import detect_language
        f = tmp_path / "data.xyz123"
        f.write_text("some data")
        assert detect_language(f) is None

    def test_dockerfile_by_name(self, tmp_path: Path):
        from code_atlas.ingestion.language_detector import detect_language
        f = tmp_path / "Dockerfile"
        f.write_text("FROM python:3.12\n")
        assert detect_language(f) == "dockerfile"

    def test_binary_guard(self, tmp_path: Path):
        from code_atlas.ingestion.language_detector import is_binary_file
        f = tmp_path / "image.bin"
        f.write_bytes(b"\x00\x01\x02\x03binary content")
        assert is_binary_file(f) is True

    def test_text_file_not_binary(self, tmp_path: Path):
        from code_atlas.ingestion.language_detector import is_binary_file
        f = tmp_path / "code.py"
        f.write_text("def f(): pass\n")
        assert is_binary_file(f) is False

class TestHasher:
    def test_hash_file_deterministic(self, tmp_path: Path):
        from code_atlas.ingestion.hasher import hash_file
        f = tmp_path / "file.py"
        f.write_text("hello world")
        h1 = hash_file(f)
        h2 = hash_file(f)
        assert h1 == h2

    def test_hash_file_changes_on_content_change(self, tmp_path: Path):
        from code_atlas.ingestion.hasher import hash_file
        f = tmp_path / "file.py"
        f.write_text("version 1")
        h1 = hash_file(f)
        f.write_text("version 2")
        h2 = hash_file(f)
        assert h1 != h2

    def test_hash_file_matches_stdlib(self, tmp_path: Path):
        from code_atlas.ingestion.hasher import hash_file
        content = b"the quick brown fox"
        f = tmp_path / "fox.txt"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert hash_file(f) == expected

    def test_hash_files_parallel_all_hashed(self, tmp_path: Path):
        from code_atlas.ingestion.hasher import hash_files_parallel
        files = []
        for i in range(10):
            p = tmp_path / f"file_{i}.py"
            p.write_text(f"content {i}")
            files.append(p)
        result = hash_files_parallel(files, workers=4)
        assert len(result) == 10

    def test_compute_change_set_new_file(self):
        from code_atlas.ingestion.hasher import compute_change_set
        current = {"a.py": "abc", "b.py": "def"}
        stored  = {}
        changed = compute_change_set(current, stored)
        assert set(changed.keys()) == {"a.py", "b.py"}

    def test_compute_change_set_modified(self):
        from code_atlas.ingestion.hasher import compute_change_set
        current = {"a.py": "newhash"}
        stored  = {"a.py": "oldhash"}
        changed = compute_change_set(current, stored)
        assert "a.py" in changed

    def test_compute_change_set_unchanged_excluded(self):
        from code_atlas.ingestion.hasher import compute_change_set
        current = {"a.py": "samehash"}
        stored  = {"a.py": "samehash"}
        changed = compute_change_set(current, stored)
        assert len(changed) == 0

class TestScanner:

    def test_scanner_finds_python_files(self, tmp_repo: Path):
        from code_atlas.ingestion.scanner import scan_repository
        records = scan_repository(tmp_repo, stored_hashes={})
        py_files = [r for r in records if r.language == "python"]
        assert len(py_files) == 4  

    def test_scanner_excludes_node_modules(self, tmp_repo: Path):
        from code_atlas.ingestion.scanner import scan_repository
        records = scan_repository(tmp_repo, stored_hashes={})
        paths = [r.path for r in records]
        assert not any("node_modules" in p for p in paths)

    def test_scanner_excludes_build_dir(self, tmp_repo: Path):
        from code_atlas.ingestion.scanner import scan_repository
        records = scan_repository(tmp_repo, stored_hashes={})
        paths = [r.path for r in records]
        assert not any(p.startswith("build") for p in paths)

    def test_scanner_marks_all_new_on_first_run(self, tmp_repo: Path):
        from code_atlas.ingestion.scanner import scan_repository
        from code_atlas.core.models import FileStatus
        records = scan_repository(tmp_repo, stored_hashes={})
        live = [r for r in records if r.status != FileStatus.DELETED]
        assert all(r.status == FileStatus.NEW for r in live)

    def test_scanner_marks_unchanged_on_second_run(self, tmp_repo: Path):
        from code_atlas.ingestion.scanner import scan_repository
        from code_atlas.ingestion.hasher import hash_files_parallel
        from code_atlas.core.models import FileStatus
        # First run
        records1 = scan_repository(tmp_repo, stored_hashes={})
        stored = {r.path: r.sha256 for r in records1 if r.status != FileStatus.DELETED}

        # Second run with same stored hashes
        records2 = scan_repository(tmp_repo, stored_hashes=stored)
        live = [r for r in records2 if r.status != FileStatus.DELETED]
        assert all(r.status == FileStatus.UNCHANGED for r in live)

    def test_scanner_detects_modification(self, tmp_repo: Path):
        from code_atlas.ingestion.scanner import scan_repository
        from code_atlas.core.models import FileStatus

        records1 = scan_repository(tmp_repo, stored_hashes={})
        stored = {r.path: r.sha256 for r in records1 if r.status != FileStatus.DELETED}

        (tmp_repo / "src" / "main.py").write_text("def main():\n    return 99\n")

        records2 = scan_repository(tmp_repo, stored_hashes=stored)
        modified = [r for r in records2 if r.status == FileStatus.MODIFIED]
        assert len(modified) == 1
        assert "main.py" in modified[0].path

    def test_scanner_detects_deletion(self, tmp_repo: Path):
        from code_atlas.ingestion.scanner import scan_repository
        from code_atlas.core.models import FileStatus

        records1 = scan_repository(tmp_repo, stored_hashes={})
        stored = {r.path: r.sha256 for r in records1 if r.status != FileStatus.DELETED}

        (tmp_repo / "src" / "utils.py").unlink()

        records2 = scan_repository(tmp_repo, stored_hashes=stored)
        deleted = [r for r in records2 if r.status == FileStatus.DELETED]
        assert len(deleted) == 1
        assert "utils.py" in deleted[0].path

    def test_scanner_line_count(self, tmp_repo: Path):
        from code_atlas.ingestion.scanner import scan_repository
        from code_atlas.core.models import FileStatus

        records = scan_repository(tmp_repo, stored_hashes={})
        main_rec = next(r for r in records if r.path.endswith("main.py"))
        assert main_rec.line_count == 2 



class TestManifestStore:

    def test_empty_snapshot_on_first_run(self, tmp_path: Path, monkeypatch):
        from code_atlas.ingestion import manifest_store as ms_module
        monkeypatch.setattr(ms_module, "__import__", None, raising=False)

        import code_atlas.core.config as cfg_module
        monkeypatch.setattr(cfg_module, "MANIFESTS_DIR", tmp_path)

        from code_atlas.ingestion.manifest_store import ManifestStore
        store = ManifestStore.__new__(ManifestStore)
        store.repo_id = "test-repo"
        store.db_path = tmp_path / "test-repo.db"
        store._init_db()

        assert store.load_snapshot() == {}

    def test_save_and_reload(self, tmp_path: Path, monkeypatch):
        import code_atlas.core.config as cfg_module
        monkeypatch.setattr(cfg_module, "MANIFESTS_DIR", tmp_path)

        from code_atlas.ingestion.manifest_store import ManifestStore
        from code_atlas.core.models import FileRecord, FileStatus

        store = ManifestStore.__new__(ManifestStore)
        store.repo_id = "test-repo"
        store.db_path = tmp_path / "test-repo.db"
        store._init_db()

        records = [
            FileRecord(
                path="src/main.py",
                language="python",
                sha256="abc123",
                size_bytes=100,
                last_modified=datetime.utcnow(),
                status=FileStatus.NEW,
                line_count=5,
            )
        ]
        store.save_records(records)
        snapshot = store.load_snapshot()
        assert snapshot == {"src/main.py": "abc123"}

    def test_deleted_files_removed_from_snapshot(self, tmp_path: Path, monkeypatch):
        import code_atlas.core.config as cfg_module
        monkeypatch.setattr(cfg_module, "MANIFESTS_DIR", tmp_path)

        from code_atlas.ingestion.manifest_store import ManifestStore
        from code_atlas.core.models import FileRecord, FileStatus

        store = ManifestStore.__new__(ManifestStore)
        store.repo_id = "test-repo"
        store.db_path = tmp_path / "test-repo.db"
        store._init_db()

        rec = FileRecord(
            path="old.py", language="python", sha256="xyz",
            size_bytes=50, last_modified=datetime.utcnow(),
            status=FileStatus.NEW, line_count=1,
        )
        store.save_records([rec])
        assert "old.py" in store.load_snapshot()

        rec.status = FileStatus.DELETED
        store.save_records([rec])
        assert "old.py" not in store.load_snapshot()

class TestModels:
    def test_repo_manifest_change_set(self):
        from code_atlas.core.models import FileRecord, FileStatus, RepoManifest, IngestionSource

        def make_record(path: str, status: FileStatus) -> FileRecord:
            return FileRecord(
                path=path, language="python", sha256="x",
                size_bytes=1, last_modified=datetime.utcnow(), status=status,
            )

        manifest = RepoManifest(
            repo_id="test", source="/tmp/x", source_type=IngestionSource.LOCAL_PATH,
            local_path="/tmp/x",
            files=[
                make_record("a.py", FileStatus.NEW),
                make_record("b.py", FileStatus.MODIFIED),
                make_record("c.py", FileStatus.UNCHANGED),
                make_record("d.py", FileStatus.DELETED),
            ],
        )

        assert len(manifest.change_set) == 2
        assert len(manifest.unchanged_files) == 1
        assert len(manifest.deleted_files) == 1

    def test_language_breakdown(self):
        from code_atlas.core.models import FileRecord, FileStatus, RepoManifest, IngestionSource

        def make_record(path: str, lang: str) -> FileRecord:
            return FileRecord(
                path=path, language=lang, sha256="x",
                size_bytes=1, last_modified=datetime.utcnow(), status=FileStatus.NEW,
            )

        manifest = RepoManifest(
            repo_id="test", source="/tmp/x", source_type=IngestionSource.LOCAL_PATH,
            local_path="/tmp/x",
            files=[
                make_record("a.py", "python"),
                make_record("b.py", "python"),
                make_record("c.ts", "typescript"),
            ],
        )

        breakdown = manifest.language_breakdown
        assert breakdown["python"] == 2
        assert breakdown["typescript"] == 1


class TestPipeline:

    def test_full_pipeline_local_path(self, tmp_repo: Path, tmp_path: Path, monkeypatch):
        import code_atlas.core.config as cfg_module
        monkeypatch.setattr(cfg_module, "MANIFESTS_DIR", tmp_path / "manifests")
        monkeypatch.setattr(cfg_module, "REPOS_DIR", tmp_path / "repos")
        (tmp_path / "manifests").mkdir()
        (tmp_path / "repos").mkdir()

        from code_atlas.ingestion.pipeline import run_ingestion

        manifest = run_ingestion(str(tmp_repo))

        assert manifest.repo_id is not None
        assert manifest.total_source_files >= 4
        assert len(manifest.change_set) >= 4     
        assert manifest.source_type == "local_path"

    def test_incremental_run_no_changes(self, tmp_repo: Path, tmp_path: Path, monkeypatch):
        import code_atlas.core.config as cfg_module
        monkeypatch.setattr(cfg_module, "MANIFESTS_DIR", tmp_path / "manifests")
        monkeypatch.setattr(cfg_module, "REPOS_DIR", tmp_path / "repos")
        (tmp_path / "manifests").mkdir()
        (tmp_path / "repos").mkdir()

        from code_atlas.ingestion.pipeline import run_ingestion

        run_ingestion(str(tmp_repo))
        manifest2 = run_ingestion(str(tmp_repo))

        assert len(manifest2.change_set) == 0

    def test_incremental_run_with_new_file(self, tmp_repo: Path, tmp_path: Path, monkeypatch):
        import code_atlas.core.config as cfg_module
        monkeypatch.setattr(cfg_module, "MANIFESTS_DIR", tmp_path / "manifests")
        monkeypatch.setattr(cfg_module, "REPOS_DIR", tmp_path / "repos")
        (tmp_path / "manifests").mkdir()
        (tmp_path / "repos").mkdir()

        from code_atlas.ingestion.pipeline import run_ingestion
        from code_atlas.core.models import FileStatus

        run_ingestion(str(tmp_repo))  

        (tmp_repo / "src" / "new_module.py").write_text("x = 1\n")

        manifest2 = run_ingestion(str(tmp_repo))
        new_files = [r for r in manifest2.change_set if r.status == FileStatus.NEW]
        assert any("new_module.py" in r.path for r in new_files)
