"""Verify that package objects remain documented as the bot evolves."""

import ast
from pathlib import Path


def test_all_package_objects_have_docstrings() -> None:
    """Require descriptions for every module, class, function, and method."""
    package_root = Path(__file__).parents[1] / "src" / "splitnshare"
    missing: list[str] = []

    for path in sorted(package_root.rglob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if module.body and ast.get_docstring(module) is None:
            missing.append(f"{path.relative_to(package_root)}: module")
        for node in ast.walk(module):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if ast.get_docstring(node) is None:
                    missing.append(
                        f"{path.relative_to(package_root)}:{node.lineno}: {node.name}"
                    )

    assert not missing, "Missing docstrings:\n" + "\n".join(missing)
