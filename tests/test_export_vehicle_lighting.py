import ast
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / "export_vehicle.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {}

for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == "get_vehicle_light_type":
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

get_vehicle_light_type = ns["get_vehicle_light_type"]


class Obj:
    pass


class MakeLight:
    def __init__(self, type_value):
        self.type = type_value


class VehicleLight:
    def __init__(self, type_value):
        self.make_light = MakeLight(type_value)


def test_get_vehicle_light_type_from_pointer_property_object():
    obj = Obj()
    obj.hve_vehicle_light = VehicleLight("HVE_HEADLIGHT_LEFT")

    assert get_vehicle_light_type(obj) == "HVE_HEADLIGHT_LEFT"


def test_get_vehicle_light_type_missing_property_returns_none():
    obj = Obj()

    assert get_vehicle_light_type(obj) is None
