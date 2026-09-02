"""Verify that package objects remain documented as the bot evolves."""

import ast
from pathlib import Path


def test_all_project_objects_have_docstrings() -> None:
    """Require descriptions for package and migration Python objects."""
    project_root = Path(__file__).parents[1]
    source_roots = (
        project_root / "src" / "splitnshare",
        project_root / "alembic",
    )
    missing: list[str] = []

    for source_root in source_roots:
        for path in sorted(source_root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            relative_path = path.relative_to(project_root)
            if module.body and ast.get_docstring(module) is None:
                missing.append(f"{relative_path}: module")
            for node in ast.walk(module):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if ast.get_docstring(node) is None:
                        missing.append(f"{relative_path}:{node.lineno}: {node.name}")

    template = (project_root / "alembic" / "script.py.mako").read_text(
        encoding="utf-8"
    )
    for description in (
        '"""Apply this schema revision."""',
        '"""Revert this schema revision."""',
    ):
        if description not in template:
            missing.append(f"alembic/script.py.mako: {description}")

    assert not missing, "Missing docstrings:\n" + "\n".join(missing)
