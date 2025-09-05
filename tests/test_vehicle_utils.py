import ast
import pathlib
import re

# Parse functions from fbx_importer.py without importing the module
module_path = pathlib.Path(__file__).resolve().parents[1] / "fbx_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {'re': re}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {"normalize_root_name", "get_root_vehicle_names", "belongs_to_vehicle"}:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

normalize_root_name = ns["normalize_root_name"]
get_root_vehicle_names = ns["get_root_vehicle_names"]
belongs_to_vehicle = ns["belongs_to_vehicle"]


class Obj:
    def __init__(self, name, type='EMPTY', parent=None):
        self.name = name
        self.type = type
        self.parent = parent


def test_get_root_vehicle_names_dedup():
    root1 = Obj('Heil')
    root2 = Obj('Heil.001')
    root3 = Obj('Heil_Rear')
    child = Obj('Mesh: Heil.001: Body', type='MESH', parent=root2)
    objects = [root1, root2, root3, child]
    assert get_root_vehicle_names(objects) == ['Heil', 'Heil_Rear']


def test_belongs_to_vehicle_match():
    assert belongs_to_vehicle('Mesh: Heil: Body', 'Heil')
    assert belongs_to_vehicle('Heil', 'Heil')
    assert belongs_to_vehicle('Mesh: Heil_Rear: Body', 'Heil')
    assert belongs_to_vehicle('Mesh: Heil_Rear: Body', 'Heil_Rear')
    assert not belongs_to_vehicle('Mesh: Other: Body', 'Heil')

def test_belongs_to_vehicle_numeric_suffix():
    assert belongs_to_vehicle('Mesh: Heil.001: Body', 'Heil')
    assert belongs_to_vehicle('Mesh: Heil_Rear.001: Body', 'Heil')
    assert not belongs_to_vehicle('Mesh: Other.001: Body', 'Heil')


if __name__ == "__main__":
    test_get_root_vehicle_names_dedup()
    test_belongs_to_vehicle_match()
    test_belongs_to_vehicle_numeric_suffix()
    print("ok")
