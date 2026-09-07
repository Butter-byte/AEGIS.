"""Import-boundary enforcement (docs/TRD.md §"Dependency rules").

Static scan of `backend/`. Fails CI if a module imports across a forbidden edge.
These edges encode the core invariant and the ownership map — a teammate module
that violates one is flagged here rather than silently taking over another's job.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1] / "backend"
TEAMMATE_PKGS = {
    "network", "telemetry", "faults", "twin", "diagnosis", "recovery", "safety", "scenarios",
}


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _modules(pkg: str) -> list[pathlib.Path]:
    return list((BACKEND / pkg).rglob("*.py"))


def test_models_is_a_leaf_package():
    for f in _modules("models"):
        for imp in _imports(f):
            assert not (imp.startswith("backend.") and not imp.startswith("backend.models")), (
                f"{f.relative_to(BACKEND)} imports {imp} — models/ must import nothing else in backend/"
            )


def test_pipeline_imports_no_teammate_package():
    # Ports are inline Protocols in backend/pipeline.py now; the orchestrator must
    # still reach teammate modules only through injected ports, never by import.
    for imp in _imports(BACKEND / "pipeline.py"):
        assert not any(imp.startswith(f"backend.{p}") for p in TEAMMATE_PKGS), (
            f"pipeline.py imports {imp} — the orchestrator talks to teammate "
            f"modules only via injected ports"
        )


def test_api_does_not_import_execution():
    for f in _modules("api"):
        assert not any(i.startswith("backend.execution") for i in _imports(f)), (
            f"{f.relative_to(BACKEND)} imports backend.execution — only the pipeline may call execution/"
        )


def test_execution_does_not_import_planner_or_safety():
    for f in _modules("execution"):
        for imp in _imports(f):
            assert not imp.startswith(("backend.recovery", "backend.diagnosis", "backend.safety")), (
                f"{f.relative_to(BACKEND)} imports {imp} — execution/ applies approved plans, it does not plan or judge"
            )


def test_teammate_packages_are_present():
    for pkg in TEAMMATE_PKGS:
        assert (BACKEND / pkg).is_dir()
        assert (BACKEND / pkg / "__init__.py").exists()