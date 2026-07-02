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
    "clip_box_axis_count",
    "points_in_local_box",
    "_clip_box_epsilon",
    "points_in_mesh_volume",
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
clip_box_axis_count = ns["clip_box_axis_count"]
points_in_local_box = ns["points_in_local_box"]
points_in_mesh_volume = ns["points_in_mesh_volume"]


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


# --- Oriented-box clip (surface only points inside a boundary object) --------

IDENTITY4 = np.eye(4)


def test_clip_box_axis_count():
    # A box/cube has 3 real axes; a flat plane (z extent 0) has 2; a line 1.
    assert clip_box_axis_count([-1, -1, -1], [1, 1, 1]) == 3
    assert clip_box_axis_count([-1, -1, 0], [1, 1, 0]) == 2   # plane
    assert clip_box_axis_count([-1, 0, 0], [1, 0, 0]) == 1    # line


def test_box_clips_in_3d():
    # A unit cube centred at origin must reject points above/below it, not just
    # outside its footprint -- this is the "a cube behaves like a plane" fix.
    bmin, bmax = [-1, -1, -1], [1, 1, 1]
    pts = np.array([
        [0.0, 0.0, 0.0],    # inside
        [0.9, -0.9, 0.5],   # inside
        [0.0, 0.0, 5.0],    # above the cube -> rejected
        [0.0, 0.0, -5.0],   # below the cube -> rejected
        [3.0, 0.0, 0.0],    # outside in X -> rejected
    ])
    mask = points_in_local_box(pts, IDENTITY4, bmin, bmax)
    assert mask.tolist() == [True, True, False, False, False]


def test_flat_plane_clips_footprint_only():
    # A plane has zero Z extent, so Z is unbounded: points at any height inside
    # the XY footprint are kept, matching the "scale a plane over the area" flow.
    bmin, bmax = [-2, -2, 0], [2, 2, 0]
    pts = np.array([
        [0.0, 0.0, 100.0],   # inside footprint, high up -> kept
        [0.0, 0.0, -50.0],   # inside footprint, far below -> kept
        [5.0, 0.0, 0.0],     # outside footprint -> rejected
    ])
    mask = points_in_local_box(pts, IDENTITY4, bmin, bmax)
    assert mask.tolist() == [True, True, False]


def test_box_clip_respects_object_transform():
    # Boundary translated to (10, 10, 0): the inverse matrix maps world points
    # back into the box's local frame before testing.
    matrix = np.eye(4)
    matrix[:3, 3] = [10.0, 10.0, 0.0]
    inv = np.linalg.inv(matrix)
    bmin, bmax = [-1, -1, -1], [1, 1, 1]
    pts = np.array([
        [10.0, 10.0, 0.0],   # at the box centre -> kept
        [0.0, 0.0, 0.0],     # at world origin, far from the box -> rejected
    ])
    mask = points_in_local_box(pts, inv, bmin, bmax)
    assert mask.tolist() == [True, False]


# --- Exact mesh-volume clip (ray-cast parity containment) --------------------

def _box_tris(bmin, bmax):
    """12 triangles of an axis-aligned box, as an (12, 3, 3) array."""
    x0, y0, z0 = bmin
    x1, y1, z1 = bmax
    v = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),  # bottom 0-3
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),  # top 4-7
    ]
    quads = [
        (0, 3, 2, 1),  # bottom
        (4, 5, 6, 7),  # top
        (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),  # sides
    ]
    tris = []
    for a, b, c, d in quads:
        tris.append([v[a], v[b], v[c]])
        tris.append([v[a], v[c], v[d]])
    return np.array(tris, dtype=float)


def _prism_tris(poly_xy, z0, z1, cap_tris):
    """Extrude a 2D outline into a closed prism (top/bottom caps + walls)."""
    bottom = [(x, y, z0) for (x, y) in poly_xy]
    top = [(x, y, z1) for (x, y) in poly_xy]
    tris = []
    for a, b, c in cap_tris:
        tris.append([bottom[a], bottom[c], bottom[b]])  # bottom (reversed)
        tris.append([top[a], top[b], top[c]])           # top
    n = len(poly_xy)
    for i in range(n):
        j = (i + 1) % n
        tris.append([bottom[i], bottom[j], top[j]])
        tris.append([bottom[i], top[j], top[i]])
    return np.array(tris, dtype=float)


def test_mesh_volume_cube():
    tris = _box_tris([-1, -1, -1], [1, 1, 1])
    pts = np.array([
        [0.0, 0.0, 0.0],    # inside
        [0.5, -0.5, 0.5],   # inside
        [0.0, 0.0, 5.0],    # above
        [0.0, 0.0, -5.0],   # below
        [3.0, 0.0, 0.0],    # outside in X
    ])
    mask = points_in_mesh_volume(pts, tris)
    assert mask.tolist() == [True, True, False, False, False]


def test_mesh_volume_respects_concavity():
    # An L-shaped prism: the square notch at [1,2]x[1,2] is NOT part of the
    # volume, so a point there is rejected even though it's inside the bbox.
    poly = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
    cap = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5)]
    tris = _prism_tris(poly, 0.0, 1.0, cap)
    pts = np.array([
        [0.5, 0.5, 0.5],   # left-bottom of the L -> inside
        [1.5, 0.5, 0.5],   # bottom strip -> inside
        [0.5, 1.5, 0.5],   # left column -> inside
        [1.5, 1.5, 0.5],   # the notch -> OUTSIDE (concavity)
        [1.5, 1.5, 5.0],   # above the notch -> outside
    ])
    mask = points_in_mesh_volume(pts, tris)
    assert mask.tolist() == [True, True, True, False, False]


def test_mesh_volume_empty_inputs():
    tris = _box_tris([0, 0, 0], [1, 1, 1])
    assert points_in_mesh_volume(np.empty((0, 3)), tris).shape == (0,)
    pts = np.array([[0.5, 0.5, 0.5]])
    assert points_in_mesh_volume(pts, np.empty((0, 3, 3))).tolist() == [False]
