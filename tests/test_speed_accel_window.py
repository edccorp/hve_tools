import ast
import pathlib

module_path = pathlib.Path(__file__).resolve().parents[1] / "speed_accel.py"
source = module_path.read_text()
module_ast = ast.parse(source)

ns = {}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {
        "normalize_window_frames",
        "get_window_for_frame",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

normalize_window_frames = ns["normalize_window_frames"]
get_window_for_frame = ns["get_window_for_frame"]


def test_window_frames_are_sample_count_not_frame_duration():
    assert get_window_for_frame(10, 1, 20, 3) == (9, 11)


def test_centered_window_shifts_at_start_and_end():
    assert get_window_for_frame(1, 1, 20, 3) == (1, 3)
    assert get_window_for_frame(20, 1, 20, 3) == (18, 20)


def test_one_frame_window_uses_nearest_two_samples():
    assert normalize_window_frames(1) == 2
    assert get_window_for_frame(10, 1, 20, 1) == (10, 11)
    assert get_window_for_frame(20, 1, 20, 1) == (19, 20)
