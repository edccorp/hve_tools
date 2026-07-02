import ast
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / "motion_data_tools" / "speed_accel.py"
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
            "PROP_AVG_V",
            "PROP_AVG_U",
            "PROP_FWD_A",
            "PROP_LAT_A",
            "PROP_VERT_A",
        }
    ) or (isinstance(node, ast.FunctionDef) and node.name == "get_output_props"):
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

get_output_props = ns["get_output_props"]


def test_output_props_include_acceleration_by_default():
    assert get_output_props() == [
        "avg_speed_mph",
        "avg_forward_speed_mph",
        "forward_accel_g",
        "lateral_accel_g",
        "vertical_accel_g",
    ]


def test_output_props_can_skip_acceleration():
    assert get_output_props(include_acceleration=False) == [
        "avg_speed_mph",
        "avg_forward_speed_mph",
    ]
