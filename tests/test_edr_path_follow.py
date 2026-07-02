import ast
import math
import pathlib


# Extract the pure (bpy-free) path-following helpers from edr_importer.py so
# they can be exercised without Blender, matching the other AST-based tests.
module_path = pathlib.Path(__file__).resolve().parents[1] / "motion_data_tools" / "edr_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)

WANTED = {
    "_vector_sub",
    "order_vertices_along_edges",
    "cumulative_path_lengths",
    "cumulative_distance_from_speed",
    "distance_at_time",
    "sample_point_on_path",
}

ns = {"math": math}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANTED:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

order_vertices_along_edges = ns["order_vertices_along_edges"]
cumulative_path_lengths = ns["cumulative_path_lengths"]
cumulative_distance_from_speed = ns["cumulative_distance_from_speed"]
distance_at_time = ns["distance_at_time"]
sample_point_on_path = ns["sample_point_on_path"]


def test_order_vertices_open_polyline_starts_at_endpoint():
    # Edges given out of order; chain is 0-1-2-3.
    edges = [(2, 3), (0, 1), (1, 2)]
    assert order_vertices_along_edges(edges, 4) == [0, 1, 2, 3]


def test_order_vertices_closed_loop_visits_all():
    edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    order = order_vertices_along_edges(edges, 4)
    assert sorted(order) == [0, 1, 2, 3]
    assert order[0] == 0


def test_cumulative_path_lengths_straight_line():
    points = [(0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (3.0, 4.0, 0.0)]
    cum = cumulative_path_lengths(points)
    assert cum == [0.0, 3.0, 7.0]


def test_cumulative_distance_constant_speed():
    # Constant 10 m/s for 2 s -> 20 m total.
    time_arr = [0.0, 1.0, 2.0]
    speed_arr = [10.0, 10.0, 10.0]
    cum = cumulative_distance_from_speed(time_arr, speed_arr)
    assert cum == [0.0, 10.0, 20.0]


def test_distance_at_time_accelerating_segment():
    # Speed ramps 0 -> 10 m/s over 2 s: distance at t=2 is 0.5*10*2 = 10 m.
    time_arr = [0.0, 2.0]
    speed_arr = [0.0, 10.0]
    cum = cumulative_distance_from_speed(time_arr, speed_arr)
    # Halfway through (t=1) speed is 5 m/s, distance = 0.5 * 5 * 1 = 2.5 m.
    assert math.isclose(distance_at_time(time_arr, speed_arr, cum, 1.0), 2.5)
    assert math.isclose(distance_at_time(time_arr, speed_arr, cum, 2.0), 10.0)


def test_distance_at_time_clamps_outside_range():
    time_arr = [0.0, 1.0]
    speed_arr = [4.0, 4.0]
    cum = cumulative_distance_from_speed(time_arr, speed_arr)
    assert distance_at_time(time_arr, speed_arr, cum, -5.0) == 0.0
    assert math.isclose(distance_at_time(time_arr, speed_arr, cum, 99.0), 4.0)


def test_sample_point_on_path_midpoint_and_tangent():
    points = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0)]
    cum = cumulative_path_lengths(points)  # [0, 10, 20]

    # 5 m along -> halfway down the first segment.
    point, tangent = sample_point_on_path(points, cum, 5.0)
    assert math.isclose(point[0], 5.0)
    assert math.isclose(point[1], 0.0)
    assert tangent == (10.0, 0.0, 0.0)

    # 15 m along -> halfway up the second segment.
    point, tangent = sample_point_on_path(points, cum, 15.0)
    assert math.isclose(point[0], 10.0)
    assert math.isclose(point[1], 5.0)
    assert tangent == (0.0, 10.0, 0.0)


def test_sample_point_on_path_clamps_to_ends():
    points = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    cum = cumulative_path_lengths(points)
    start, _ = sample_point_on_path(points, cum, -1.0)
    end, _ = sample_point_on_path(points, cum, 100.0)
    assert start == (0.0, 0.0, 0.0)
    assert end == (10.0, 0.0, 0.0)
