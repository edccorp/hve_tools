import ast
import math
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / "motionpaths.py"
source = module_path.read_text()
module_ast = ast.parse(source)

ns = {"math": math}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {
        "iter_marker_frame_times",
        "split_frame_value",
        "get_marker_relative_seconds",
        "format_marker_relative_time",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

iter_marker_frame_times = ns["iter_marker_frame_times"]
split_frame_value = ns["split_frame_value"]
get_marker_relative_seconds = ns["get_marker_relative_seconds"]
format_marker_relative_time = ns["format_marker_relative_time"]


def test_iter_marker_frame_times_uses_seconds_and_scene_fps():
    frames = list(iter_marker_frame_times(1, 61, 30.0, 1.0))

    assert frames == [1.0, 31.0, 61.0]


def test_iter_marker_frame_times_clamps_tiny_intervals_to_one_frame():
    frames = list(iter_marker_frame_times(10, 12, 24.0, 0.0))

    assert frames == [10.0, 11.0, 12.0]


def test_iter_marker_frame_times_steps_backward_and_forward_from_zero_frame():
    frames = list(iter_marker_frame_times(1, 61, 30.0, 1.0, zero_frame=31))

    assert frames == [1.0, 31.0, 61.0]


def test_iter_marker_frame_times_omits_bounds_that_are_not_on_zero_interval():
    frames = list(iter_marker_frame_times(1, 70, 10.0, 2.0, zero_frame=30))

    assert frames == [10.0, 30.0, 50.0, 70.0]


def test_split_frame_value_returns_subframe_for_fractional_intervals():
    frame, subframe = split_frame_value(12.5)

    assert frame == 12
    assert math.isclose(subframe, 0.5)


def test_get_marker_relative_seconds_uses_zero_frame_and_fps():
    relative_seconds = get_marker_relative_seconds(61, 31, 30.0)

    assert math.isclose(relative_seconds, 1.0)


def test_format_marker_relative_time_includes_sign_and_seconds():
    assert format_marker_relative_time(-1.5) == "-1.50s"
    assert format_marker_relative_time(0.0) == "+0.00s"
    assert format_marker_relative_time(1.5) == "+1.50s"
