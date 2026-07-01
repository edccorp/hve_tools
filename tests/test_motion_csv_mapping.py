import ast
import pathlib
import re


# Extract the bpy-free CSV-mapping helpers from import_xyzrpy.py (and the shared
# normalize_header from edr_importer.py) so they can be exercised without
# Blender, matching the other AST-based tests in this suite.
root = pathlib.Path(__file__).resolve().parents[1]

ns = {"re": re}


def _load(module_name, func_names=(), assign_names=()):
    module_ast = ast.parse((root / module_name).read_text())
    for node in module_ast.body:
        if isinstance(node, ast.Assign):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if targets & set(assign_names):
                exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), ns)
        elif isinstance(node, ast.FunctionDef) and node.name in func_names:
            exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), ns)


# normalize_header is shared from the EDR importer.
_load("edr_importer.py", func_names={"normalize_header"})
_load(
    "import_xyzrpy.py",
    func_names={"auto_map_motion_columns", "default_motion_positional_mapping"},
    assign_names={"MOTION_COLUMN_FIELDS", "MOTION_COLUMN_KEYWORDS"},
)

auto_map_motion_columns = ns["auto_map_motion_columns"]
default_motion_positional_mapping = ns["default_motion_positional_mapping"]


def test_auto_map_motion_columns_named_headers():
    headers = ["Time (s)", "X", "Y", "Z", "Roll", "Pitch", "Yaw"]
    mapping = auto_map_motion_columns(headers)
    assert mapping == {
        "time": 0,
        "x": 1,
        "y": 2,
        "z": 3,
        "roll": 4,
        "pitch": 5,
        "yaw": 6,
    }


def test_auto_map_motion_columns_reordered_and_descriptive():
    headers = ["Yaw (deg)", "Elapsed Time", "X Position", "Y Position", "Z Position"]
    mapping = auto_map_motion_columns(headers)
    assert mapping["yaw"] == 0
    assert mapping["time"] == 1
    assert mapping["x"] == 2
    assert mapping["y"] == 3
    assert mapping["z"] == 4
    # No roll/pitch columns present.
    assert mapping["roll"] == -1
    assert mapping["pitch"] == -1


def test_auto_map_motion_columns_yaw_not_claimed_by_y():
    # The single-letter "y" keyword must not steal the Yaw column.
    headers = ["t", "x", "y", "z", "yaw"]
    mapping = auto_map_motion_columns(headers)
    assert mapping["time"] == 0
    assert mapping["x"] == 1
    assert mapping["y"] == 2
    assert mapping["z"] == 3
    assert mapping["yaw"] == 4


def test_auto_map_motion_columns_single_letter_rpy():
    # r/p map to roll/pitch even without a yaw column present.
    headers = ["Time", "X", "Y", "Z", "R", "P"]
    mapping = auto_map_motion_columns(headers)
    assert mapping["roll"] == 4
    assert mapping["pitch"] == 5
    assert mapping["yaw"] == -1


def test_auto_map_motion_columns_abbreviated_rotations_with_y():
    # X,Y,Z,R,P,Y: positional Y is claimed first, the trailing Y is yaw.
    headers = ["Time", "X", "Y", "Z", "R", "P", "Y"]
    mapping = auto_map_motion_columns(headers)
    assert mapping == {
        "time": 0,
        "x": 1,
        "y": 2,
        "z": 3,
        "roll": 4,
        "pitch": 5,
        "yaw": 6,
    }


def test_auto_map_motion_columns_unmatched_returns_negative_one():
    headers = ["foo", "bar", "baz"]
    mapping = auto_map_motion_columns(headers)
    assert mapping == {field: -1 for field in ns["MOTION_COLUMN_FIELDS"]}


def test_default_motion_positional_mapping_full():
    mapping = default_motion_positional_mapping(7)
    assert mapping == {
        "time": 0,
        "x": 1,
        "y": 2,
        "z": 3,
        "roll": 4,
        "pitch": 5,
        "yaw": 6,
    }


def test_default_motion_positional_mapping_position_only():
    mapping = default_motion_positional_mapping(4)
    assert mapping["time"] == 0
    assert mapping["x"] == 1
    assert mapping["y"] == 2
    assert mapping["z"] == 3
    assert mapping["roll"] == -1
    assert mapping["pitch"] == -1
    assert mapping["yaw"] == -1
