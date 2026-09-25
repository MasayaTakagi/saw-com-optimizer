import ast
import importlib.util
from pathlib import Path
import unittest


SRC = Path(__file__).parents[2] / 'src' / 'sawopt'


def _absolute_import(package, node):
    if isinstance(node, ast.Import):
        return [(alias.name, None) for alias in node.names]
    relative = '.' * node.level + (node.module or '')
    name = importlib.util.resolve_name(relative, package) if relative else package
    return [(name, alias.name) for alias in node.names]


def _architecture_violations(module, path_name, source):
    parts = module.split('.')
    package = '.'.join(parts[:-1])
    owner = parts[1] if len(parts) > 1 else ''
    violations = []
    tree = ast.parse(source, filename=path_name)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for imported, imported_name in _absolute_import(package, node):
            if owner == 'core' and imported.startswith(('sawopt.optimization', 'sawopt.optimizers', 'sawopt.problem', 'sawopt.studies')):
                violations.append(f'{module} imports {imported}')
            if owner == 'optimizers' and imported.startswith(('sawopt.core', 'sawopt.studies', 'sawopt.problem')):
                violations.append(f'{module} imports {imported}')
            if owner == 'problem' and imported.startswith('sawopt.studies'):
                violations.append(f'{module} imports {imported}')
            if owner == 'optimization' and imported.startswith('sawopt.studies'):
                violations.append(f'{module} imports {imported}')
            if owner == 'studies' and imported.startswith('sawopt.studies') and imported_name and imported_name.startswith('_'):
                violations.append(f'{module} imports private {imported}.{imported_name}')
    return violations


class ArchitectureBoundaries(unittest.TestCase):
    def test_layer_import_boundaries_and_public_cross_study_imports(self):
        violations = []
        for path in SRC.rglob('*.py'):
            relative = path.relative_to(SRC).with_suffix('')
            parts = ('sawopt',) + relative.parts
            module = '.'.join(parts)
            violations.extend(_architecture_violations(
                module, str(path), path.read_text(encoding='utf-8')
            ))
        self.assertEqual([], violations)

    def test_relative_and_absolute_cross_study_private_imports_are_rejected(self):
        relative = _architecture_violations(
            'sawopt.studies.fixture', 'fixture.py',
            'from .other import _private_helper\n',
        )
        absolute = _architecture_violations(
            'sawopt.studies.fixture', 'fixture.py',
            'from sawopt.studies.other import _private_helper\n',
        )
        self.assertTrue(relative)
        self.assertTrue(absolute)
        self.assertIn('sawopt.studies.other._private_helper', relative[0])
        self.assertIn('sawopt.studies.other._private_helper', absolute[0])

    def test_live_study_adapters_are_role_named(self):
        modules = {path.stem for path in (SRC / 'studies').glob('*.py')}
        self.assertIn('dms_topology_screening', modules)
        self.assertIn('hybrid', modules)
        self.assertFalse(any(name.startswith(('stage', 'phase_c')) for name in modules))
