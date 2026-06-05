import ast
import math
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / "speed_accel.py"
source = module_path.read_text()
module_ast = ast.parse(source)

ns = {}
for node in module_ast.body:
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id
        in {
            "FEET_PER_SECOND_TO_MPH",
            "METERS_PER_SECOND_TO_MPH",
            "METERS_PER_SECOND_SQUARED_TO_G",
            "FEET_PER_SECOND_SQUARED_TO_G",
        }
    ) or (isinstance(node, ast.FunctionDef) and node.name == "get_unit_conversions"):
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

get_unit_conversions = ns["get_unit_conversions"]


class UnitSettings:
    def __init__(self, system="METRIC", scale_length=1.0):
        self.system = system
        self.scale_length = scale_length


class Scene:
    def __init__(self, system="METRIC", scale_length=1.0):
        self.unit_settings = UnitSettings(system, scale_length)


def test_auto_units_convert_blender_units_with_scene_scale_to_mph_and_g():
    speed_to_mph, accel_to_g, resolved_mode = get_unit_conversions(
        Scene(system="IMPERIAL", scale_length=1.0),
        "AUTO",
    )

    assert resolved_mode == "SCENE"
    assert math.isclose(speed_to_mph, 2.2369362921)
    assert math.isclose(accel_to_g, 1.0 / 9.80665)


def test_auto_units_honor_feet_scaled_scene():
    speed_to_mph, accel_to_g, resolved_mode = get_unit_conversions(
        Scene(system="IMPERIAL", scale_length=0.3048),
        "AUTO",
    )

    assert resolved_mode == "SCENE"
    assert math.isclose(speed_to_mph, 3600.0 / 5280.0, rel_tol=1e-9)
    assert math.isclose(accel_to_g, 0.3048 / 9.80665, rel_tol=1e-9)


def test_explicit_feet_units_keep_feet_per_second_conversion():
    speed_to_mph, accel_to_g, resolved_mode = get_unit_conversions(
        Scene(system="METRIC", scale_length=1.0),
        "FEET",
    )

    assert resolved_mode == "FEET"
    assert math.isclose(speed_to_mph, 3600.0 / 5280.0)
    assert math.isclose(accel_to_g, 1.0 / 32.174)
