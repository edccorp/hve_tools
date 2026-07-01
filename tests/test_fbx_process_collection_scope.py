import ast
import pathlib
import types


# Extract the collection-scoping helpers from fbx_importer_ui.py and drive them
# with stub collections (no Blender needed).
module_path = pathlib.Path(__file__).resolve().parents[1] / "fbx_importer_ui.py"
module_ast = ast.parse(module_path.read_text())

WANTED = {"_collection_and_descendant_names", "get_hve_vehicle_names"}


class FakeCollection:
    def __init__(self, name, children=()):
        self.name = name
        self.children = list(children)


# Scene hierarchy: two vehicles; only "Toyota" is nested under the event.
body_toyota = FakeCollection("Body Mesh: Toyota: Event: FBX")
veh_toyota = FakeCollection("HVE: Event: Toyota", [body_toyota])
event = FakeCollection("HVE: Event", [veh_toyota])
body_honda = FakeCollection("Body Mesh: Honda: Event: FBX")
veh_honda = FakeCollection("HVE: Event: Honda", [body_honda])

all_collections = [event, veh_toyota, body_toyota, veh_honda, body_honda]
fake_bpy = types.SimpleNamespace(data=types.SimpleNamespace(collections=all_collections))

ns = {"bpy": fake_bpy}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANTED:
        exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), ns)

get_hve_vehicle_names = ns["get_hve_vehicle_names"]
_collection_and_descendant_names = ns["_collection_and_descendant_names"]


def test_descendant_names_includes_self_and_children():
    assert _collection_and_descendant_names(event) == {
        "HVE: Event",
        "HVE: Event: Toyota",
        "Body Mesh: Toyota: Event: FBX",
    }


def test_all_vehicles_without_scope():
    assert get_hve_vehicle_names() == ["Toyota", "Honda"]


def test_scope_limits_to_collection_subtree():
    assert get_hve_vehicle_names(event) == ["Toyota"]
    assert get_hve_vehicle_names(veh_honda) == ["Honda"]


def test_scope_with_no_body_meshes_returns_empty():
    empty = FakeCollection("Some Other Collection")
    assert get_hve_vehicle_names(empty) == []
