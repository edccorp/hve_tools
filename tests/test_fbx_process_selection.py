import ast
import pathlib
import types


# Extract the pure helpers from fbx_importer_ui.py without importing the module
# (it imports bpy at load time, which isn't available in the test environment).
module_path = pathlib.Path(__file__).resolve().parents[1] / "fbx_importer_ui.py"
module_ast = ast.parse(module_path.read_text())
ns = {}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {
        "is_body_mesh_collection",
        "get_target_vehicle_names",
    }:
        exec(compile(ast.Module([node], []), "<ast>", "exec"), ns)

is_body_mesh_collection = ns["is_body_mesh_collection"]
get_target_vehicle_names = ns["get_target_vehicle_names"]


def _context(collection):
    scene = types.SimpleNamespace(fbx_process_collection=collection)
    return types.SimpleNamespace(scene=scene)


def test_is_body_mesh_collection_filters_by_prefix():
    assert is_body_mesh_collection(None, types.SimpleNamespace(name="Body Mesh: Toyota: FBX"))
    assert not is_body_mesh_collection(None, types.SimpleNamespace(name="Wheels: Toyota: FBX"))


def test_get_target_vehicle_names_uses_chosen_collection():
    chosen = types.SimpleNamespace(name="Body Mesh: Toyota: SideFlip: FBX")
    # A specific pick should not need the scene-wide scan.
    ns["get_hve_vehicle_names"] = lambda: (_ for _ in ()).throw(AssertionError("should not scan"))
    assert get_target_vehicle_names(_context(chosen)) == ["Toyota"]


def test_get_target_vehicle_names_falls_back_to_all_when_unset():
    ns["get_hve_vehicle_names"] = lambda: ["Toyota", "Honda"]
    assert get_target_vehicle_names(_context(None)) == ["Toyota", "Honda"]


def test_get_target_vehicle_names_falls_back_for_non_body_mesh_collection():
    ns["get_hve_vehicle_names"] = lambda: ["Toyota"]
    chosen = types.SimpleNamespace(name="Wheels: Toyota: FBX")
    assert get_target_vehicle_names(_context(chosen)) == ["Toyota"]
