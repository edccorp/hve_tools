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
    "bake_point_color_texture",
    "grid_uvs",
    "voxel_downsample",
    "statistical_outlier_mask",
    "mask_points_near_ground",
    "convex_hull_2d",
    "points_in_convex_polygon",
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
bake_point_color_texture = ns["bake_point_color_texture"]
grid_uvs = ns["grid_uvs"]
voxel_downsample = ns["voxel_downsample"]
statistical_outlier_mask = ns["statistical_outlier_mask"]
mask_points_near_ground = ns["mask_points_near_ground"]
convex_hull_2d = ns["convex_hull_2d"]
points_in_convex_polygon = ns["points_in_convex_polygon"]


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


def test_voxel_downsample_averages_per_voxel():
    # Two points inside the same 1.0 3D voxel, one far away -> two output points.
    pts = np.array([(0.1, 0.1, 0.1), (0.9, 0.9, 0.9), (5.0, 5.0, 5.0)])
    cols = np.array([(1.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0), (0.0, 1.0, 0.0, 1.0)])
    ds_pts, ds_cols = voxel_downsample(pts, cols, 1.0)
    assert ds_pts.shape[0] == 2
    # The merged voxel is the average of its two points.
    merged = ds_pts[np.argmin(ds_pts[:, 0])]
    assert np.allclose(merged, [0.5, 0.5, 0.5])
    assert ds_cols.shape == (2, 4)


def test_voxel_downsample_noop_without_size():
    pts = np.array([(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)])
    ds_pts, ds_cols = voxel_downsample(pts, None, 0.0)
    assert ds_pts.shape == (2, 3)
    assert ds_cols is None


def test_statistical_outlier_mask_drops_far_point():
    # One clearly-distant mean distance is rejected; the tight cluster is kept.
    dists = np.array([1.0, 1.1, 0.9, 1.0, 10.0])
    keep = statistical_outlier_mask(dists, ratio=1.0)
    assert keep[:4].all()
    assert not keep[4]


def test_mask_points_near_ground():
    z_grid = np.zeros((2, 2))  # flat ground at z=0 over a 2x2 grid
    pts = np.array([
        (0.1, 0.1, 0.05),   # on the road
        (0.1, 0.1, 3.0),    # overhead (e.g. a vehicle)
        (1.0, 1.0, -0.1),   # slightly below ground (noise, within band)
    ])
    keep = mask_points_near_ground(pts, z_grid, 0.0, 0.0, 1.0, 0.25)
    assert keep.tolist() == [True, False, True]


def test_color_height_tolerance_excludes_overhead_color():
    # Dense white ground plus a red point 5m above the middle.
    pts = _flat_ground()
    colors = [(1.0, 1.0, 1.0, 1.0)] * len(pts)
    pts.append((1.0, 1.0, 5.0))
    colors.append((1.0, 0.0, 0.0, 1.0))
    pts = np.array(pts)
    colors = np.array(colors)

    tainted = generate_surface(pts, 1.0, 2.0, 5.0, colors=colors, color_height_tol=0.0)
    clean = generate_surface(pts, 1.0, 2.0, 5.0, colors=colors, color_height_tol=0.5)

    # Without the tolerance the red overhead point tints its cell; with it,
    # every surface colour stays white.
    assert tainted["colors"][:, 1].min() < 0.999
    assert np.allclose(clean["colors"], 1.0)


def test_generate_surface_rejects_tiny_input():
    assert generate_surface(np.zeros((2, 3)), 1.0, 2.0, 5.0) is None


def test_bake_texture_resolution_independent_of_grid():
    # A tiny 3x3 grid (cell 1.0) but a dense red point cloud -> a bigger texture
    # sampled from the points, not the 3x3 grid.
    pts = []
    colors = []
    x = 0.0
    while x <= 2.0:
        y = 0.0
        while y <= 2.0:
            pts.append((x, y, 0.0))
            colors.append((1.0, 0.0, 0.0, 1.0))
            y += 0.05
        x += 0.05
    pixels, w, h = bake_point_color_texture(
        np.array(pts), np.array(colors), 0.0, 0.0, 1.0, 3, 3, target_size=64
    )
    # Covered extent is square ((nx-1)*cell == (ny-1)*cell), so 64x64.
    assert (w, h) == (64, 64)
    assert len(pixels) == 64 * 64 * 4
    # Everything sampled red.
    px = np.asarray(pixels).reshape(-1, 4)
    assert np.allclose(px[:, 0], 1.0)
    assert np.allclose(px[:, 1], 0.0)


def test_bake_texture_matches_grid_when_target_zero():
    pts = np.array([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)])
    cols = np.tile([0.3, 0.4, 0.5, 1.0], (4, 1))
    pixels, w, h = bake_point_color_texture(pts, cols, 0.0, 0.0, 1.0, 2, 2, target_size=0)
    assert (w, h) == (2, 2)
    assert len(pixels) == 2 * 2 * 4


def test_grid_uvs_corners():
    uv = grid_uvs(3, 2)
    assert uv.shape == (6, 2)
    assert tuple(uv[0]) == (0.0, 0.0)
    assert tuple(uv[2]) == (1.0, 0.0)
    assert tuple(uv[3]) == (0.0, 1.0)
    assert tuple(uv[5]) == (1.0, 1.0)


# --- Convex-hull clip (surface only points inside a boundary object) ---------

def test_convex_hull_of_square():
    # Interior point should be dropped from the hull; corners kept.
    pts = [(0, 0), (2, 0), (2, 2), (0, 2), (1, 1)]
    hull = convex_hull_2d(pts)
    assert hull.shape == (4, 2)
    corners = {tuple(p) for p in hull.tolist()}
    assert corners == {(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)}


def test_convex_hull_degenerate_is_empty():
    assert convex_hull_2d([(0, 0), (1, 1)]).shape == (0, 2)
    assert convex_hull_2d([(0, 0), (1, 1), (2, 2)]).shape == (0, 2)  # collinear


def test_points_in_convex_polygon_square():
    hull = convex_hull_2d([(0, 0), (4, 0), (4, 4), (0, 4)])
    pts = np.array([
        [2.0, 2.0],   # inside
        [0.0, 0.0],   # on a corner -> inside
        [4.0, 2.0],   # on an edge -> inside
        [5.0, 2.0],   # outside
        [-1.0, -1.0],  # outside
    ])
    mask = points_in_convex_polygon(pts, hull)
    assert mask.tolist() == [True, True, True, False, False]


def test_points_in_empty_hull_keeps_all():
    pts = np.array([[0.0, 0.0], [9.0, 9.0]])
    mask = points_in_convex_polygon(pts, np.empty((0, 2)))
    assert mask.all()


def test_clip_filters_a_cloud_to_boundary():
    # A 5x5 grid of points, clipped to the lower-left 2x2 region.
    xs = np.arange(5.0)
    pts = np.array([[x, y] for x in xs for y in xs])
    hull = convex_hull_2d([(0, 0), (2, 0), (2, 2), (0, 2)])
    keep = points_in_convex_polygon(pts, hull)
    kept = pts[keep]
    assert kept.min() >= 0.0 and kept[:, 0].max() <= 2.0 and kept[:, 1].max() <= 2.0
    # 3x3 lattice of integer points lies within [0,2]x[0,2].
    assert keep.sum() == 9
