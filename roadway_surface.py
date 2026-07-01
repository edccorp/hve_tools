bl_info = {
    "name": "Roadway Surface from Point Cloud",
    "author": "EDC",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > HVE > Other Tools > Roadway Surface",
    "description": "Build a draped ground surface mesh from a point-cloud object for vehicle simulations",
    "category": "Object",
}

import bpy
import math

# ---------------------------------------------------------------------------
# Heightfield core
#
# These helpers are plain-Python (no bpy / mathutils) so the sampling and mesh
# generation can be unit tested outside Blender, matching the other tools in
# this add-on. The operator below feeds them world-space point tuples.
#
# The approach reproduces a "shrink-wrap from below" drape without needing a
# target surface: lay a regular XY grid at the chosen resolution, and for each
# grid vertex take a low percentile of the Z of nearby cloud points. The low
# percentile grabs the ground and ignores overhead noise (vehicles, foliage)
# while still rejecting the occasional spurious below-ground point.
# ---------------------------------------------------------------------------


def compute_xy_bounds(points):
    """Return ``(min_x, min_y, max_x, max_y)`` over 3D points, or None if empty."""
    if not points:
        return None
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for p in points:
        x, y = p[0], p[1]
        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        if y > max_y:
            max_y = y
    return (min_x, min_y, max_x, max_y)


def grid_dimensions(min_x, min_y, max_x, max_y, cell_size):
    """Number of grid vertices along X and Y for ``cell_size`` (each at least 2)."""
    if cell_size <= 0:
        raise ValueError("cell_size must be positive")
    span_x = max(max_x - min_x, 0.0)
    span_y = max(max_y - min_y, 0.0)
    nx = int(math.floor(span_x / cell_size)) + 1
    ny = int(math.floor(span_y / cell_size)) + 1
    return max(nx, 2), max(ny, 2)


def percentile(values, q):
    """Linear-interpolation percentile of ``values``; ``q`` in [0, 100]."""
    if not values:
        raise ValueError("percentile of empty sequence")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    q = min(max(q, 0.0), 100.0)
    rank = (q / 100.0) * (len(ordered) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return ordered[lo]
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _build_xy_bins(points, bin_size):
    """Bucket points into a dict keyed by integer ``(ix, iy)`` XY bin."""
    bins = {}
    for p in points:
        key = (int(math.floor(p[0] / bin_size)), int(math.floor(p[1] / bin_size)))
        bins.setdefault(key, []).append(p)
    return bins


def _neighbor_z(bins, bin_size, x, y, radius):
    """Return the Z values of points within ``radius`` (XY) of ``(x, y)``."""
    r2 = radius * radius
    cx = int(math.floor(x / bin_size))
    cy = int(math.floor(y / bin_size))
    span = int(math.ceil(radius / bin_size))
    zs = []
    for ix in range(cx - span, cx + span + 1):
        for iy in range(cy - span, cy + span + 1):
            for p in bins.get((ix, iy), ()):
                dx = p[0] - x
                dy = p[1] - y
                if dx * dx + dy * dy <= r2:
                    zs.append(p[2])
    return zs


def sample_heightfield(points, cell_size, search_radius, ground_percentile):
    """Sample a grid of ground Z from a point cloud.

    Returns a dict ``{origin_x, origin_y, cell_size, nx, ny, z_grid}`` where
    ``z_grid`` is a row-major list of length ``nx * ny``; each entry is a float
    ground height, or None where no points fell within ``search_radius`` of that
    grid vertex. Returns None when ``points`` is empty.
    """
    bounds = compute_xy_bounds(points)
    if bounds is None:
        return None
    min_x, min_y, max_x, max_y = bounds
    nx, ny = grid_dimensions(min_x, min_y, max_x, max_y, cell_size)

    bin_size = max(search_radius, cell_size)
    bins = _build_xy_bins(points, bin_size)

    z_grid = [None] * (nx * ny)
    for j in range(ny):
        gy = min_y + j * cell_size
        for i in range(nx):
            gx = min_x + i * cell_size
            zs = _neighbor_z(bins, bin_size, gx, gy, search_radius)
            if zs:
                z_grid[j * nx + i] = percentile(zs, ground_percentile)

    return {
        "origin_x": min_x,
        "origin_y": min_y,
        "cell_size": cell_size,
        "nx": nx,
        "ny": ny,
        "z_grid": z_grid,
    }


def fill_missing_heights(z_grid, nx, ny, max_passes=100):
    """Fill None cells from the average of their filled 4-neighbours, iterating.

    Returns a new list. Cells that stay unreachable (fully isolated regions)
    remain None.
    """
    grid = list(z_grid)
    for _ in range(max_passes):
        holes = [k for k, v in enumerate(grid) if v is None]
        if not holes:
            break
        updates = {}
        for k in holes:
            i = k % nx
            j = k // nx
            vals = []
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = i + di, j + dj
                if 0 <= ni < nx and 0 <= nj < ny:
                    nv = grid[nj * nx + ni]
                    if nv is not None:
                        vals.append(nv)
            if vals:
                updates[k] = sum(vals) / len(vals)
        if not updates:
            break
        for k, v in updates.items():
            grid[k] = v
    return grid


def build_surface_mesh(sample, fill_holes=True):
    """Turn a :func:`sample_heightfield` result into ``(verts, faces, filled, total)``.

    ``verts`` is a list of ``(x, y, z)``; ``faces`` a list of quad index tuples.
    A quad is emitted only when all four of its corners have a height, so gaps in
    the cloud leave holes rather than spikes. ``filled`` / ``total`` report how
    many grid cells were sampled.
    """
    nx = sample["nx"]
    ny = sample["ny"]
    cs = sample["cell_size"]
    ox = sample["origin_x"]
    oy = sample["origin_y"]

    heights = fill_missing_heights(sample["z_grid"], nx, ny) if fill_holes else list(sample["z_grid"])

    verts = []
    for j in range(ny):
        for i in range(nx):
            zz = heights[j * nx + i]
            verts.append((ox + i * cs, oy + j * cs, zz if zz is not None else 0.0))

    faces = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            b = j * nx + (i + 1)
            c = (j + 1) * nx + (i + 1)
            d = (j + 1) * nx + i
            if all(heights[idx] is not None for idx in (a, b, c, d)):
                faces.append((a, b, c, d))

    filled = sum(1 for v in heights if v is not None)
    return verts, faces, filled, len(heights)


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

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

        depsgraph = context.evaluated_depsgraph_get()
        eval_obj = source.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        try:
            matrix = source.matrix_world
            points = [tuple(matrix @ v.co) for v in mesh.vertices]
        finally:
            eval_obj.to_mesh_clear()

        if len(points) < 3:
            self.report({'ERROR'}, "Source object has too few vertices for a surface.")
            return {'CANCELLED'}

        cell_size = float(scene.roadway_cell_size)
        search_radius = float(scene.roadway_search_radius)
        ground_percentile = float(scene.roadway_ground_percentile)
        fill_holes = bool(scene.roadway_fill_holes)

        if search_radius < cell_size:
            self.report({'WARNING'}, "Search radius smaller than cell size may leave gaps.")

        sample = sample_heightfield(points, cell_size, search_radius, ground_percentile)
        if sample is None:
            self.report({'ERROR'}, "Could not sample the point cloud.")
            return {'CANCELLED'}

        verts, faces, filled, total = build_surface_mesh(sample, fill_holes=fill_holes)
        if not faces:
            self.report(
                {'WARNING'},
                "No cells had enough points; increase the search radius or cell size.",
            )
            return {'CANCELLED'}

        mesh_name = f"Roadway Surface: {source.name}"
        new_mesh = bpy.data.meshes.new(mesh_name)
        new_mesh.from_pydata(verts, [], [tuple(f) for f in faces])
        new_mesh.update()

        new_obj = bpy.data.objects.new(mesh_name, new_mesh)
        context.collection.objects.link(new_obj)

        # Classify as an HVE Environment object so it flows into H3D environment
        # export for vehicle simulations.
        try:
            new_obj.hve_type.set_type.type = 'ENVIRONMENT'
        except (AttributeError, TypeError):
            pass

        for obj in list(context.selected_objects):
            obj.select_set(False)
        new_obj.select_set(True)
        context.view_layer.objects.active = new_obj

        self.report(
            {'INFO'},
            f"Roadway surface: {sample['nx']}x{sample['ny']} grid, {len(faces)} faces, "
            f"{filled}/{total} cells sampled from {len(points)} points.",
        )
        return {'FINISHED'}


classes = [
    HVE_OT_CreateRoadwaySurface,
]
