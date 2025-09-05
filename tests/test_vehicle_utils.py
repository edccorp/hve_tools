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
    root2 = Obj('Heil_Rear')
    child = Obj('Mesh: Heil: Body', type='MESH', parent=root1)
    objects = [root1, root2, child]
    assert get_root_vehicle_names(objects) == ['Heil', 'Heil_Rear']


def test_belongs_to_vehicle_match():
    assert belongs_to_vehicle('Mesh: Heil: Body', 'Heil')
    assert belongs_to_vehicle('Heil', 'Heil')
    assert not belongs_to_vehicle('Mesh: Heil_Rear: Body', 'Heil')
    assert belongs_to_vehicle('Mesh: Heil_Rear: Body', 'Heil_Rear')


if __name__ == "__main__":
    test_get_root_vehicle_names_dedup()
    test_belongs_to_vehicle_match()
    print("ok")
