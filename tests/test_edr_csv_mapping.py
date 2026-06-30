import ast
import pathlib


# Extract the bpy-free CSV-mapping helpers from edr_importer.py so they can be
# exercised without Blender, matching the other AST-based tests in this suite.
module_path = pathlib.Path(__file__).resolve().parents[1] / "edr_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)

WANTED_FUNCS = {
    "normalize_header",
    "detect_header_row",
    "auto_map_columns",
    "default_positional_mapping",
}
WANTED_ASSIGNS = {"EDR_COLUMN_FIELDS", "EDR_COLUMN_KEYWORDS"}

import re  # noqa: E402  (the extracted functions reference the re module)

ns = {"re": re}
for node in module_ast.body:
    if isinstance(node, ast.Assign):
        targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if targets & WANTED_ASSIGNS:
            exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), ns)
    elif isinstance(node, ast.FunctionDef) and node.name in WANTED_FUNCS:
        exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), ns)

normalize_header = ns["normalize_header"]
detect_header_row = ns["detect_header_row"]
auto_map_columns = ns["auto_map_columns"]
default_positional_mapping = ns["default_positional_mapping"]


def test_normalize_header_strips_units_and_punctuation():
    assert normalize_header(" Yaw Rate (deg/s) ") == "yaw rate"
    assert normalize_header("Speed [mph]") == "speed"
    assert normalize_header("Steering_Wheel_Angle") == "steering wheel angle"


def test_detect_header_row_text_vs_numeric():
    assert detect_header_row(["Time", "Speed", "YawRate"]) is True
    assert detect_header_row(["0.0", "10.5", "-2.3"]) is False
    # Empty trailing cells are ignored.
    assert detect_header_row(["0.0", "10.5", ""]) is False


def test_auto_map_columns_named_headers():
    headers = ["Time (s)", "Speed (mph)", "Yaw Rate (deg/s)", "Steering Wheel Angle (deg)"]
    mapping = auto_map_columns(headers)
    assert mapping == {
        "time": 0,
        "speed": 1,
        "yaw_rate": 2,
        "steering_wheel_angle": 3,
    }


def test_auto_map_columns_handles_reordered_and_extra_columns():
    headers = ["Vehicle Speed", "Elapsed Time", "Throttle", "Steering Angle"]
    mapping = auto_map_columns(headers)
    assert mapping["speed"] == 0
    assert mapping["time"] == 1
    assert mapping["steering_wheel_angle"] == 3
    # No yaw-rate column present.
    assert mapping["yaw_rate"] == -1


def test_auto_map_columns_steering_not_claimed_by_generic_yaw():
    # The single-letter "r" yaw keyword must not steal the steering column.
    headers = ["t", "v", "steer"]
    mapping = auto_map_columns(headers)
    assert mapping["time"] == 0
    assert mapping["speed"] == 1
    assert mapping["steering_wheel_angle"] == 2
    assert mapping["yaw_rate"] == -1


def test_auto_map_columns_unmatched_returns_negative_one():
    headers = ["foo", "bar", "baz"]
    mapping = auto_map_columns(headers)
    assert mapping == {
        "time": -1,
        "speed": -1,
        "yaw_rate": -1,
        "steering_wheel_angle": -1,
    }


def test_default_positional_mapping_yaw_mode():
    mapping = default_positional_mapping(3, "YAW_RATE")
    assert mapping["time"] == 0
    assert mapping["speed"] == 1
    assert mapping["yaw_rate"] == 2
    assert mapping["steering_wheel_angle"] == -1


def test_default_positional_mapping_steering_mode():
    mapping = default_positional_mapping(3, "STEERING_WHEEL_ANGLE")
    assert mapping["steering_wheel_angle"] == 2
    assert mapping["yaw_rate"] == -1


def test_default_positional_mapping_two_columns_only():
    mapping = default_positional_mapping(2, "YAW_RATE")
    assert mapping["time"] == 0
    assert mapping["speed"] == 1
    assert mapping["yaw_rate"] == -1
