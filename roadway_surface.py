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


def color_grid_to_image(colors, nx, ny, max_size=0):
    """Build an RGBA image from per-vertex colours for baking to a texture.

    ``colors`` is an (nx*ny, C) array in vertex order (index ``j * nx + i``).
    Returns ``(pixels, width, height)`` where ``pixels`` is a flat RGBA float
    array of length ``width * height * 4`` laid out bottom-row-first (Blender's
    image pixel order, matching v=0 at the grid's min-Y edge). When ``max_size``
    is > 0 and the grid's larger side exceeds it, the image is nearest-sampled
    down so its longest side is ``max_size``.
    """
    arr = np.asarray(colors, dtype=np.float64)
    channels = arr.shape[1]
    grid = arr.reshape(ny, nx, channels)
    if channels < 4:
        pad = np.ones((ny, nx, 4 - channels), dtype=np.float64)
        grid = np.concatenate([grid, pad], axis=2)
    else:
        grid = grid[:, :, :4]

    width, height = nx, ny
    if max_size and max(nx, ny) > max_size:
        scale = max_size / float(max(nx, ny))
        width = max(1, int(round(nx * scale)))
        height = max(1, int(round(ny * scale)))
        yi = np.linspace(0, ny - 1, height).round().astype(np.int64)
        xi = np.linspace(0, nx - 1, width).round().astype(np.int64)
        grid = grid[yi][:, xi]

    return grid.reshape(-1), width, height


def grid_uvs(nx, ny):
    """Per-vertex ``(u, v)`` for an ``nx*ny`` grid; vertex index is ``j * nx + i``."""
    us = (np.arange(nx, dtype=np.float64) / (nx - 1)) if nx > 1 else np.zeros(nx)
    vs = (np.arange(ny, dtype=np.float64) / (ny - 1)) if ny > 1 else np.zeros(ny)
    uu, vv = np.meshgrid(us, vs)
    return np.column_stack([uu.ravel(), vv.ravel()])


def generate_surface(points, cell_size, fill_distance, ground_percentile, fill_holes=True, colors=None):
    """End-to-end: point cloud -> ``dict`` with verts, faces, grid size, counts.

    When ``colors`` (an (N, C) array of per-point colour) is given, the result
    also includes a per-vertex ``colors`` array aligned with ``verts``. Returns
    None when fewer than three points are supplied.
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
        "sampled": sampled,
        "total": nx * ny,
    }
    if colors is not None:
        result["colors"] = _color_grid(pts, colors, min_x, min_y, nx, ny, cell_size, max_passes)
    return result


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

# Guard against accidental multi-hundred-million-vertex grids (tiny cell size on
# a huge extent) that would exhaust memory before mesh creation.
MAX_GRID_VERTS = 8_000_000


def _build_color_attribute_material(name, attribute_name):
    """Create a material whose Base Color is driven by a color attribute."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()

    output = tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (300, 0)
    principled = tree.nodes.new('ShaderNodeBsdfPrincipled')
    principled.location = (0, 0)
    attribute = tree.nodes.new('ShaderNodeAttribute')
    attribute.location = (-300, 0)
    attribute.attribute_name = attribute_name
    try:
        attribute.attribute_type = 'GEOMETRY'
    except (AttributeError, TypeError):
        pass

    tree.links.new(attribute.outputs['Color'], principled.inputs['Base Color'])
    tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    return material


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


def _apply_baked_texture(source_name, new_mesh, result, max_size, blend_dir):
    """Bake the surface colours to a JPG, add grid UVs and an image material.

    Returns the saved image file path.
    """
    nx, ny = result["nx"], result["ny"]
    pixels, tw, th = color_grid_to_image(result["colors"], nx, ny, max_size)

    image = bpy.data.images.new(f"Roadway Color: {source_name}", width=tw, height=th, alpha=True)
    image.pixels.foreach_set(np.asarray(pixels, dtype=np.float32))

    jpg_path = os.path.join(blend_dir, _safe_filename(f"Roadway_Color_{source_name}") + ".jpg")
    image.filepath_raw = jpg_path
    image.file_format = 'JPEG'
    image.save()

    # UVs: a per-vertex grid UV assigned to each loop by its vertex index.
    vert_uv = grid_uvs(nx, ny)
    uv_layer = new_mesh.uv_layers.new(name="UVMap")
    loop_vi = np.empty(len(new_mesh.loops), dtype=np.int64)
    new_mesh.loops.foreach_get("vertex_index", loop_vi)
    uv_layer.data.foreach_set("uv", vert_uv[loop_vi].reshape(-1))

    material = _build_image_texture_material(f"Roadway Surface: {source_name}", image)
    new_mesh.materials.append(material)
    return jpg_path


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
            depsgraph = context.evaluated_depsgraph_get()
            eval_obj = source.evaluated_get(depsgraph)
            mesh = eval_obj.to_mesh()
            try:
                count = len(mesh.vertices)
                if count < 3:
                    eval_obj.to_mesh_clear()
                    self.report({'ERROR'}, "Source object has too few vertices for a surface.")
                    return {'CANCELLED'}
                # Bulk-read coordinates (fast even for millions of vertices).
                local = np.empty(count * 3, dtype=np.float64)
                mesh.vertices.foreach_get("co", local)
                local = local.reshape(count, 3)

                colors = None
                if bool(scene.roadway_transfer_color):
                    color_attr = _find_point_color_attribute(mesh)
                    if color_attr is not None:
                        raw = np.empty(count * 4, dtype=np.float64)
                        color_attr.data.foreach_get("color", raw)
                        colors = raw.reshape(count, 4)
            finally:
                eval_obj.to_mesh_clear()

            wm.progress_update(25)

            # Transform to world space with a single vectorized matrix multiply.
            matrix = np.array(source.matrix_world, dtype=np.float64)
            points = local @ matrix[:3, :3].T + matrix[:3, 3]

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
                points, cell_size, fill_distance, ground_percentile, fill_holes, colors=colors
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

                made_material = False
                if bool(scene.roadway_bake_texture):
                    if bpy.data.filepath:
                        baked_texture_path = _apply_baked_texture(
                            source.name, new_mesh, result,
                            int(scene.roadway_texture_max_size),
                            os.path.dirname(bpy.data.filepath),
                        )
                        made_material = True
                    else:
                        self.report(
                            {'WARNING'},
                            "Save the .blend first to bake the roadway texture; "
                            "used a vertex-colour material instead.",
                        )
                if not made_material and (bool(scene.roadway_create_material) or bool(scene.roadway_bake_texture)):
                    material = _build_color_attribute_material(f"Roadway Surface: {source.name}", "Col")
                    new_mesh.materials.append(material)

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
                f"sampled from {len(points)} points.{texture_note}",
            )
            return {'FINISHED'}
        finally:
            wm.progress_end()
            if window is not None:
                window.cursor_set('DEFAULT')


classes = [
    HVE_OT_CreateRoadwaySurface,
]
