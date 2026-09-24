"""Dependency-boundary tests for the application-operations layering.

The target architecture (see ARCHITECTURE.md "Module responsibilities"):

    HTTP routes (web.routes) -> application operations (web.operations)
        -> repository data functions (web.repository) -> web.database

These tests pin the import direction with AST scans so a violation fails in
CI instead of surviving as a silent architectural regression. In-function
(lazy) imports are checked separately: they are allowed only in the two
documented deprecated repository delegates.
"""

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WEB = SRC / "web"

sys.path.insert(0, str(SRC))


def _module_files(package: Path) -> list[Path]:
    return sorted(package.glob("*.py"))


def _imports_at_module_level(tree: ast.Module) -> list[str]:
    """Full dotted names imported at module level (imports inside functions
    or classes are excluded)."""

    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.extend(f"{node.module}.{a.name}" for a in node.names)
            else:
                names.extend(a.name for a in node.names)
    return names


class RepositoryToOperationsBoundaryTests(unittest.TestCase):
    """The repository depends on the database and domain records only; the
    application-operations layer calls into it, never the reverse (the two
    deprecated delegates call operations lazily inside their function bodies
    and are counted explicitly)."""

    def test_repository_never_imports_operations_at_module_level(self) -> None:
        offenders = []
        for path in _module_files(WEB / "repository"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name in _imports_at_module_level(tree):
                if ".operations" in name or name.startswith("operations"):
                    offenders.append(f"{path.name}: {name}")
        self.assertEqual(offenders, [])

    def test_lazy_operations_imports_are_limited_to_documented_delegates(self) -> None:
        allowed = {
            "result.py": "update_result_analysis_and_complete",
            "batch.py": "update_fabrication_batch_status",
        }
        for path in _module_files(WEB / "repository"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            lazy = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module
                and "operations" in node.module
                and id(node) not in {id(n) for n in tree.body}
            ]
            if not lazy:
                continue
            self.assertIn(path.name, allowed, f"unexpected lazy import in {path.name}")
            # Every lazy operations import in the file must sit inside the
            # one documented delegate method.
            lazy_ids = {id(node) for node in lazy}
            containing_functions = [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and any(id(child) in lazy_ids for child in ast.walk(node))
            ]
            self.assertEqual(
                len(containing_functions), len(lazy),
                f"lazy operations imports spread over multiple functions in {path.name}",
            )
            for function in containing_functions:
                self.assertEqual(function.name, allowed[path.name])


class ServicesToRepositoryBoundaryTests(unittest.TestCase):
    """The services layer must not import the repository package; shared
    low-level functionality (audit events) lives in web.audit_trail."""

    def test_services_never_import_repository_at_module_level(self) -> None:
        offenders = []
        for path in _module_files(WEB / "services"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name in _imports_at_module_level(tree):
                if name.startswith("repository") or ".repository" in name:
                    offenders.append(f"{path.name}: {name}")
        self.assertEqual(offenders, [])

    def test_services_do_not_lazily_import_repository(self) -> None:
        offenders = []
        for path in _module_files(WEB / "services"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and "repository" in node.module
                ):
                    offenders.append(f"{path.name}: {node.module}")
        self.assertEqual(offenders, [])


class OperationsBoundaryTests(unittest.TestCase):
    """Application operations stay HTTP-free and never import the routes."""

    def test_operations_never_import_routes_or_http(self) -> None:
        offenders = []
        for path in _module_files(WEB / "operations"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for name in _imports_at_module_level(tree):
                if "routes" in name or "HTTPException" in name:
                    offenders.append(f"{path.name}: {name}")
            if "HTTPException" in source:
                offenders.append(f"{path.name}: raises HTTPException")
        self.assertEqual(offenders, [])


class CorePackageBoundaryTests(unittest.TestCase):
    """perovskite_bo (the core science package) must not import web."""

    def test_core_never_imports_web(self) -> None:
        offenders = []
        core = SRC / "perovskite_bo"
        for path in _module_files(core):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name in _imports_at_module_level(tree):
                if name == "web" or name.startswith("web."):
                    offenders.append(f"{path.name}: {name}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
