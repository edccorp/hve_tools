bl_info = {
    "name": "Roadway Surface from Point Cloud",
    "author": "EDC",
    "version": (1, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > HVE > Other Tools > Roadway Surface",
    "description": "Build a draped ground surface mesh from a point-cloud object for vehicle simulations",
    "category": "Object",
}

import os
import re
import warnings

import bpy
import numpy as np

# ---------------------------------------------------------------------------
# Heightfield core (numpy-vectorized)
#
# These helpers are bpy-free so the sampling and mesh generation can be unit
# tested outside Blender, matching the other tools in this add-on. The operator
# below feeds them an (N, 3) array of world-space points.
#
# The approach reproduces a "shrink-wrap from below" drape without needing a
# target surface, and is fully vectorized so it stays fast on million-point
# clouds: bin every point into a regular XY grid cell (the resolution), and for
# each cell take a low percentile of the point heights. The low percentile grabs
# the ground and ignores overhead noise (vehicles, foliage) while still
# rejecting the occasional spurious below-ground point. Empty cells are then
# filled from their neighbours. Optional per-point colours are averaged per cell
# and carried onto the surface.
# ---------------------------------------------------------------------------


def build_grid_spec(points, cell_size):
    """Return ``(min_x, min_y, nx, ny)`` for a grid over the points' XY extent."""
    if cell_size <= 0:
        raise ValueError("cell_size must be positive")
    pts = np.asarray(points, dtype=np.float64)
    min_x = float(pts[:, 0].min())
    min_y = float(pts[:, 1].min())
    max_x = float(pts[:, 0].max())
    max_y = float(pts[:, 1].max())
    nx = max(int(np.floor((max_x - min_x) / cell_size)) + 1, 2)
    ny = max(int(np.floor((max_y - min_y) / cell_size)) + 1, 2)
    return min_x, min_y, nx, ny


def cell_indices(points, min_x, min_y, nx, ny, cell_size):
    """Flat ``iy * nx + ix`` cell index for each point (clamped to the grid)."""
    pts = np.asarray(points, dtype=np.float64)
    ix = np.clip(np.floor((pts[:, 0] - min_x) / cell_size).astype(np.int64), 0, nx - 1)
    iy = np.clip(np.floor((pts[:, 1] - min_y) / cell_size).astype(np.int64), 0, ny - 1)
    return iy * nx + ix


def cell_percentile_grid(points, min_x, min_y, nx, ny, cell_size, ground_percentile):
    """Per-cell low-percentile ground height as an ``(ny, nx)`` array (NaN = empty).

    Vectorized: points are binned to cells, sorted once by (cell, z), and the
    percentile sample per cell is gathered by index.
    """
    pts = np.asarray(points, dtype=np.float64)
    z = pts[:, 2]
    flat = cell_indices(pts, min_x, min_y, nx, ny, cell_size)

    order = np.lexsort((z, flat))  # sort by cell, then ascending z within cell
    flat_sorted = flat[order]
    z_sorted = z[order]

    cells, starts, counts = np.unique(flat_sorted, return_index=True, return_counts=True)
    q = min(max(float(ground_percentile), 0.0), 100.0)
    offset = np.floor((q / 100.0) * (counts - 1)).astype(np.int64)
    values = z_sorted[starts + offset]

    grid = np.full(nx * ny, np.nan, dtype=np.float64)
    grid[cells] = values
    return grid.reshape(ny, nx)


def cell_mean_grid(flat, values, nx, ny):
    """Per-cell mean of ``values`` (indexed by flat cell id) as ``(ny, nx)``; NaN = empty."""
    values = np.asarray(values, dtype=np.float64)
    sums = np.bincount(flat, weights=values, minlength=nx * ny)
    counts = np.bincount(flat, minlength=nx * ny)
    grid = np.full(nx * ny, np.nan, dtype=np.float64)
    nonzero = counts > 0
    grid[nonzero] = sums[nonzero] / counts[nonzero]
    return grid.reshape(ny, nx)


def _shift(grid, dj, di):
    """Return ``grid`` shifted by (dj, di) with NaN padding at the edges."""
    out = np.full_like(grid, np.nan)
    ny, nx = grid.shape
    sy0, sy1 = max(0, -dj), ny - max(0, dj)
    sx0, sx1 = max(0, -di), nx - max(0, di)
    dy0, dy1 = max(0, dj), ny - max(0, -dj)
    dx0, dx1 = max(0, di), nx - max(0, -di)
    out[dy0:dy1, dx0:dx1] = grid[sy0:sy1, sx0:sx1]
    return out


def fill_holes_grid(grid, max_passes):
    """Iteratively fill NaN cells from the mean of their filled 4-neighbours.

    ``max_passes`` bounds how far filling reaches (in cells). Cells that remain
    unreachable stay NaN.
    """
    filled = grid.copy()
    for _ in range(max(int(max_passes), 0)):
        nan_mask = np.isnan(filled)
        if not nan_mask.any():
            break
        stack = np.stack(
            [_shift(filled, 1, 0), _shift(filled, -1, 0), _shift(filled, 0, 1), _shift(filled, 0, -1)],
            axis=0,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            neighbour_mean = np.nanmean(stack, axis=0)
        fillable = nan_mask & ~np.isnan(neighbour_mean)
        if not fillable.any():
            break
        filled[fillable] = neighbour_mean[fillable]
    return filled


def build_mesh_arrays(min_x, min_y, cell_size, z_grid):
    """Turn a height grid into ``(verts, faces)`` numpy arrays.

    A quad is emitted only where all four of its corners have a height, so gaps
    in the cloud leave holes rather than spikes. NaN vertices are placed at Z 0
    but are not referenced by any face.
    """
    z_grid = np.asarray(z_grid, dtype=np.float64)
    ny, nx = z_grid.shape

    xs = min_x + np.arange(nx, dtype=np.float64) * cell_size
    ys = min_y + np.arange(ny, dtype=np.float64) * cell_size
    gx, gy = np.meshgrid(xs, ys)
    gz = np.where(np.isnan(z_grid), 0.0, z_grid)
    verts = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])

    a = (np.arange(ny - 1)[:, None] * nx + np.arange(nx - 1)[None, :])
    b = a + 1
    c = a + nx + 1
    d = a + nx
    valid = ~np.isnan(z_grid)
    cell_valid = valid[:-1, :-1] & valid[:-1, 1:] & valid[1:, 1:] & valid[1:, :-1]
    mask = cell_valid.ravel()
    faces = np.column_stack([a.ravel(), b.ravel(), c.ravel(), d.ravel()])[mask]
    return verts, faces


def _color_grid(points, colors, min_x, min_y, nx, ny, cell_size, max_passes):
    """Per-vertex colour array (nx*ny, C) from per-point colours; averaged per cell."""
    col = np.asarray(colors, dtype=np.float64)
    flat = cell_indices(points, min_x, min_y, nx, ny, cell_size)
    channels = []
    for c in range(col.shape[1]):
        chan = cell_mean_grid(flat, col[:, c], nx, ny)
        if max_passes > 0:
            chan = fill_holes_grid(chan, max_passes)
        channels.append(chan)
    stacked = np.stack(channels, axis=-1)  # (ny, nx, C)
    stacked = np.where(np.isnan(stacked), 0.5, stacked)  # unresolved cells -> mid grey
    return stacked.reshape(nx * ny, col.shape[1])


def grid_uvs(nx, ny):
    """Per-vertex ``(u, v)`` for an ``nx*ny`` grid; vertex index is ``j * nx + i``."""
    us = (np.arange(nx, dtype=np.float64) / (nx - 1)) if nx > 1 else np.zeros(nx)
    vs = (np.arange(ny, dtype=np.float64) / (ny - 1)) if ny > 1 else np.zeros(ny)
    uu, vv = np.meshgrid(us, vs)
    return np.column_stack([uu.ravel(), vv.ravel()])


# ---------------------------------------------------------------------------
# Optional point-cloud pre-filters
# ---------------------------------------------------------------------------

def _clip_box_epsilon(extents):
    """Relative tolerance below which a box axis counts as degenerate (flat)."""
    mx = float(np.max(extents)) if len(extents) else 0.0
    return mx * 1e-6


def clip_box_axis_count(bbox_min, bbox_max):
    """Number of box axes with a real (non-degenerate) extent.

    A flat plane has 2, a box/cube has 3, a line 1. Used to decide whether a
    boundary object defines a usable clip region.
    """
    extents = np.asarray(bbox_max, dtype=np.float64) - np.asarray(bbox_min, dtype=np.float64)
    return int(np.count_nonzero(extents > _clip_box_epsilon(extents)))


def points_in_local_box(points, inv_matrix, bbox_min, bbox_max, tol=0.0):
    """Keep-mask for points inside a boundary object's oriented box.

    Points are transformed into the object's local frame with ``inv_matrix``
    (the inverse of its world matrix), then tested against the object's local
    axis-aligned bounds. This clips a true 3D volume, so a cube/box trims points
    above and below it, not just its footprint. An axis whose local extent is
    ~0 (e.g. a flat plane's thickness) is treated as unbounded, so a plane still
    clips just its XY footprint. Fully vectorized.
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] == 0:
        return np.ones(0, dtype=bool)
    inv = np.asarray(inv_matrix, dtype=np.float64)
    local = pts @ inv[:3, :3].T + inv[:3, 3]
    bmin = np.asarray(bbox_min, dtype=np.float64)
    bmax = np.asarray(bbox_max, dtype=np.float64)
    eps = _clip_box_epsilon(bmax - bmin)

    mask = np.ones(pts.shape[0], dtype=bool)
    for ax in range(3):
        if (bmax[ax] - bmin[ax]) <= eps:
            continue  # degenerate axis (plane thickness) -> unbounded
        mask &= (local[:, ax] >= bmin[ax] - tol) & (local[:, ax] <= bmax[ax] + tol)
    return mask


def voxel_downsample(points, colors, voxel_size):
    """Thin a cloud to one averaged point (and colour) per occupied voxel.

    Returns ``(points, colors)`` as numpy arrays; ``colors`` is None when no
    colours were supplied. A ``voxel_size`` <= 0 or an empty cloud is a no-op.
    """
    pts = np.asarray(points, dtype=np.float64)
    cols = np.asarray(colors, dtype=np.float64) if colors is not None else None
    if voxel_size <= 0 or pts.shape[0] == 0:
        return pts, cols

    keys = np.floor(pts / voxel_size).astype(np.int64)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.ravel()
    n_vox = counts.shape[0]

    sums = np.zeros((n_vox, 3), dtype=np.float64)
    np.add.at(sums, inverse, pts)
    ds_pts = sums / counts[:, None]

    ds_cols = None
    if cols is not None:
        csum = np.zeros((n_vox, cols.shape[1]), dtype=np.float64)
        np.add.at(csum, inverse, cols)
        ds_cols = csum / counts[:, None]
    return ds_pts, ds_cols


def statistical_outlier_mask(mean_distances, ratio):
    """Keep-mask for statistical outlier removal.

    Given each point's mean distance to its neighbours, keep points whose mean
    distance is within ``global_mean + ratio * global_std``.
    """
    d = np.asarray(mean_distances, dtype=np.float64)
    if d.size == 0:
        return np.ones(0, dtype=bool)
    threshold = d.mean() + ratio * d.std()
    return d <= threshold


def mask_points_near_ground(points, z_grid, min_x, min_y, cell_size, tol):
    """Keep-mask for points within ``tol`` of the sampled ground height.

    Each point looks up the ground height of its XY cell in ``z_grid`` (the
    filled ``(ny, nx)`` height grid); points more than ``tol`` above or below it
    are masked out. This stops colours from objects above the road (vehicles,
    foliage) bleeding into the surface colour and texture. Points over cells
    with no ground height are masked out too.
    """
    pts = np.asarray(points, dtype=np.float64)
    ny, nx = z_grid.shape
    ix = np.clip(np.floor((pts[:, 0] - min_x) / cell_size).astype(np.int64), 0, nx - 1)
    iy = np.clip(np.floor((pts[:, 1] - min_y) / cell_size).astype(np.int64), 0, ny - 1)
    ground = np.asarray(z_grid, dtype=np.float64)[iy, ix]
    return ~np.isnan(ground) & (np.abs(pts[:, 2] - ground) <= tol)


def generate_surface(points, cell_size, fill_distance, ground_percentile, fill_holes=True, colors=None,
                     color_height_tol=0.0):
    """End-to-end: point cloud -> ``dict`` with verts, faces, grid size, counts.

    When ``colors`` (an (N, C) array of per-point colour) is given, the result
    also includes a per-vertex ``colors`` array aligned with ``verts``. When
    ``color_height_tol`` > 0, only points within that height of the sampled
    ground contribute colour (overhead objects are excluded). Returns None when
    fewer than three points are supplied.
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] < 3:
        return None

    min_x, min_y, nx, ny = build_grid_spec(pts, cell_size)
    grid = cell_percentile_grid(pts, min_x, min_y, nx, ny, cell_size, ground_percentile)
    sampled = int(np.count_nonzero(~np.isnan(grid)))

    if fill_holes:
        if fill_distance and fill_distance > 0:
            max_passes = max(1, int(round(fill_distance / cell_size)))
        else:
            max_passes = nx + ny  # effectively unlimited for a connected region
    else:
        max_passes = 0

    if max_passes > 0:
        grid = fill_holes_grid(grid, max_passes)

    verts, faces = build_mesh_arrays(min_x, min_y, cell_size, grid)
    result = {
        "verts": verts,
        "faces": faces,
        "nx": nx,
        "ny": ny,
        "min_x": min_x,
        "min_y": min_y,
        "cell_size": cell_size,
        "z_grid": grid,
        "sampled": sampled,
        "total": nx * ny,
    }
    if colors is not None:
        pts_c = pts
        cols_c = np.asarray(colors, dtype=np.float64)
        if color_height_tol and color_height_tol > 0:
            near = mask_points_near_ground(pts, grid, min_x, min_y, cell_size, color_height_tol)
            if near.any():
                pts_c = pts[near]
                cols_c = cols_c[near]
        result["colors"] = _color_grid(pts_c, cols_c, min_x, min_y, nx, ny, cell_size, max_passes)
    return result


def bake_point_color_texture(points, colors, min_x, min_y, cell_size, nx, ny,
                             target_size, fill_passes=256):
    """Rasterize per-point colours into a texture, sampled from the full cloud.

    The texture spans the surface's covered XY extent — ``(nx-1)*cell_size`` by
    ``(ny-1)*cell_size`` — so it lines up with the surface's normalized UVs, but
    its pixel resolution is set by ``target_size`` (the longest side, aspect
    preserved) instead of the mesh grid. This lets a dense point cloud produce a
    texture far sharper than the surface resolution. ``target_size`` of 0 falls
    back to the grid resolution. Returns ``(pixels, width, height)`` with pixels
    laid out bottom-row-first (Blender image order).
    """
    covered_w = max((nx - 1) * cell_size, 0.0)
    covered_h = max((ny - 1) * cell_size, 0.0)

    if target_size and target_size > 0 and covered_w > 0 and covered_h > 0:
        if covered_w >= covered_h:
            tex_w = int(target_size)
            tex_h = max(1, int(round(target_size * covered_h / covered_w)))
        else:
            tex_h = int(target_size)
            tex_w = max(1, int(round(target_size * covered_w / covered_h)))
    else:
        tex_w, tex_h = nx, ny

    size_x = covered_w / tex_w if (tex_w and covered_w > 0) else cell_size
    size_y = covered_h / tex_h if (tex_h and covered_h > 0) else cell_size

    pts = np.asarray(points, dtype=np.float64)
    ix = np.clip(np.floor((pts[:, 0] - min_x) / size_x).astype(np.int64), 0, tex_w - 1)
    iy = np.clip(np.floor((pts[:, 1] - min_y) / size_y).astype(np.int64), 0, tex_h - 1)
    flat = iy * tex_w + ix

    col = np.asarray(colors, dtype=np.float64)
    channels = min(col.shape[1], 4)
    grids = []
    for c in range(channels):
        chan = cell_mean_grid(flat, col[:, c], tex_w, tex_h)
        chan = fill_holes_grid(chan, fill_passes)
        grids.append(chan)
    grid = np.stack(grids, axis=-1)  # (tex_h, tex_w, channels)
    if channels < 4:
        pad = np.ones((tex_h, tex_w, 4 - channels), dtype=np.float64)
        grid = np.concatenate([grid, pad], axis=2)
    grid = np.where(np.isnan(grid), 0.5, grid)  # unresolved texels -> mid grey

    return grid.reshape(-1), tex_w, tex_h


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

# Guard against accidental multi-hundred-million-vertex grids (tiny cell size on
# a huge extent) that would exhaust memory before mesh creation.
MAX_GRID_VERTS = 8_000_000


def _build_image_texture_material(name, image):
    """Create a material whose Base Color comes from an Image Texture node."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()

    output = tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (400, 0)
    principled = tree.nodes.new('ShaderNodeBsdfPrincipled')
    principled.location = (100, 0)
    tex = tree.nodes.new('ShaderNodeTexImage')
    tex.location = (-300, 0)
    tex.image = image

    tree.links.new(tex.outputs['Color'], principled.inputs['Base Color'])
    tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    return material


def _safe_filename(name):
    """Sanitize ``name`` into a safe base filename."""
    cleaned = re.sub(r"[^\w\-]+", "_", name).strip("_")
    return cleaned or "Roadway_Surface"


def _apply_baked_texture(source_name, new_mesh, points, colors, result,
                         target_size, fill_distance, blend_dir):
    """Bake per-point colours to a JPG, add grid UVs and an image material.

    The texture is sampled directly from the point cloud at ``target_size``
    resolution (independent of the mesh grid), then mapped onto the surface via
    its grid UVs. The image-texture material is always built and assigned.
    Returns the saved JPG path, or None when the image was only packed into the
    .blend (because it has not been saved to disk yet).
    """
    nx, ny = result["nx"], result["ny"]
    cell_size = result["cell_size"]

    # Convert the fill distance (scene units) into texel passes.
    covered_long = max((nx - 1) * cell_size, (ny - 1) * cell_size)
    tex_long = target_size if target_size > 0 else max(nx, ny)
    texel = (covered_long / tex_long) if tex_long else cell_size
    if fill_distance and fill_distance > 0 and texel > 0:
        fill_passes = min(1024, max(1, int(round(fill_distance / texel))))
    else:
        fill_passes = 256

    pixels, tw, th = bake_point_color_texture(
        points, colors, result["min_x"], result["min_y"], cell_size, nx, ny,
        target_size, fill_passes,
    )

    image = bpy.data.images.new(f"Roadway Color: {source_name}", width=tw, height=th, alpha=True)
    image.pixels.foreach_set(np.asarray(pixels, dtype=np.float32))

    saved_path = None
    if blend_dir:
        saved_path = os.path.join(blend_dir, _safe_filename(f"Roadway_Color_{source_name}") + ".jpg")
        image.filepath_raw = saved_path
        image.file_format = 'JPEG'
        image.save()
    else:
        # No .blend on disk yet: keep the image inside the .blend so the material
        # still shows the texture. It must be saved before the H3D export can
        # reference it on disk.
        image.pack()

    # UVs: a per-vertex grid UV assigned to each loop by its vertex index.
    vert_uv = grid_uvs(nx, ny)
    uv_layer = new_mesh.uv_layers.new(name="UVMap")
    loop_vi = np.empty(len(new_mesh.loops), dtype=np.int64)
    new_mesh.loops.foreach_get("vertex_index", loop_vi)
    uv_layer.data.foreach_set("uv", vert_uv[loop_vi].reshape(-1))

    material = _build_image_texture_material(f"Roadway Surface: {source_name}", image)
    new_mesh.materials.append(material)
    return saved_path


def _sor_neighbor_mean_distances(points, k):
    """Mean distance from each point to its ``k`` nearest neighbours.

    Uses Blender's bundled ``mathutils.kdtree``. This is a per-point query, so
    subsampling first keeps it affordable on large clouds.
    """
    from mathutils.kdtree import KDTree

    pts = np.asarray(points, dtype=np.float64)
    n = pts.shape[0]
    tree = KDTree(n)
    for i in range(n):
        tree.insert((float(pts[i, 0]), float(pts[i, 1]), float(pts[i, 2])), i)
    tree.balance()

    means = np.zeros(n, dtype=np.float64)
    for i in range(n):
        found = tree.find_n((float(pts[i, 0]), float(pts[i, 1]), float(pts[i, 2])), k + 1)
        dists = [d for (_co, idx, d) in found if idx != i]
        if dists:
            means[i] = sum(dists) / len(dists)
    return means


def _find_point_color_attribute(mesh):
    """Return a POINT-domain colour attribute on ``mesh``, preferring the active one."""
    color_attributes = getattr(mesh, "color_attributes", None)
    if not color_attributes:
        return None
    active = getattr(color_attributes, "active_color", None)
    if active is not None and getattr(active, "domain", None) == 'POINT':
        return active
    for attr in color_attributes:
        if getattr(attr, "domain", None) == 'POINT':
            return attr
    return None


def _read_point_cloud(source, want_colors):
    """Bulk-read a mesh object's raw vertices (local space) and point colours.

    Returns ``(local_points, colors, color_attr_name)``; ``colors`` is None when
    the mesh has no usable POINT-domain colour attribute.
    """
    mesh = source.data
    count = len(mesh.vertices)
    local = np.empty(count * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", local)
    local = local.reshape(count, 3)

    colors = None
    attr_name = "Col"
    if want_colors:
        color_attr = _find_point_color_attribute(mesh)
        if color_attr is not None and len(color_attr.data) == count:
            attr_name = color_attr.name
            raw = np.empty(count * 4, dtype=np.float64)
            color_attr.data.foreach_get("color", raw)
            colors = raw.reshape(count, 4)
    return local, colors, attr_name


def _clip_object_box(clip_obj):
    """Return ``(inv_matrix, bbox_min, bbox_max)`` for a boundary object's box.

    The bounds are the object's local-space axis-aligned bounding box (its 8
    ``bound_box`` corners); ``inv_matrix`` maps world points into that local
    frame. Returns ``None`` when ``clip_obj`` is unusable (not a mesh, no
    geometry).
    """
    if clip_obj is None or getattr(clip_obj, "type", None) != 'MESH':
        return None
    corners = np.array([c[:] for c in clip_obj.bound_box], dtype=np.float64)
    if corners.shape[0] < 8:
        return None
    bbox_min = corners.min(axis=0)
    bbox_max = corners.max(axis=0)
    matrix = np.array(clip_obj.matrix_world, dtype=np.float64)
    try:
        inv = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return None
    return inv, bbox_min, bbox_max


def _run_prefilters(scene, points, colors):
    """Apply the enabled pre-filters (voxel subsample, then SOR).

    Returns ``(points, colors, count_before)``. The inputs are never modified;
    filtering produces new arrays.
    """
    n_before = len(points)
    if bool(scene.roadway_subsample) and float(scene.roadway_voxel_size) > 0:
        points, colors = voxel_downsample(points, colors, float(scene.roadway_voxel_size))
    if bool(scene.roadway_sor) and len(points) > int(scene.roadway_sor_neighbors) + 1:
        means = _sor_neighbor_mean_distances(points, int(scene.roadway_sor_neighbors))
        keep = statistical_outlier_mask(means, float(scene.roadway_sor_ratio))
        points = points[keep]
        if colors is not None:
            colors = colors[keep]
    return points, colors, n_before


class HVE_OT_CreateRoadwaySurface(bpy.types.Operator):
    """Build a draped ground surface from a selected point-cloud object (e.g. a PLY)"""
    bl_idname = "object.create_roadway_surface"
    bl_label = "Create Roadway Surface"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        source = getattr(scene, "roadway_source_object", None) or context.object

        if source is None or source.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh point-cloud object (e.g. an imported PLY).")
            return {'CANCELLED'}

        wm = context.window_manager
        window = context.window
        wm.progress_begin(0, 100)
        if window is not None:
            window.cursor_set('WAIT')

        try:
            wm.progress_update(5)
            # Read the raw base-mesh vertices, not the evaluated mesh: a point
            # cloud imported with a GeoNodes display modifier would otherwise
            # yield the display geometry instead of the original points.
            local, colors, _attr_name = _read_point_cloud(source, True)
            if len(local) < 3:
                self.report({'ERROR'}, "Source object has too few vertices for a surface.")
                return {'CANCELLED'}

            wm.progress_update(20)

            # Transform to world space with a single vectorized matrix multiply.
            matrix = np.array(source.matrix_world, dtype=np.float64)
            points = local @ matrix[:3, :3].T + matrix[:3, 3]

            # Keep the unfiltered cloud so the texture can optionally sample it.
            points_full = points
            colors_full = colors

            # Optional dedicated colour source for the texture (e.g. the original
            # full-resolution cloud when the geometry source is a filtered copy).
            tex_src = getattr(scene, "roadway_texture_source_object", None)
            if tex_src is not None and tex_src.type == 'MESH' and tex_src is not source:
                t_local, t_colors, _t_attr = _read_point_cloud(tex_src, True)
                if len(t_local) and t_colors is not None:
                    t_matrix = np.array(tex_src.matrix_world, dtype=np.float64)
                    points_full = t_local @ t_matrix[:3, :3].T + t_matrix[:3, 3]
                    colors_full = t_colors

            # Optional clip: keep only points inside a boundary object's box, so
            # far-away scan points don't get draped or textured. A box/cube
            # clips in 3D (above and below too); a flat plane clips its footprint.
            clip_note = ""
            clip_obj = getattr(scene, "roadway_clip_object", None)
            if clip_obj is not None and clip_obj is not source:
                clip = _clip_object_box(clip_obj)
                if clip is not None and clip_box_axis_count(clip[1], clip[2]) >= 2:
                    inv, bmin, bmax = clip
                    keep = points_in_local_box(points, inv, bmin, bmax)
                    n_clip = len(points)
                    points = points[keep]
                    if colors is not None:
                        colors = colors[keep]
                    # Clip the texture cloud to the same box too.
                    keep_full = points_in_local_box(points_full, inv, bmin, bmax)
                    points_full = points_full[keep_full]
                    if colors_full is not None:
                        colors_full = colors_full[keep_full]
                    if keep.sum() != n_clip:
                        clip_note = f" Clipped to {int(keep.sum())} points inside {clip_obj.name}."
                    if len(points) < 3:
                        self.report(
                            {'WARNING'},
                            f"Clip boundary '{clip_obj.name}' left too few points; "
                            "check it overlaps the cloud.",
                        )
                        return {'CANCELLED'}
                else:
                    self.report(
                        {'WARNING'},
                        f"Clip boundary '{clip_obj.name}' has no usable volume; ignoring it.",
                    )

            # Optional pre-filters: voxel subsample, then statistical outlier
            # removal, before any surfacing.
            filtered_note = ""
            points, colors, n_before = _run_prefilters(scene, points, colors)
            if len(points) != n_before:
                filtered_note = f" Filtered {n_before}->{len(points)} points."
            if len(points) < 3:
                self.report({'WARNING'}, "Pre-filter left too few points; relax the filters.")
                return {'CANCELLED'}

            wm.progress_update(35)
            cell_size = float(scene.roadway_cell_size)
            fill_distance = float(scene.roadway_fill_distance)
            ground_percentile = float(scene.roadway_ground_percentile)
            fill_holes = bool(scene.roadway_fill_holes)

            # Reject grids that would be too large before doing the heavy work.
            min_x, min_y, nx, ny = build_grid_spec(points, cell_size)
            if nx * ny > MAX_GRID_VERTS:
                self.report({'ERROR'}, f"Grid would be {nx}x{ny} vertices; increase the cell size.")
                return {'CANCELLED'}

            wm.progress_update(45)
            result = generate_surface(
                points, cell_size, fill_distance, ground_percentile, fill_holes, colors=colors,
                color_height_tol=float(scene.roadway_color_height_tol),
            )
            if result is None or len(result["faces"]) == 0:
                self.report(
                    {'WARNING'},
                    "No surface cells were produced; try a larger cell size or fill distance.",
                )
                return {'CANCELLED'}

            wm.progress_update(75)
            mesh_name = f"Roadway Surface: {source.name}"
            new_mesh = bpy.data.meshes.new(mesh_name)
            new_mesh.from_pydata(result["verts"].tolist(), [], result["faces"].tolist())
            new_mesh.update()

            baked_texture_path = None
            if "colors" in result:
                color_layer = new_mesh.color_attributes.new(name="Col", type='FLOAT_COLOR', domain='POINT')
                color_layer.data.foreach_set("color", result["colors"].astype(np.float32).ravel())

                blend_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ""
                # Always bake the texture from the full (unfiltered / dedicated)
                # colour cloud, restricted to the surface's XY extent so
                # far-away points cannot smear into the border texels.
                tex_points, tex_colors = points, colors
                if colors_full is not None:
                    max_x = result["min_x"] + (result["nx"] - 1) * result["cell_size"]
                    max_y = result["min_y"] + (result["ny"] - 1) * result["cell_size"]
                    inside = (
                        (points_full[:, 0] >= result["min_x"]) & (points_full[:, 0] <= max_x)
                        & (points_full[:, 1] >= result["min_y"]) & (points_full[:, 1] <= max_y)
                    )
                    if inside.any():
                        tex_points, tex_colors = points_full[inside], colors_full[inside]
                # Only points near the sampled ground colour the texture, so
                # vehicles/foliage above the road cannot tint it.
                tol = float(scene.roadway_color_height_tol)
                if tol > 0:
                    near = mask_points_near_ground(
                        tex_points, result["z_grid"], result["min_x"], result["min_y"],
                        result["cell_size"], tol,
                    )
                    if near.any():
                        tex_points, tex_colors = tex_points[near], tex_colors[near]
                baked_texture_path = _apply_baked_texture(
                    source.name, new_mesh, tex_points, tex_colors, result,
                    int(scene.roadway_texture_size),
                    float(scene.roadway_fill_distance),
                    blend_dir,
                )
                if baked_texture_path is None:
                    self.report(
                        {'WARNING'},
                        "Texture baked into the .blend; save the .blend and re-create "
                        "the surface to write the JPG for H3D export.",
                    )

            new_obj = bpy.data.objects.new(mesh_name, new_mesh)
            context.collection.objects.link(new_obj)

            # Classify as an HVE Environment object so it flows into H3D
            # environment export for vehicle simulations.
            try:
                new_obj.hve_type.set_type.type = 'ENVIRONMENT'
            except (AttributeError, TypeError):
                pass

            for obj in list(context.selected_objects):
                obj.select_set(False)
            new_obj.select_set(True)
            context.view_layer.objects.active = new_obj

            wm.progress_update(100)
            colored = " (coloured)" if "colors" in result else ""
            texture_note = f" Texture saved to {os.path.basename(baked_texture_path)}." if baked_texture_path else ""
            self.report(
                {'INFO'},
                f"Roadway surface{colored}: {result['nx']}x{result['ny']} grid, "
                f"{len(result['faces'])} faces, {result['sampled']}/{result['total']} cells "
                f"sampled from {len(points)} points.{clip_note}{filtered_note}{texture_note}",
            )
            return {'FINISHED'}
        finally:
            wm.progress_end()
            if window is not None:
                window.cursor_set('DEFAULT')


class HVE_OT_FilterPointCloud(bpy.types.Operator):
    """Apply the Subsample / SOR pre-filters into a brand-new point-cloud object, leaving the original unchanged"""
    bl_idname = "object.filter_point_cloud"
    bl_label = "Filter → Create New Point Cloud"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        source = getattr(scene, "roadway_source_object", None) or context.object

        if source is None or source.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh point-cloud object (e.g. an imported PLY).")
            return {'CANCELLED'}
        if not (bool(scene.roadway_subsample) or bool(scene.roadway_sor)):
            self.report({'WARNING'}, "Enable Subsample and/or Remove Outliers first.")
            return {'CANCELLED'}

        wm = context.window_manager
        window = context.window
        wm.progress_begin(0, 100)
        if window is not None:
            window.cursor_set('WAIT')

        try:
            local, colors, attr_name = _read_point_cloud(source, True)
            if len(local) < 1:
                self.report({'ERROR'}, "Source object has no vertices.")
                return {'CANCELLED'}

            wm.progress_update(15)
            matrix = np.array(source.matrix_world, dtype=np.float64)
            points = local @ matrix[:3, :3].T + matrix[:3, 3]

            points, colors, n_before = _run_prefilters(scene, points, colors)
            if len(points) < 1:
                self.report({'WARNING'}, "Pre-filter removed every point; relax the filters.")
                return {'CANCELLED'}

            wm.progress_update(70)
            verts32 = np.ascontiguousarray

            # Always build a new point-cloud object from the filtered result;
            # the original cloud is never modified.
            mesh = bpy.data.meshes.new(f"{source.name} Filtered")
            mesh.vertices.add(len(points))
            mesh.vertices.foreach_set("co", verts32(points, dtype=np.float32).ravel())
            mesh.update()
            if colors is not None:
                layer = mesh.color_attributes.new(name=attr_name, type='FLOAT_COLOR', domain='POINT')
                layer.data.foreach_set("color", colors.astype(np.float32).ravel())

            target = bpy.data.objects.new(mesh.name, mesh)
            context.collection.objects.link(target)

            # Give the copy the same GeoNodes point display as the importer.
            try:
                from .ply_pointcloud.materials import make_point_material
                from .ply_pointcloud.geonodes import make_geonodes_group, assign_geonodes_modifier

                mat = None
                if colors is not None:
                    mat_name = f"PointCloud_Color_{attr_name}"
                    mat = bpy.data.materials.get(mat_name) or make_point_material(mat_name, attr_name)
                ng = make_geonodes_group("PCD_View_Geo", 0.01, mat)
                assign_geonodes_modifier(target, ng, 0.01)
                if mat is not None and mat.name not in [m.name for m in mesh.materials]:
                    mesh.materials.append(mat)
            except Exception as exc:  # noqa: BLE001 - display setup is best-effort
                print(f"Point display setup skipped: {exc}")

            for obj in list(context.selected_objects):
                obj.select_set(False)
            target.select_set(True)
            context.view_layer.objects.active = target

            # If the panel pointed at the original explicitly, follow the copy
            # so Create Roadway Surface uses the filtered cloud.
            if getattr(scene, "roadway_source_object", None) == source:
                scene.roadway_source_object = target

            wm.progress_update(100)
            self.report(
                {'INFO'},
                f"Created new point cloud '{target.name}': {n_before} -> {len(points)} "
                f"points. Original '{source.name}' left unchanged.",
            )
            return {'FINISHED'}
        finally:
            wm.progress_end()
            if window is not None:
                window.cursor_set('DEFAULT')


classes = [
    HVE_OT_CreateRoadwaySurface,
    HVE_OT_FilterPointCloud,
]
