import ast
import pathlib
from contextlib import contextmanager


module_path = pathlib.Path(__file__).resolve().parents[1] / 'fbx_importer.py'
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {'contextmanager': contextmanager}

for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == 'temporarily_disable_modifiers':
        code = compile(ast.Module([node], []), filename='<ast>', mode='exec')
        exec(code, ns)


temporarily_disable_modifiers = ns['temporarily_disable_modifiers']


class DummyModifier:
    def __init__(self, show_viewport=True, show_render=True):
        self.show_viewport = show_viewport
        self.show_render = show_render


class DummyObject:
    def __init__(self, modifiers):
        self.modifiers = modifiers


def test_temporarily_disable_modifiers_restores_original_state():
    modifiers = [DummyModifier(True, False), DummyModifier(False, True)]
    obj = DummyObject(modifiers)

    with temporarily_disable_modifiers(obj):
        assert all(not modifier.show_viewport for modifier in modifiers)
        assert all(not modifier.show_render for modifier in modifiers)

    assert modifiers[0].show_viewport is True
    assert modifiers[0].show_render is False
    assert modifiers[1].show_viewport is False
    assert modifiers[1].show_render is True
