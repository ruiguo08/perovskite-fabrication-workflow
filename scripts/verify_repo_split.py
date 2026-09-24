"""Verify that a WebRepository refactor preserved every method's AST.

The domain split of ``web.repository`` moves methods into per-domain mixin
modules. This script proves the move changed no logic: every method of the
old ``WebRepository`` must exist, unchanged at the AST level (``ast.dump``
ignores line numbers but not one token of code), in the new layout, and no
method may be added, lost, or altered. Top-level helper functions are
compared the same way.

Usage (compare the working tree against a git ref, default ``main``):

    uv run --no-sync python scripts/verify_repo_split.py --ref main

Exit code 0 means the layout is equivalent; 1 lists the differences.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OLD_SINGLE_FILE = "src/web/repository.py"
OLD_PACKAGE_DIR = "src/web/repository"


def _git_show(ref: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def _git_ls(ref: str, path: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref, path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def collect_definitions(sources: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Return ({method_name: ast-dump}, {function_name: ast-dump})."""

    methods: dict[str, str] = {}
    functions: dict[str, str] = {}
    for filename, source in sorted(sources.items()):
        tree = ast.parse(source, filename=filename)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if child.name in methods:
                            raise SystemExit(
                                f"duplicate method name across classes: {child.name}"
                            )
                        methods[child.name] = ast.dump(child)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions[node.name] = ast.dump(node)
    return methods, functions


def load_old(ref: str) -> tuple[dict[str, str], dict[str, str]]:
    package_files = [
        path for path in _git_ls(ref, OLD_PACKAGE_DIR) if path.endswith(".py")
    ]
    single = _git_show(ref, OLD_SINGLE_FILE)
    if single is not None and not package_files:
        sources = {OLD_SINGLE_FILE: single}
    elif package_files:
        sources = {}
        for path in package_files:
            body = _git_show(ref, path)
            if body is None:
                raise SystemExit(f"cannot read {path} from {ref}")
            sources[path] = body
    else:
        raise SystemExit(f"no repository module found at ref {ref}")
    return collect_definitions(sources)


def load_new() -> tuple[dict[str, str], dict[str, str]]:
    package_dir = REPO_ROOT / OLD_PACKAGE_DIR
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(package_dir.glob("*.py"))
    }
    return collect_definitions(sources)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main", help="git ref of the pre-split layout")
    args = parser.parse_args()

    old_methods, old_functions = load_old(args.ref)
    new_methods, new_functions = load_new()

    problems: list[str] = []
    for name in sorted(set(old_methods) - set(new_methods)):
        problems.append(f"missing method: {name}")
    for name in sorted(set(new_methods) - set(old_methods)):
        problems.append(f"unexpected new method: {name}")
    for name in sorted(set(old_methods) & set(new_methods)):
        if old_methods[name] != new_methods[name]:
            problems.append(f"changed method: {name}")
    for name in sorted(set(old_functions) - set(new_functions)):
        problems.append(f"missing top-level function: {name}")
    for name in sorted(set(new_functions) - set(old_functions)):
        problems.append(f"unexpected new top-level function: {name}")
    for name in sorted(set(old_functions) & set(new_functions)):
        if old_functions[name] != new_functions[name]:
            problems.append(f"changed top-level function: {name}")

    print(f"methods compared: {len(old_methods)} old / {len(new_methods)} new")
    print(f"top-level functions compared: {len(old_functions)} old / {len(new_functions)} new")
    if problems:
        print(f"\nFAIL ({len(problems)} problems):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nOK: every method and top-level function is AST-identical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
