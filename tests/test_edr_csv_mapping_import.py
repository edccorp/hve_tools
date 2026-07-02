import ast
import csv
import pathlib
import tempfile


# Extract import_mapped_csv_data (and the helpers it depends on) so the
# end-to-end mapping/parsing can be tested without Blender, using mock objects.
module_path = pathlib.Path(__file__).resolve().parents[1] / "motion_data_tools" / "edr_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)

WANTED = {
    "get_target_object",
    "get_vehicle_path_entries",
    "import_mapped_csv_data",
}

ns = {"csv": csv}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANTED:
        exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), ns)

import_mapped_csv_data = ns["import_mapped_csv_data"]


class MockEntry:
    def __init__(self):
        self.time = 0.0
        self.speed = 0.0
        self.yaw_rate = 0.0
        self.steering_wheel_angle = 0.0


class MockEntries(list):
    def add(self):
        entry = MockEntry()
        self.append(entry)
        return entry

    def clear(self):
        del self[:]


class MockObject:
    def __init__(self):
        self.name = "MockTarget"
        self.vehicle_path_entries = MockEntries()


class MockAnimSettings:
    def __init__(self, target):
        self.edr_anim_object = target


class MockScene:
    def __init__(self, target):
        self.anim_settings = MockAnimSettings(target)
        self.frame_start = 99


class MockContext:
    def __init__(self, target):
        self.scene = MockScene(target)
        self.object = target


def _write_csv(rows):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="")
    writer = csv.writer(tmp)
    for row in rows:
        writer.writerow(row)
    tmp.close()
    return tmp.name


def test_import_maps_all_columns_with_header():
    path = _write_csv([
        ["Time", "Speed", "YawRate", "Steering"],
        [0.0, 10.0, 1.0, 5.0],
        [1.0, 12.0, 2.0, 6.0],
    ])
    target = MockObject()
    context = MockContext(target)
    mapping = {"time": 0, "speed": 1, "yaw_rate": 2, "steering_wheel_angle": 3}

    count, error = import_mapped_csv_data(path, mapping, True, context)

    assert error is None
    assert count == 2
    entries = target.vehicle_path_entries
    assert entries[0].time == 0.0 and entries[0].speed == 10.0
    assert entries[0].yaw_rate == 1.0 and entries[0].steering_wheel_angle == 5.0
    assert entries[1].time == 1.0 and entries[1].steering_wheel_angle == 6.0
    assert context.scene.frame_start == 0


def test_import_reordered_columns_and_optional_missing():
    # Columns out of order; no steering column present (mapped to -1).
    path = _write_csv([
        ["YawRate", "Time", "Speed"],
        [0.5, 0.0, 20.0],
        [0.6, 0.5, 22.0],
    ])
    target = MockObject()
    context = MockContext(target)
    mapping = {"time": 1, "speed": 2, "yaw_rate": 0, "steering_wheel_angle": -1}

    count, error = import_mapped_csv_data(path, mapping, True, context)

    assert error is None and count == 2
    entries = target.vehicle_path_entries
    assert entries[0].time == 0.0 and entries[0].speed == 20.0
    assert entries[0].yaw_rate == 0.5
    # Unmapped steering stays at its default of 0.0.
    assert entries[0].steering_wheel_angle == 0.0


def test_import_requires_time_and_speed():
    path = _write_csv([["Time", "Speed"], [0.0, 10.0]])
    context = MockContext(MockObject())
    mapping = {"time": -1, "speed": 1, "yaw_rate": -1, "steering_wheel_angle": -1}

    count, error = import_mapped_csv_data(path, mapping, True, context)

    assert count == 0
    assert "Time column" in error and "Speed column" in error


def test_import_negative_time_is_offset_to_zero():
    path = _write_csv([
        ["Time", "Speed", "YawRate"],
        [-0.5, 10.0, 0.0],
        [0.5, 12.0, 0.0],
    ])
    target = MockObject()
    context = MockContext(target)
    mapping = {"time": 0, "speed": 1, "yaw_rate": 2, "steering_wheel_angle": -1}

    count, error = import_mapped_csv_data(path, mapping, True, context)

    assert error is None and count == 2
    entries = target.vehicle_path_entries
    assert entries[0].time == 0.0
    assert entries[1].time == 1.0


def test_import_skips_non_numeric_rows():
    path = _write_csv([
        ["Time", "Speed", "YawRate"],
        [0.0, 10.0, 1.0],
        ["bad", "row", "here"],
        [1.0, 12.0, 2.0],
    ])
    target = MockObject()
    context = MockContext(target)
    mapping = {"time": 0, "speed": 1, "yaw_rate": 2, "steering_wheel_angle": -1}

    count, error = import_mapped_csv_data(path, mapping, True, context)

    assert error is None
    assert count == 2
