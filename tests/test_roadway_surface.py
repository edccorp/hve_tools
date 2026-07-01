import ast
import math
import pathlib


# Extract the bpy-free heightfield helpers from roadway_surface.py so they can
# be exercised without Blender, matching the other AST-based tests here.
module_path = pathlib.Path(__file__).resolve().parents[1] / "roadway_surface.py"
module_ast = ast.parse(module_path.read_text())

WANTED = {
    "compute_xy_bounds",
    "grid_dimensions",
    "percentile",
    "_build_xy_bins",
    "_neighbor_z",
    "sample_heightfield",
    "fill_missing_heights",
    "build_surface_mesh",
}

ns = {"math": math}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANTED:
        exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), ns)

compute_xy_bounds = ns["compute_xy_bounds"]
grid_dimensions = ns["grid_dimensions"]
percentile = ns["percentile"]
sample_heightfield = ns["sample_heightfield"]
fill_missing_heights = ns["fill_missing_heights"]
build_surface_mesh = ns["build_surface_mesh"]


def test_compute_xy_bounds():
    pts = [(0.0, 0.0, 5.0), (2.0, 3.0, -1.0), (-1.0, 1.0, 0.0)]
    assert compute_xy_bounds(pts) == (-1.0, 0.0, 2.0, 3.0)
    assert compute_xy_bounds([]) is None


def test_grid_dimensions():
    assert grid_dimensions(0.0, 0.0, 10.0, 4.0, 1.0) == (11, 5)
    # Degenerate span still yields a minimum 2x2 grid.
    assert grid_dimensions(0.0, 0.0, 0.0, 0.0, 1.0) == (2, 2)


def test_percentile():
    assert percentile([0.0, 10.0], 50.0) == 5.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.0) == 1.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 100.0) == 4.0
    assert percentile([7.0], 5.0) == 7.0


def test_sample_heightfield_takes_ground_and_ignores_overhead():
    # Dense flat ground at z=0 over a 2x2 area, plus one overhead outlier.
    pts = []
    i = 0
    while i <= 8:
        j = 0
        while j <= 8:
            pts.append((i * 0.25, j * 0.25, 0.0))
            j += 1
        i += 1
    pts.append((1.0, 1.0, 5.0))  # overhead noise (e.g. a vehicle)

    sample = sample_heightfield(pts, cell_size=1.0, search_radius=0.75, ground_percentile=5.0)
    assert sample["nx"] == 3 and sample["ny"] == 3
    # Every cell sampled, and the low percentile rejects the z=5 outlier.
    for z in sample["z_grid"]:
        assert z is not None
        assert abs(z) < 0.1


def test_sample_heightfield_empty():
    assert sample_heightfield([], 1.0, 1.0, 5.0) is None


def test_fill_missing_heights_fills_interior_hole():
    # 3x3 grid, center missing; neighbours average to 1.0.
    grid = [1.0, 1.0, 1.0,
            1.0, None, 1.0,
            1.0, 1.0, 1.0]
    filled = fill_missing_heights(grid, 3, 3)
    assert filled[4] == 1.0
    assert all(v is not None for v in filled)


def test_build_surface_mesh_full_grid():
    sample = {
        "origin_x": 0.0, "origin_y": 0.0, "cell_size": 1.0,
        "nx": 3, "ny": 2,
        "z_grid": [0.0, 0.1, 0.2, 0.0, 0.1, 0.2],
    }
    verts, faces, filled, total = build_surface_mesh(sample, fill_holes=False)
    assert len(verts) == 6          # nx * ny
    assert len(faces) == 2          # (nx-1) * (ny-1)
    assert filled == 6 and total == 6
    # Vertex XY positions follow the grid; Z carries the sampled heights.
    assert verts[0] == (0.0, 0.0, 0.0)
    assert verts[2] == (2.0, 0.0, 0.2)


def test_build_surface_mesh_skips_faces_with_missing_corner():
    sample = {
        "origin_x": 0.0, "origin_y": 0.0, "cell_size": 1.0,
        "nx": 3, "ny": 2,
        "z_grid": [0.0, 0.0, None, 0.0, 0.0, 0.0],
    }
    # Without hole filling, the quad touching the None corner is skipped.
    _verts, faces, _filled, _total = build_surface_mesh(sample, fill_holes=False)
    assert len(faces) == 1
