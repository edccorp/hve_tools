import ast
import pathlib

import pytest

np = pytest.importorskip("numpy")


# Extract the bpy-free helper from surface_reconstruct.py without importing the
# module (which pulls in bpy and roadway_surface).
module_path = pathlib.Path(__file__).resolve().parents[1] / "surface_reconstruct.py"
module_ast = ast.parse(module_path.read_text())

ns = {"np": np}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == "ball_pivoting_radii":
        exec(compile(ast.Module([node], []), "<ast>", "exec"), ns)

ball_pivoting_radii = ns["ball_pivoting_radii"]


def test_ball_pivoting_radii_scales_with_spacing():
    radii = ball_pivoting_radii(2.0, multipliers=(1.0, 2.0))
    assert radii == [2.0, 4.0]


def test_ball_pivoting_radii_defaults_are_increasing():
    radii = ball_pivoting_radii(0.5)
    assert len(radii) == 3
    assert radii == sorted(radii)
    assert all(r > 0 for r in radii)


def test_ball_pivoting_radii_handles_zero_spacing():
    assert ball_pivoting_radii(0.0) == [0.0, 0.0, 0.0]
    # Negative spacing is clamped to 0 rather than producing negative radii.
    assert ball_pivoting_radii(-3.0) == [0.0, 0.0, 0.0]
