import ast
import pathlib
import re


module_path = pathlib.Path(__file__).resolve().parents[1] / "export_vehicle.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {"re": re}

for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {
        "get_vehicle_light_type",
        "extract_switch_material_names",
        "get_vehicle_light_switch_text",
        "clean_def",
        "find_material_by_switch_id",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

get_vehicle_light_type = ns["get_vehicle_light_type"]
extract_switch_material_names = ns["extract_switch_material_names"]
get_vehicle_light_switch_text = ns["get_vehicle_light_switch_text"]
find_material_by_switch_id = ns["find_material_by_switch_id"]


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


class Material:
    def __init__(self, name):
        self.name = name


def test_extract_switch_material_names_returns_all_use_entries():
    light_text = (
        "DEF A Switch {USE LIGHT_WHITE_LO}\n"
        "DEF B Switch {USE LIGHT_WHITE_HI}\n"
    )

    assert extract_switch_material_names(light_text) == ["LIGHT_WHITE_LO", "LIGHT_WHITE_HI"]


def test_find_material_by_switch_id_matches_cleaned_material_name():
    material = Material("LIGHT_RED_HI.001")

    matched = find_material_by_switch_id([material], "LIGHT_RED_HI_001")

    assert matched is material


def test_find_material_by_switch_id_matches_exact_material_name():
    material = Material("LIGHT_RED_HI")

    matched = find_material_by_switch_id([material], "LIGHT_RED_HI")

    assert matched is material


def test_get_vehicle_light_switch_text_for_headlight_left_contains_low_and_high():
    light_text = get_vehicle_light_switch_text("HVE_HEADLIGHT_LEFT")

    assert "{USE LIGHT_WHITE_LO}" in light_text
    assert "{USE LIGHT_WHITE_HI}" in light_text


def test_get_vehicle_light_switch_text_unknown_type_returns_empty_string():
    assert get_vehicle_light_switch_text("UNKNOWN") == ""
