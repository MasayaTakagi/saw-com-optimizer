import ast
import importlib
from pathlib import Path


PHYSICS_MODULES = ("com", "elements", "network", "literature_com")
FORBIDDEN_ROOTS = {
    "core", "design", "problem", "optimization", "optimizers", "studies",
    "reporting", "orchestration", "runtime",
}


def test_physics_modules_are_importable_without_upward_dependencies():
    package_dir = Path(__file__).parents[3] / "src" / "sawopt" / "physics"
    for module_name in PHYSICS_MODULES:
        module_path = package_dir / f"{module_name}.py"
        importlib.import_module(f"sawopt.physics.{module_name}")
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported = [node.module or ""]
            else:
                continue
            roots = {name.split(".")[1] for name in imported if name.startswith("sawopt.")}
            assert roots.isdisjoint(FORBIDDEN_ROOTS), (
                f"{module_path} imports an upward package: {roots & FORBIDDEN_ROOTS}"
            )
