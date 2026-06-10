import ast
import math
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / "motionpaths.py"
source = module_path.read_text()
module_ast = ast.parse(source)



class StubVector:
    def __init__(self, values):
        self.x, self.y, self.z = (float(value) for value in values)

    def __add__(self, other):
        return StubVector((self.x + other.x, self.y + other.y, self.z + other.z))

    def __sub__(self, other):
        return StubVector((self.x - other.x, self.y - other.y, self.z - other.z))

    def __mul__(self, scalar):
        return StubVector((self.x * scalar, self.y * scalar, self.z * scalar))

    __rmul__ = __mul__

    def __iter__(self):
        yield self.x
        yield self.y
        yield self.z

    @property
    def length(self):
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalize(self):
        length = self.length
        self.x /= length
        self.y /= length
        self.z /= length


def face_normal_z(vertices):
    first, second, third = vertices[:3]
    edge_a = second - first
    edge_b = third - first
    return (edge_a.x * edge_b.y) - (edge_a.y * edge_b.x)


ns = {"math": math, "Vector": StubVector}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {
        "iter_marker_frame_times",
        "split_frame_value",
        "get_marker_relative_seconds",
        "format_marker_relative_time",
        "get_marker_lateral_direction",
        "build_triangle_marker_vertices",
        "build_circle_marker_vertices",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

iter_marker_frame_times = ns["iter_marker_frame_times"]
split_frame_value = ns["split_frame_value"]
get_marker_relative_seconds = ns["get_marker_relative_seconds"]
format_marker_relative_time = ns["format_marker_relative_time"]
build_triangle_marker_vertices = ns["build_triangle_marker_vertices"]
build_circle_marker_vertices = ns["build_circle_marker_vertices"]


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


def test_triangle_marker_is_forward_of_center_with_upward_normal():
    location = StubVector((10.0, 20.0, 0.0))
    forward = StubVector((0.0, 1.0, 0.0))

    vertices = build_triangle_marker_vertices(location, forward, 2.0)

    assert len(vertices) == 3
    assert all(vertex.y > location.y for vertex in vertices)
    assert face_normal_z(vertices) > 0.0


def test_circle_marker_is_centered_at_sample_origin_with_upward_normal():
    location = StubVector((10.0, 20.0, 0.0))
    forward = StubVector((0.0, 1.0, 0.0))

    vertices = build_circle_marker_vertices(location, forward, 2.0, segments=8)

    assert len(vertices) == 8
    assert math.isclose(sum(vertex.x for vertex in vertices) / len(vertices), location.x)
    assert math.isclose(sum(vertex.y for vertex in vertices) / len(vertices), location.y)
    assert math.isclose(vertices[0].x, location.x + 0.44)
    assert math.isclose(vertices[0].y, location.y)
    assert face_normal_z(vertices) > 0.0


def test_generated_markers_build_circle_and_forward_triangle_faces():
    assert 'circle_verts = build_circle_marker_vertices(location, forward, marker_size)' in source
    assert 'faces.append(tuple(range(circle_start_index, circle_start_index + len(circle_verts))))' in source
    assert 'faces.append((triangle_start_index, triangle_start_index + 1, triangle_start_index + 2))' in source


def test_generated_markers_are_configured_as_overlay_environment_objects():
    assert 'OVERLAY_MARKERS_LABEL = "Markers"' in source
    assert 'hve_type.type = "ENVIRONMENT"' in source
    assert 'env_props.poSurfaceType = "EdTypeOther"' in source
    assert 'env_props.polabel = OVERLAY_MARKERS_LABEL' in source


def test_generated_markers_and_labels_receive_overlay_materials():
    assert 'MARKER_MATERIAL_NAME = "HVE_Overlay_Markers"' in source
    assert 'TEXT_MATERIAL_NAME = "BLACK"' in source
    assert 'get_or_create_overlay_material(MARKER_MATERIAL_NAME, MARKER_MATERIAL_COLOR)' in source
    assert 'get_or_create_overlay_material(TEXT_MATERIAL_NAME, TEXT_MATERIAL_COLOR)' in source


def test_marker_cleanup_removes_meshes_and_text_curves_from_matching_collections():
    assert "old_type = old_obj.type" in source
    assert "if old_type == 'MESH':" in source
    assert "bpy.data.meshes.remove(old_data)" in source
    assert "elif old_type in {'CURVE', 'FONT'}:" in source
    assert "bpy.data.curves.remove(old_data)" in source
