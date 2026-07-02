import ast
import pathlib

import pytest

np = pytest.importorskip("numpy")


# Extract the bpy-free helper from surface_reconstruct.py without importing the
# module (which pulls in bpy and roadway_surface).
module_path = pathlib.Path(__file__).resolve().parents[1] / "surface_reconstruct.py"
module_ast = ast.parse(module_path.read_text())

ns = {"np": np}
_WANTED = {
    "ball_pivoting_radii", "_dilate_texture", "rasterize_uv_triangles",
    "scatter_uv_colors",
}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in _WANTED:
        exec(compile(ast.Module([node], []), "<ast>", "exec"), ns)

ball_pivoting_radii = ns["ball_pivoting_radii"]
rasterize_uv_triangles = ns["rasterize_uv_triangles"]
scatter_uv_colors = ns["scatter_uv_colors"]


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


def test_ball_pivoting_radii_scale_widens_the_ladder():
    base = ball_pivoting_radii(1.0, multipliers=(1.0, 2.0))
    scaled = ball_pivoting_radii(1.0, multipliers=(1.0, 2.0), scale=3.0)
    assert scaled == [b * 3.0 for b in base]
    # A negative scale is clamped to 0 rather than flipping the radii.
    assert ball_pivoting_radii(1.0, scale=-2.0) == [0.0, 0.0, 0.0]


# --- UV texture rasterizer ---------------------------------------------------

def test_rasterize_solid_triangle_fills_interior():
    # One triangle covering most of a 10x10 texture, all corners red.
    uvs = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    tris = np.array([[0, 1, 2]])
    red = np.tile([1.0, 0.0, 0.0, 1.0], (3, 1))
    img, written = rasterize_uv_triangles(uvs, tris, red, 10, 10, dilate=0)
    assert img.shape == (10, 10, 4)
    # A point clearly inside the lower-left triangle is red and marked written.
    assert written[1, 1]
    assert np.allclose(img[1, 1], [1.0, 0.0, 0.0, 1.0])
    # A point in the opposite (uncovered) corner keeps the grey fill.
    assert not written[9, 9]
    assert img[9, 9, 0] == 0.5


def test_rasterize_interpolates_corner_colors():
    # A single triangle with red/green/blue corners; a point strictly inside
    # should blend all three (none of the channels is zero).
    uvs = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]], dtype=float)
    tris = np.array([[0, 1, 2]])
    cols = np.array([[1, 0, 0, 1], [0, 1, 0, 1], [0, 0, 1, 1]], dtype=float)
    img, written = rasterize_uv_triangles(uvs, tris, cols, 16, 16, dilate=0)
    # Pixel near (u=0.6, v=0.2) is inside the triangle (v < u).
    px = img[3, 9]
    assert written[3, 9]
    assert px[0] > 0.1 and px[1] > 0.1 and px[2] > 0.1  # red, green and blue all mix in


def test_rasterize_empty_inputs_return_fill():
    img, written = rasterize_uv_triangles(np.empty((0, 2)), np.empty((0, 3)),
                                          np.empty((0, 4)), 8, 8)
    assert img.shape == (8, 8, 4)
    assert not written.any()
    assert np.all(img[..., 0] == 0.5)


# --- Cloud-sampled scatter bake ----------------------------------------------

def test_scatter_averages_points_in_a_texel():
    # Two points land in the same texel (bottom-left of a 4x4) with black+white
    # -> that texel is their average (grey); everything else stays fill.
    uvs = np.array([[0.10, 0.10], [0.15, 0.15]])
    cols = np.array([[0.0, 0.0, 0.0, 1.0], [1.0, 1.0, 1.0, 1.0]])
    img, written = scatter_uv_colors(uvs, cols, 4, 4, dilate=0)
    assert written[0, 0]
    assert np.allclose(img[0, 0, :3], 0.5)   # averaged
    assert not written[3, 3]                 # untouched texel keeps fill


def test_scatter_places_points_by_uv():
    # A point near UV (1,1) lands in the top-right texel, not the bottom-left.
    uvs = np.array([[0.95, 0.95]])
    cols = np.array([[1.0, 0.0, 0.0, 1.0]])
    img, written = scatter_uv_colors(uvs, cols, 8, 8, dilate=0)
    assert written[7, 7]
    assert not written[0, 0]
    assert np.allclose(img[7, 7], [1.0, 0.0, 0.0, 1.0])


def test_scatter_empty_returns_fill():
    img, written = scatter_uv_colors(np.empty((0, 2)), np.empty((0, 4)), 8, 8)
    assert not written.any()
    assert np.all(img[..., 0] == 0.5)
