import ast
import pathlib
import re


# Extract the bpy-free CSV-mapping helpers from xyz_importer.py (and the shared
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


_load("edr_importer.py", func_names={"normalize_header"})
_load(
    "xyz_importer.py",
    func_names={"auto_map_point_columns", "default_point_positional_mapping"},
    assign_names={"POINT_COLUMN_FIELDS", "POINT_COLUMN_KEYWORDS"},
)

auto_map_point_columns = ns["auto_map_point_columns"]
default_point_positional_mapping = ns["default_point_positional_mapping"]


def test_auto_map_point_columns_named_headers():
    headers = ["Point Number", "X", "Y", "Z", "Description"]
    mapping = auto_map_point_columns(headers)
    assert mapping == {
        "point_number": 0,
        "x": 1,
        "y": 2,
        "z": 3,
        "description": 4,
    }


def test_auto_map_point_columns_reordered_and_extra():
    headers = ["Easting", "Northing", "Elevation", "Label", "Point"]
    mapping = auto_map_point_columns(headers)
    assert mapping["x"] == 0
    assert mapping["y"] == 1
    assert mapping["z"] == 2
    assert mapping["description"] == 3
    assert mapping["point_number"] == 4


def test_auto_map_point_columns_missing_optionals():
    # Only coordinates present; point number and description are absent.
    headers = ["x", "y", "z"]
    mapping = auto_map_point_columns(headers)
    assert mapping["x"] == 0
    assert mapping["y"] == 1
    assert mapping["z"] == 2
    assert mapping["point_number"] == -1
    assert mapping["description"] == -1


def test_auto_map_point_columns_unmatched_returns_negative_one():
    headers = ["foo", "bar", "baz"]
    mapping = auto_map_point_columns(headers)
    assert mapping == {field: -1 for field in ns["POINT_COLUMN_FIELDS"]}


def test_default_point_positional_mapping_full():
    mapping = default_point_positional_mapping(5)
    assert mapping == {
        "point_number": 0,
        "x": 1,
        "y": 2,
        "z": 3,
        "description": 4,
    }


def test_default_point_positional_mapping_coords_only():
    mapping = default_point_positional_mapping(4)
    assert mapping["point_number"] == 0
    assert mapping["x"] == 1
    assert mapping["y"] == 2
    assert mapping["z"] == 3
    assert mapping["description"] == -1
