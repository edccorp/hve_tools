import ast
import pathlib
import warnings

import pytest

np = pytest.importorskip("numpy")  # roadway core is numpy-vectorized; skip if absent


# Extract the bpy-free heightfield helpers from roadway_surface.py so they can
# be exercised without Blender, matching the other AST-based tests here.
module_path = pathlib.Path(__file__).resolve().parents[1] / "roadway_surface.py"
module_ast = ast.parse(module_path.read_text())

WANTED = {
    "build_grid_spec",
    "cell_indices",
    "cell_percentile_grid",
    "cell_mean_grid",
    "_shift",
    "fill_holes_grid",
    "build_mesh_arrays",
    "_color_grid",
    "generate_surface",
}

ns = {"np": np, "warnings": warnings}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANTED:
        exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), ns)

build_grid_spec = ns["build_grid_spec"]
cell_percentile_grid = ns["cell_percentile_grid"]
cell_mean_grid = ns["cell_mean_grid"]
cell_indices = ns["cell_indices"]
fill_holes_grid = ns["fill_holes_grid"]
build_mesh_arrays = ns["build_mesh_arrays"]
generate_surface = ns["generate_surface"]


def _flat_ground(step=0.1, extent=2.0):
    pts = []
    n = int(round(extent / step)) + 1
    for i in range(n):
        for j in range(n):
            pts.append((i * step, j * step, 0.0))
    return pts


def test_build_grid_spec():
    pts = [(0.0, 0.0, 5.0), (10.0, 4.0, 1.0)]
    assert build_grid_spec(pts, 1.0) == (0.0, 0.0, 11, 5)


def test_cell_percentile_ignores_overhead_and_below_ground():
    pts = _flat_ground()
    pts.append((1.0, 1.0, 5.0))    # overhead noise (e.g. a vehicle roof)
    pts.append((1.0, 1.0, -3.0))   # spurious below-ground return
    grid = cell_percentile_grid(np.array(pts), 0.0, 0.0, 3, 3, 1.0, 5.0)
    assert grid.shape == (3, 3)
    assert not np.isnan(grid).any()
    # 5th percentile sits on the dense z=0 ground, rejecting both outliers.
    assert np.nanmax(np.abs(grid)) < 0.1


def test_cell_mean_grid():
    flat = np.array([0, 0, 3])          # two points in cell 0, one in cell 3
    values = np.array([1.0, 3.0, 9.0])
    grid = cell_mean_grid(flat, values, 2, 2)
    assert grid[0, 0] == 2.0            # mean of 1 and 3
    assert grid[1, 1] == 9.0
    assert np.isnan(grid[0, 1]) and np.isnan(grid[1, 0])


def test_fill_holes_grid_fills_interior():
    grid = np.array([[1.0, 1.0, 1.0],
                     [1.0, np.nan, 1.0],
                     [1.0, 1.0, 1.0]])
    filled = fill_holes_grid(grid, max_passes=10)
    assert filled[1, 1] == 1.0
    assert not np.isnan(filled).any()


def test_build_mesh_arrays_shapes_and_skips_holes():
    z = np.array([[0.0, 0.1, 0.2],
                  [0.0, 0.1, 0.2]])
    verts, faces = build_mesh_arrays(0.0, 0.0, 1.0, z)
    assert verts.shape == (6, 3)
    assert faces.shape == (2, 4)
    # A NaN corner removes only the quad that touches it.
    z2 = np.array([[0.0, 0.0, np.nan],
                   [0.0, 0.0, 0.0]])
    _v, faces2 = build_mesh_arrays(0.0, 0.0, 1.0, z2)
    assert faces2.shape == (1, 4)


def test_generate_surface_end_to_end_with_color():
    pts = np.array(_flat_ground())
    colors = np.tile([0.2, 0.4, 0.6, 1.0], (len(pts), 1))
    result = generate_surface(pts, 1.0, 2.0, 5.0, fill_holes=True, colors=colors)
    assert result["nx"] == 3 and result["ny"] == 3
    assert result["verts"].shape[0] == 9
    assert len(result["faces"]) == 4
    # Per-vertex colours carried through and aligned with verts.
    assert result["colors"].shape == (9, 4)
    assert np.allclose(result["colors"][:, 0], 0.2)


def test_generate_surface_rejects_tiny_input():
    assert generate_surface(np.zeros((2, 3)), 1.0, 2.0, 5.0) is None
