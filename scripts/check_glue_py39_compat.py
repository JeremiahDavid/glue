"""Scan meshflow sources bundled for Glue Python Shell 3.9 for incompatibilities."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

GLUE_MESHFLOW_ROOTS = (
    PROJECT_ROOT / "packages" / "meshflow-platform" / "src" / "meshflow",
    PROJECT_ROOT / "packages" / "meshflow-connectors" / "src" / "meshflow",
    PROJECT_ROOT / "packages" / "meshflow-lake" / "src" / "meshflow",
    PROJECT_ROOT / "packages" / "meshflow-dna" / "src" / "meshflow",
    PROJECT_ROOT / "packages" / "meshflow-portal" / "src" / "meshflow",
    PROJECT_ROOT / "packages" / "meshflow" / "src" / "meshflow",
)
GLUE_SCRIPT = PROJECT_ROOT / "scripts" / "glue_bronze_ingest.py"


@dataclass(frozen=True)
class Issue:
    path: Path
    lineno: int
    kind: str
    detail: str


def _line(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if lineno < 1 or lineno > len(lines):
        return ""
    return lines[lineno - 1].strip()


def _has_future_annotations(tree: ast.AST) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == "annotations" for alias in node.names):
                return True
    return False


def _bit_or_union(node: ast.AST) -> bool:
    return isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)


class Py39Visitor(ast.NodeVisitor):
    def __init__(self, path: Path, text: str, *, has_future_annotations: bool) -> None:
        self.path = path
        self.text = text
        self.has_future_annotations = has_future_annotations
        self.issues: list[Issue] = []

    def visit_Match(self, node: ast.Match) -> None:
        self.issues.append(
            Issue(self.path, node.lineno, "match-statement", _line(self.text, node.lineno))
        )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in {"isinstance", "issubclass"}:
            if len(node.args) >= 2 and _bit_or_union(node.args[1]):
                self.issues.append(
                    Issue(
                        self.path,
                        node.lineno,
                        "runtime-union-isinstance",
                        _line(self.text, node.lineno),
                    )
                )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_pep604_signature(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_pep604_signature(node)
        self.generic_visit(node)

    def _check_pep604_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self.has_future_annotations:
            return
        args = [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        if node.args.vararg and node.args.vararg.annotation:
            args.append(node.args.vararg)
        if node.args.kwarg and node.args.kwarg.annotation:
            args.append(node.args.kwarg)
        for arg in args:
            if arg.annotation and _bit_or_union(arg.annotation):
                self.issues.append(
                    Issue(
                        self.path,
                        arg.lineno,
                        "pep604-without-future-annotations",
                        _line(self.text, arg.lineno),
                    )
                )
        if node.returns and _bit_or_union(node.returns):
            self.issues.append(
                Issue(
                    self.path,
                    node.lineno,
                    "pep604-return-without-future-annotations",
                    node.name,
                )
            )


def _check_source(path: Path) -> list[Issue]:
    if path.name == "compat.py":
        return []
    text = path.read_text(encoding="utf-8")
    issues: list[Issue] = []

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped == "from datetime import UTC" or stripped.startswith("from datetime import UTC,"):
            issues.append(
                Issue(path, lineno, "datetime-utc-import", stripped)
            )

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        issues.append(Issue(path, exc.lineno or 0, "syntax-error", str(exc)))
        return issues

    visitor = Py39Visitor(path, text, has_future_annotations=_has_future_annotations(tree))
    visitor.visit(tree)
    issues.extend(visitor.issues)
    return issues


def iter_glue_python_files() -> list[Path]:
    files: list[Path] = []
    if GLUE_SCRIPT.is_file():
        files.append(GLUE_SCRIPT)
    for root in GLUE_MESHFLOW_ROOTS:
        if root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    return files


def main() -> int:
    issues: list[Issue] = []
    for path in iter_glue_python_files():
        issues.extend(_check_source(path))

    if not issues:
        print("Glue Python 3.9 compatibility check passed.")
        return 0

    for issue in sorted(issues, key=lambda item: (str(item.path), item.lineno, item.kind)):
        rel = issue.path.relative_to(PROJECT_ROOT)
        print(f"{rel}:{issue.lineno}: {issue.kind}: {issue.detail}")
    print(f"\nFound {len(issues)} Python 3.9 compatibility issue(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
