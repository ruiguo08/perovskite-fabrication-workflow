"""Structural guardrails for the split web.repository package.

The split into per-domain mixins moved methods and helpers across module
boundaries. Three regression classes from that work are invisible to the
unittest suite at runtime, so they are locked in here:

- postponed annotation evaluation (``from __future__ import annotations``)
  means a missing import used only in an annotation never fails at runtime;
  it only surfaces through ``typing.get_type_hints``;
- a submodule whose name collides with a package-level re-export (e.g. a
  plural ``experiments.py`` next to the re-exported ``experiments`` table)
  silently shadows the re-export once imported;
- ``helpers.py`` is the bottom of the layering: it must never import from a
  domain module, or the shared/domain split collapses into a cycle.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import types
import typing
import unittest
from pathlib import Path

import sqlalchemy

import web.repository
from web.repository import WebRepository

REPOSITORY_PACKAGE_DIR = Path(web.repository.__file__).resolve().parent

DOMAIN_MODULE_NAMES = [
    "experiment",
    "baseline",
    "preset",
    "material",
    "result",
    "identity",
    "admin",
    "campaign",
    "condition",
    "batch",
]


def package_module_names() -> list[str]:
    """Every submodule that exists in the package, discovered on disk.

    Importing all of them is what makes the shadowing check below honest: a
    submodule only shadows a package-level re-export once it is imported.
    """
    return sorted(
        path.stem
        for path in REPOSITORY_PACKAGE_DIR.glob("*.py")
        if path.stem != "__init__"
    )


class RepositoryAnnotationTests(unittest.TestCase):
    """Every annotation in the package must evaluate despite postponed eval."""

    def test_all_annotations_evaluate(self) -> None:
        checked = 0
        failures: list[str] = []
        for module_name in package_module_names():
            module = importlib.import_module(f"web.repository.{module_name}")
            for obj in vars(module).values():
                targets: list[object] = []
                if inspect.isfunction(obj) and obj.__module__ == module.__name__:
                    targets.append(obj)
                elif isinstance(obj, type) and obj.__module__ == module.__name__:
                    targets.extend(
                        member
                        for member in vars(obj).values()
                        if inspect.isfunction(member)
                    )
                for target in targets:
                    checked += 1
                    try:
                        typing.get_type_hints(target)
                    except Exception as error:  # collect all failures, then assert
                        failures.append(
                            f"{target.__qualname__}: {error}"
                        )
        self.assertGreater(checked, 0)
        self.assertEqual(failures, [], "annotations that do not evaluate")


class RepositorySurfaceTests(unittest.TestCase):
    """Package-level re-exports must not be shadowed by submodules."""

    def test_no_all_entry_is_a_module(self) -> None:
        # Import every submodule first: a submodule shadows a package-level
        # re-export only once something has imported it.
        for module_name in package_module_names():
            importlib.import_module(f"web.repository.{module_name}")
        shadowed = [
            name
            for name in web.repository.__all__
            if isinstance(getattr(web.repository, name), types.ModuleType)
        ]
        self.assertEqual(shadowed, [])

    def test_sqlalchemy_table_reexports_are_tables(self) -> None:
        self.assertIsInstance(web.repository.experiments, sqlalchemy.Table)
        self.assertIsInstance(web.repository.experiment_conditions, sqlalchemy.Table)

    def test_webrepository_composes_all_domain_mixins(self) -> None:
        mixin_names = [
            base.__name__
            for base in WebRepository.__mro__
            if base.__name__.endswith("Mixin")
        ]
        self.assertEqual(
            mixin_names,
            [
                "ExperimentsMixin",
                "BaselinesMixin",
                "LayerPresetsMixin",
                "MaterialsMixin",
                "ResultsMixin",
                "UsersMixin",
                "AdminMixin",
                "CampaignsMixin",
                "ConditionsMixin",
                "FabricationBatchesMixin",
            ],
        )


class RepositoryLayeringTests(unittest.TestCase):
    """helpers.py is the bottom layer and must not import domain modules."""

    def test_helpers_never_import_domain_modules(self) -> None:
        source = (REPOSITORY_PACKAGE_DIR / "helpers.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = ("." * node.level) + (node.module or "")
                stem = module.lstrip(".")
                if stem in DOMAIN_MODULE_NAMES:
                    violations.append(f"from {module} import ...")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
