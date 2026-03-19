import ast
import math
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / "fbx_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {"math": math}

for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {
        "max_vertex_deviation",
        "interpolated_sample",
        "select_adaptive_sample_indices",
        "trim_sample_indices",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)


max_vertex_deviation = ns["max_vertex_deviation"]
interpolated_sample = ns["interpolated_sample"]
select_adaptive_sample_indices = ns["select_adaptive_sample_indices"]
trim_sample_indices = ns["trim_sample_indices"]


def test_max_vertex_deviation_returns_largest_distance():
    sample_a = [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)]
    sample_b = [(3.0, 4.0, 0.0), (1.0, 0.0, 0.0)]
    assert max_vertex_deviation(sample_a, sample_b) == 5.0


def test_select_adaptive_sample_indices_skips_linear_motion():
    frames = [0, 1, 2, 3]
    samples = [
        [(0.0, 0.0, 0.0)],
        [(1.0, 0.0, 0.0)],
        [(2.0, 0.0, 0.0)],
        [(3.0, 0.0, 0.0)],
    ]

    assert select_adaptive_sample_indices(frames, samples, tolerance=0.01) == [0, 3]


def test_select_adaptive_sample_indices_keeps_non_linear_motion():
    frames = [0, 1, 2, 3]
    samples = [
        [(0.0, 0.0, 0.0)],
        [(1.0, 0.0, 0.0)],
        [(4.0, 0.0, 0.0)],
        [(3.0, 0.0, 0.0)],
    ]

    assert select_adaptive_sample_indices(frames, samples, tolerance=0.25) == [0, 1, 2, 3]


def test_trim_sample_indices_removes_low_error_intermediates_first():
    frames = [0, 1, 2, 3, 4]
    samples = [
        [(0.0, 0.0, 0.0)],
        [(0.5, 0.0, 0.0)],
        [(1.0, 0.0, 0.0)],
        [(2.5, 0.0, 0.0)],
        [(4.0, 0.0, 0.0)],
    ]

    trimmed = trim_sample_indices(frames, samples, [0, 1, 2, 3, 4], max_samples=3)
    assert trimmed == [0, 2, 4]


def test_interpolated_sample_reconstructs_midpoint():
    midpoint = interpolated_sample(
        [(0.0, 0.0, 0.0), (2.0, 2.0, 2.0)],
        [(2.0, 2.0, 2.0), (4.0, 4.0, 4.0)],
        0.5,
    )
    assert midpoint == [(1.0, 1.0, 1.0), (3.0, 3.0, 3.0)]
