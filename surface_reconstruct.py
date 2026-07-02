"""Full 3D surface reconstruction from a point cloud, backed by Open3D.

This is a complement to the 2.5D heightfield Roadway Surface tool, not a
replacement. The heightfield tool is the right choice for drivable ground
surfaces; this one reconstructs a true 3D mesh (Poisson / ball-pivoting / alpha
shape) that can follow vertical and overhanging geometry — barriers, walls,
embankments, buildings, overpass structures.

Open3D is a heavy optional dependency; it is installed on first use (like the
E57/LAZ importer packages) and the operator fails gracefully with instructions
if the install can't complete.
"""

import math
import os

import bpy
import numpy as np

from .roadway_surface import (
    _log,
    _show_system_console,
    _read_point_cloud,
    _run_prefilters,
    _clip_object_box,
    _clip_object_triangles,
    _safe_filename,
    _build_image_texture_material,
    points_in_local_box,
    clip_box_axis_count,
    points_in_mesh_volume,
)

__all__ = [
    "HVE_OT_ReconstructSurface3D",
    "HVE_OT_BakeSurfaceTexture",
    "ball_pivoting_radii",
    "rasterize_uv_triangles",
    "scatter_uv_colors",
    "classes",
]


def _dilate_texture(img, written, passes):
    """Grow written texels outward to hide UV-island seams under filtering."""
    out = img.copy()
    wr = written.copy()
    for _ in range(max(int(passes), 0)):
        if wr.all():
            break
        acc = np.zeros_like(out)
        cnt = np.zeros(wr.shape, dtype=np.float64)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rolled = np.roll(out, (dy, dx), axis=(0, 1))
            rolled_w = np.roll(wr, (dy, dx), axis=(0, 1))
            acc += np.where(rolled_w[..., None], rolled, 0.0)
            cnt += rolled_w
        grow = (~wr) & (cnt > 0)
        if not grow.any():
            break
        out[grow] = acc[grow] / cnt[grow][..., None]
        wr = wr | grow
    return out, wr


def scatter_uv_colors(uvs, colors, width, height, dilate=4, fill=0.5):
    """Average per-point colours into a texture by their UV coordinates.

    Used for the cloud-sampled bake: each cloud point is placed at its UV on the
    surface and its colour accumulated into that texel (multiple points per texel
    are averaged), so the texture's detail comes from the point cloud, not the
    mesh resolution. ``uvs`` is (N, 2) in 0-1, ``colors`` is (N, 4). Returns
    ``(image, written)`` laid out bottom-row-first (Blender order). bpy-free.
    """
    img = np.full((height, width, 4), float(fill), dtype=np.float64)
    img[..., 3] = 1.0
    written = np.zeros((height, width), dtype=bool)
    uv = np.asarray(uvs, dtype=np.float64)
    col = np.asarray(colors, dtype=np.float64)
    if uv.shape[0] == 0:
        return img, written

    tx = np.clip(np.floor(uv[:, 0] * width).astype(np.int64), 0, width - 1)
    ty = np.clip(np.floor(uv[:, 1] * height).astype(np.int64), 0, height - 1)
    flat = ty * width + tx
    n = width * height
    csum = np.zeros((n, 4), dtype=np.float64)
    cnt = np.zeros(n, dtype=np.float64)
    np.add.at(csum, flat, col[:, :4])
    np.add.at(cnt, flat, 1.0)
    mask = cnt > 0

    out = img.reshape(n, 4)
    out[mask] = csum[mask] / cnt[mask][:, None]
    img = out.reshape(height, width, 4)
    written = mask.reshape(height, width)
    if dilate > 0:
        img, written = _dilate_texture(img, written, dilate)
    return img, written


def rasterize_uv_triangles(loop_uvs, loop_tris, loop_colors, width, height,
                           dilate=4, fill=0.5):
    """Rasterize per-corner colours into a texture through UV coordinates.

    ``loop_uvs`` is an (L, 2) array of UVs (0-1) per mesh loop, ``loop_tris`` an
    (T, 3) array of loop indices per triangle, and ``loop_colors`` an (L, 4)
    RGBA array. Each triangle is filled with barycentric-interpolated colour.
    Returns ``(image, written)`` where ``image`` is (height, width, 4) laid out
    bottom-row-first (Blender image order) and ``written`` marks covered texels.
    bpy-free, so it can be unit-tested without Blender.
    """
    img = np.full((height, width, 4), float(fill), dtype=np.float64)
    img[..., 3] = 1.0
    written = np.zeros((height, width), dtype=bool)

    uv = np.asarray(loop_uvs, dtype=np.float64)
    cols = np.asarray(loop_colors, dtype=np.float64)
    if uv.shape[0] == 0 or np.asarray(loop_tris).shape[0] == 0:
        return img, written
    px = uv[:, 0] * width
    py = uv[:, 1] * height

    for tri in np.asarray(loop_tris, dtype=np.int64):
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        xs = (px[a], px[b], px[c])
        ys = (py[a], py[b], py[c])
        x0 = max(int(np.floor(min(xs))), 0)
        x1 = min(int(np.ceil(max(xs))), width - 1)
        y0 = max(int(np.floor(min(ys))), 0)
        y1 = min(int(np.ceil(max(ys))), height - 1)
        if x1 < x0 or y1 < y0:
            continue
        denom = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(denom) < 1e-12:
            continue
        gx, gy = np.meshgrid(
            np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5
        )
        wa = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / denom
        wb = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / denom
        wc = 1.0 - wa - wb
        inside = (wa >= 0) & (wb >= 0) & (wc >= 0)
        if not inside.any():
            continue
        color = (
            wa[..., None] * cols[a] + wb[..., None] * cols[b] + wc[..., None] * cols[c]
        )
        sub = img[y0:y1 + 1, x0:x1 + 1]
        sub_w = written[y0:y1 + 1, x0:x1 + 1]
        sub[inside] = color[inside]
        sub_w[inside] = True

    if dilate > 0:
        img, written = _dilate_texture(img, written, dilate)
    return img, written


def ball_pivoting_radii(avg_spacing, multipliers=(0.75, 1.5, 3.0), scale=1.0):
    """Ball-pivoting radii derived from a cloud's average point spacing.

    A short ladder of increasing ball sizes lets the algorithm bridge both dense
    and sparse regions. ``scale`` widens the whole ladder — larger balls span
    bigger gaps and close holes (at the cost of bridging fine detail). Returns a
    plain list of floats (bpy-free, so it can be unit-tested without Open3D).
    """
    s = max(float(avg_spacing), 0.0)
    m = max(float(scale), 0.0)
    return [s * mult * m for mult in multipliers]


def _build_color_attribute_material(name, attribute_name):
    """Material whose Base Color is driven by a mesh colour attribute.

    Lets the reconstructed 3D surface display its per-vertex colour in Blender's
    Material Preview / Rendered view. (Vertex colour does not export to HVE; a
    baked texture would be needed for that.)
    """
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


def _clip_points_to_object(scene, source, points, colors):
    """Apply the panel's Clip To Object to a single cloud (for reconstruction).

    Mirrors the roadway surface tool's clip but for one point set. Returns
    ``(points, colors, note)``; a note string is empty when nothing was clipped.
    """
    clip_obj = getattr(scene, "roadway_clip_object", None)
    if clip_obj is None or clip_obj is source:
        return points, colors, ""

    mode = getattr(scene, "roadway_clip_mode", 'BOX')
    keep = None
    if mode == 'MESH':
        tris = _clip_object_triangles(clip_obj)
        if tris is not None and tris.shape[0] >= 4:
            flat = tris.reshape(-1, 3)
            tmin, tmax = flat.min(axis=0), flat.max(axis=0)
            in_box = np.all((points >= tmin) & (points <= tmax), axis=1)
            keep = np.zeros(points.shape[0], dtype=bool)
            if in_box.any():
                keep[in_box] = points_in_mesh_volume(points[in_box], tris)
    else:
        clip = _clip_object_box(clip_obj)
        if clip is not None and clip_box_axis_count(clip[1], clip[2]) >= 2:
            inv, bmin, bmax = clip
            keep = points_in_local_box(points, inv, bmin, bmax)

    if keep is None:
        return points, colors, ""
    n_before = len(points)
    points = points[keep]
    if colors is not None:
        colors = colors[keep]
    note = ""
    if keep.sum() != n_before:
        note = f" Clipped to {int(keep.sum())} points inside {clip_obj.name}."
    return points, colors, note


def _ensure_open3d():
    """Import Open3D, installing it into Blender's Python on first use.

    Returns the module, or raises RuntimeError with guidance on failure.
    """
    try:
        import open3d  # noqa: F401
        return open3d
    except ImportError:
        pass
    try:
        from .ply_pointcloud.operator import install_optional_packages
        install_optional_packages(["open3d"])
        import open3d  # noqa: F811
        return open3d
    except Exception as exc:  # noqa: BLE001 - surface install/import failure clearly
        raise RuntimeError(
            "3D reconstruction needs the 'open3d' package, which couldn't be "
            f"installed automatically ({exc}). Install it in Blender's Python "
            "with `pip install open3d` (it must match Blender's Python version), "
            "then restart Blender. If it still won't load, Open3D may not ship a "
            "wheel for this Blender build."
        ) from exc


def _reconstruct_mesh(o3d, points, colors, scene):
    """Run the chosen Open3D reconstruction. Returns (verts, tris, vcols|None)."""
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.ascontiguousarray(points, dtype=np.float64))
    if colors is not None and len(colors):
        pcd.colors = o3d.utility.Vector3dVector(
            np.ascontiguousarray(colors[:, :3], dtype=np.float64)
        )

    import time

    k = max(int(getattr(scene, "roadway_recon_normals_k", 30)), 4)
    t0 = time.perf_counter()
    _log(f"  estimating normals (k={k}, multithreaded)...")
    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=k))
    _log(f"  normals estimated in {time.perf_counter() - t0:.1f}s")

    orient = getattr(scene, "roadway_recon_orient", 'CONSISTENT')
    t0 = time.perf_counter()
    if orient == 'UP':
        _log("  orienting normals up (fast)...")
        pcd.orient_normals_to_align_with_direction(np.array([0.0, 0.0, 1.0]))
    else:
        _log("  orienting normals consistently (single-threaded; the slow step)...")
        try:
            pcd.orient_normals_consistent_tangent_plane(k)
        except Exception:  # noqa: BLE001 - fall back to a simple up-ish orientation
            pcd.orient_normals_to_align_with_direction(np.array([0.0, 0.0, 1.0]))
    _log(f"  normals oriented in {time.perf_counter() - t0:.1f}s")

    method = getattr(scene, "roadway_recon_method", 'POISSON')
    t0 = time.perf_counter()
    _log(f"  reconstructing ({method}, multithreaded)... this can take a while")
    if method == 'POISSON':
        depth = int(getattr(scene, "roadway_recon_depth", 9))
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=depth
        )
        trim = float(getattr(scene, "roadway_recon_density_trim", 0.05))
        densities = np.asarray(densities)
        if trim > 0 and densities.size:
            thresh = np.quantile(densities, trim)
            mesh.remove_vertices_by_mask(densities < thresh)
    elif method == 'BPA':
        dists = np.asarray(pcd.compute_nearest_neighbor_distance())
        avg = float(np.mean(dists)) if dists.size else 0.0
        scale = float(getattr(scene, "roadway_recon_bpa_radius_mult", 1.0))
        radii = ball_pivoting_radii(avg, scale=scale)
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd, o3d.utility.DoubleVector(radii)
        )
    else:  # ALPHA
        alpha = float(getattr(scene, "roadway_recon_alpha", 0.0))
        if alpha <= 0:
            dists = np.asarray(pcd.compute_nearest_neighbor_distance())
            avg = float(np.mean(dists)) if dists.size else 1.0
            alpha = avg * 5.0
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(pcd, alpha)

    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_unreferenced_vertices()

    verts = np.asarray(mesh.vertices)
    tris = np.asarray(mesh.triangles)
    vcols = np.asarray(mesh.vertex_colors) if mesh.has_vertex_colors() else None
    return verts, tris, vcols


class HVE_OT_ReconstructSurface3D(bpy.types.Operator):
    """Reconstruct a full 3D mesh surface from the selected point cloud with Open3D (Poisson / ball-pivoting / alpha shape). For vertical/overhanging geometry; the Roadway Surface tool remains best for drivable ground"""
    bl_idname = "object.reconstruct_surface_3d"
    bl_label = "Reconstruct 3D Surface"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        source = getattr(scene, "roadway_source_object", None) or context.object
        if source is None or source.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh point-cloud object (e.g. an imported cloud).")
            return {'CANCELLED'}

        wm = context.window_manager
        window = context.window
        wm.progress_begin(0, 100)
        if window is not None:
            window.cursor_set('WAIT')
        try:
            wm.progress_update(5)
            _show_system_console()
            _log(f"Reconstructing 3D surface from '{source.name}'...")
            local, colors, _attr = _read_point_cloud(source, True)
            if len(local) < 4:
                self.report({'ERROR'}, "Source object has too few vertices to reconstruct.")
                return {'CANCELLED'}

            matrix = np.array(source.matrix_world, dtype=np.float64)
            points = local @ matrix[:3, :3].T + matrix[:3, 3]

            # Honor the same pre-filters and clip as the roadway tool.
            points, colors, clip_note = _clip_points_to_object(scene, source, points, colors)
            points, colors, _n_before = _run_prefilters(scene, points, colors)
            if len(points) < 4:
                self.report({'WARNING'}, "Too few points after clip/filter; relax them.")
                return {'CANCELLED'}
            _log(f"  {len(points)} points after clip/filter")

            wm.progress_update(20)
            try:
                o3d = _ensure_open3d()
            except RuntimeError as exc:
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}

            wm.progress_update(35)
            verts, tris, vcols = _reconstruct_mesh(o3d, points, colors, scene)
            _log(f"  built mesh: {len(verts)} verts, {len(tris)} tris")
            wm.progress_update(80)
            if len(verts) == 0 or len(tris) == 0:
                self.report(
                    {'WARNING'},
                    "Reconstruction produced no mesh; try a different method, more "
                    "points, or a larger alpha / lower density trim.",
                )
                return {'CANCELLED'}

            mesh_name = f"3D Surface: {source.name}"
            new_mesh = bpy.data.meshes.new(mesh_name)
            new_mesh.from_pydata(verts.tolist(), [], tris.tolist())
            new_mesh.update()
            new_mesh.validate(clean_customdata=False)

            has_color = vcols is not None and len(vcols) == len(verts)
            if has_color:
                layer = new_mesh.color_attributes.new(name="Col", type='FLOAT_COLOR', domain='POINT')
                rgba = np.hstack([vcols, np.ones((len(vcols), 1))])
                layer.data.foreach_set("color", np.ascontiguousarray(rgba, dtype=np.float32).ravel())

            new_obj = bpy.data.objects.new(mesh_name, new_mesh)
            context.collection.objects.link(new_obj)
            # Remember the source cloud so the texture can be (re)baked from it,
            # and tag the object so the panel offers a rebake button.
            if has_color:
                new_obj["surface_3d"] = 1
                new_obj["surface_3d_source"] = source.name
            try:
                new_obj.hve_type.set_type.type = 'ENVIRONMENT'
            except (AttributeError, TypeError):
                pass

            for obj in list(context.selected_objects):
                obj.select_set(False)
            new_obj.select_set(True)
            context.view_layer.objects.active = new_obj

            # Auto-bake the colour texture now (fast next to reconstruction). Fall
            # back to a colour-attribute material if the bake can't run.
            tex_note = ""
            if has_color:
                wm.progress_update(85)
                _log("  baking colour texture...")
                try:
                    saved, tsize = bake_surface_texture(context, new_obj, scene)
                    tex_note = (
                        f" Texture {tsize}x{tsize}"
                        + (f" -> {os.path.basename(saved)}." if saved else " (packed; save the .blend).")
                    )
                except Exception as exc:  # noqa: BLE001 - keep the surface even if baking fails
                    _log(f"  texture bake failed ({exc}); keeping colour attribute")
                    new_mesh.materials.append(
                        _build_color_attribute_material(f"3D Surface: {source.name}", "Col")
                    )
                    tex_note = " (texture bake skipped; showing vertex colour)"

            wm.progress_update(100)
            method = getattr(scene, "roadway_recon_method", 'POISSON')
            self.report(
                {'INFO'},
                f"3D surface ({method}): {len(verts)} verts, {len(tris)} tris "
                f"from {len(points)} points.{clip_note}{tex_note}",
            )
            return {'FINISHED'}
        finally:
            wm.progress_end()
            if window is not None:
                window.cursor_set('DEFAULT')


def _cloud_texel_uvs(o3d, vert_world, tri_verts, tri_uv, cloud_points, dist_mult=3.0):
    """Map each cloud point to a UV on the surface via closest-point-on-mesh.

    Uses Open3D's raycasting scene to find, for every cloud point, the closest
    triangle and its barycentric coordinates, then interpolates that triangle's
    corner UVs. Returns ``(texel_uv, keep)`` where ``keep`` drops points that lie
    too far from the surface (> ``dist_mult`` x the median distance), so stray
    off-surface returns don't smear the texture.
    """
    scene = o3d.t.geometry.RaycastingScene()
    tmesh = o3d.t.geometry.TriangleMesh()
    tmesh.vertex.positions = o3d.core.Tensor(
        np.ascontiguousarray(vert_world, dtype=np.float32)
    )
    tmesh.triangle.indices = o3d.core.Tensor(
        np.ascontiguousarray(tri_verts, dtype=np.uint32)
    )
    scene.add_triangles(tmesh)

    query = o3d.core.Tensor(np.ascontiguousarray(cloud_points, dtype=np.float32))
    res = scene.compute_closest_points(query)
    prim = res['primitive_ids'].numpy().astype(np.int64)
    bary = res['primitive_uvs'].numpy().astype(np.float64)  # (N, 2)
    closest = res['points'].numpy().astype(np.float64)

    dist = np.linalg.norm(cloud_points - closest, axis=1)
    med = float(np.median(dist)) if dist.size else 0.0
    keep = dist <= (med * dist_mult) if med > 0 else np.ones(dist.shape[0], dtype=bool)

    # Barycentric weights: Open3D gives (u, v) for corners 1 and 2; corner 0 is
    # the remainder. Interpolate the triangle's corner UVs.
    w = np.empty((prim.shape[0], 3), dtype=np.float64)
    w[:, 1] = bary[:, 0]
    w[:, 2] = bary[:, 1]
    w[:, 0] = 1.0 - bary[:, 0] - bary[:, 1]
    sel = tri_uv[prim]  # (N, 3, 2)
    texel_uv = (w[:, :, None] * sel).sum(axis=1)
    return texel_uv, keep


def _color_attr(mesh):
    """The mesh's preferred colour attribute (Col, then active, then first)."""
    return (
        mesh.color_attributes.get("Col")
        or getattr(mesh.color_attributes, "active_color", None)
        or (mesh.color_attributes[0] if len(mesh.color_attributes) else None)
    )


def _ensure_uvs(context, obj):
    """Auto-unwrap (Smart UV Project) if the mesh has no UVs yet."""
    if obj.data.uv_layers:
        return
    _log(f"Unwrapping '{obj.name}' (Smart UV Project)...")
    prev_active = context.view_layer.objects.active
    prev_selected = list(context.selected_objects)
    try:
        bpy.ops.object.mode_set(mode='OBJECT')
    except RuntimeError:
        pass
    for o in prev_selected:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    context.view_layer.objects.active = prev_active or obj


def bake_surface_texture(context, obj, scene):
    """Unwrap ``obj``, bake a colour texture, and assign an image material.

    Prefers sampling the original point cloud (detail independent of the mesh);
    falls back to the mesh's vertex colours if the cloud isn't available. Returns
    ``(saved_path_or_None, size)``. Raises ``RuntimeError`` when the mesh can't be
    unwrapped or has no colour attribute. Shared by the auto-bake on reconstruct
    and the manual rebake operator.
    """
    # Unwrap BEFORE grabbing any mesh-data references: the Edit-mode round trip
    # reallocates attribute storage, so an earlier colour-attribute pointer would
    # dangle and crash Blender on foreach_get.
    _ensure_uvs(context, obj)
    mesh = obj.data
    if not mesh.uv_layers:
        raise RuntimeError("Couldn't create UVs for the mesh.")
    ca = _color_attr(mesh)
    if ca is None:
        raise RuntimeError("This mesh has no colour attribute to bake.")

    mesh.calc_loop_triangles()
    n_loops = len(mesh.loops)
    loop_uv = np.empty(n_loops * 2, dtype=np.float64)
    mesh.uv_layers.active.data.foreach_get("uv", loop_uv)
    loop_uv = loop_uv.reshape(n_loops, 2)

    if ca.domain == 'CORNER':
        cc = np.empty(n_loops * 4, dtype=np.float64)
        ca.data.foreach_get("color", cc)
        loop_colors = cc.reshape(n_loops, 4)
    else:  # POINT domain: gather each loop's vertex colour
        n_v = len(mesh.vertices)
        vc = np.empty(n_v * 4, dtype=np.float64)
        ca.data.foreach_get("color", vc)
        vc = vc.reshape(n_v, 4)
        lv = np.empty(n_loops, dtype=np.int64)
        mesh.loops.foreach_get("vertex_index", lv)
        loop_colors = vc[lv]

    n_tris = len(mesh.loop_triangles)
    tri_loops = np.empty(n_tris * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("loops", tri_loops)
    tri_loops = tri_loops.reshape(n_tris, 3)

    size = int(scene.roadway_texture_size)
    if size <= 0:
        size = 2048

    # Prefer sampling the texture directly from the original point cloud.
    img_arr = None
    source_name = str(obj.get("surface_3d_source", ""))
    src = bpy.data.objects.get(source_name) if source_name else None
    if src is not None and src.type == 'MESH':
        s_local, s_colors, _sa = _read_point_cloud(src, True)
        if s_colors is not None and len(s_local):
            try:
                o3d = _ensure_open3d()
                s_mw = np.array(src.matrix_world, dtype=np.float64)
                cloud_pts = s_local @ s_mw[:3, :3].T + s_mw[:3, 3]

                vco = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
                mesh.vertices.foreach_get("co", vco)
                vco = vco.reshape(len(mesh.vertices), 3)
                o_mw = np.array(obj.matrix_world, dtype=np.float64)
                vert_world = vco @ o_mw[:3, :3].T + o_mw[:3, 3]

                tri_verts = np.empty(n_tris * 3, dtype=np.int64)
                mesh.loop_triangles.foreach_get("vertices", tri_verts)
                tri_verts = tri_verts.reshape(n_tris, 3)
                tri_uv = loop_uv[tri_loops]  # (T, 3, 2)

                _log(f"  cloud-sampling {size}x{size} texture from {len(cloud_pts)} points...")
                texel_uv, keep = _cloud_texel_uvs(o3d, vert_world, tri_verts, tri_uv, cloud_pts)
                img_arr, _w = scatter_uv_colors(texel_uv[keep], s_colors[keep], size, size)
            except Exception as exc:  # noqa: BLE001 - fall back to vertex bake
                _log(f"  cloud sampling failed ({exc}); using vertex colours")
                img_arr = None

    if img_arr is None:
        _log(f"  baking {size}x{size} texture from {n_tris} mesh triangles...")
        img_arr, _written = rasterize_uv_triangles(loop_uv, tri_loops, loop_colors, size, size)

    image = bpy.data.images.new(
        f"3D Surface Color: {obj.name}", width=size, height=size, alpha=True
    )
    image.pixels.foreach_set(np.ascontiguousarray(img_arr.reshape(-1), dtype=np.float32))

    blend_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ""
    saved = None
    if blend_dir:
        saved = os.path.join(blend_dir, _safe_filename(f"3D_Surface_Color_{obj.name}") + ".jpg")
        image.filepath_raw = saved
        image.file_format = 'JPEG'
        image.save()
    else:
        image.pack()

    mesh.materials.clear()
    mesh.materials.append(_build_image_texture_material(f"3D Surface: {obj.name}", image))
    return saved, size


class HVE_OT_BakeSurfaceTexture(bpy.types.Operator):
    """Re-bake the selected 3D surface's colour texture at the current Texture Resolution (sampled from the point cloud, so detail isn't limited by the mesh)"""
    bl_idname = "object.bake_surface_texture"
    bl_label = "Rebake Texture (Selected 3D Surface)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None and obj.type == 'MESH'
            and len(obj.data.color_attributes) > 0
        )

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH' or len(obj.data.color_attributes) == 0:
            self.report({'ERROR'}, "Select a 3D surface mesh with colour to bake.")
            return {'CANCELLED'}

        window = context.window
        wm = context.window_manager
        wm.progress_begin(0, 100)
        if window is not None:
            window.cursor_set('WAIT')
        try:
            _show_system_console()
            saved, size = bake_surface_texture(context, obj, context.scene)
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            wm.progress_end()
            if window is not None:
                window.cursor_set('DEFAULT')

        if saved is None:
            self.report(
                {'WARNING'},
                f"Baked {size}x{size} texture (packed into the .blend; save the "
                ".blend and rebake to write the JPG for H3D export).",
            )
        else:
            self.report({'INFO'}, f"Baked texture: {os.path.basename(saved)} ({size}x{size}).")
        return {'FINISHED'}


class HVE_OT_TrimSurfaceToCloud(bpy.types.Operator):
    """Delete parts of the selected 3D surface that lie farther than the Trim Distance from the source point cloud — removes Poisson bulges and invented geometry after the surface is built"""
    bl_idname = "object.trim_surface_to_cloud"
    bl_label = "Trim Bulges (To Cloud)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.get("surface_3d_source")

    def execute(self, context):
        import bmesh

        scene = context.scene
        obj = context.active_object
        src_name = str(obj.get("surface_3d_source", ""))
        src = bpy.data.objects.get(src_name)
        if src is None or src.type != 'MESH':
            self.report(
                {'ERROR'},
                f"Source cloud '{src_name}' not found; keep it in the scene to trim.",
            )
            return {'CANCELLED'}

        window = context.window
        wm = context.window_manager
        wm.progress_begin(0, 100)
        if window is not None:
            window.cursor_set('WAIT')
        try:
            _show_system_console()
            try:
                o3d = _ensure_open3d()
            except RuntimeError as exc:
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}

            # Source cloud in world space.
            s_local, _c, _a = _read_point_cloud(src, False)
            s_mw = np.array(src.matrix_world, dtype=np.float64)
            cloud = s_local @ s_mw[:3, :3].T + s_mw[:3, 3]

            # Surface vertices in world space.
            mesh = obj.data
            nv = len(mesh.vertices)
            vco = np.empty(nv * 3, dtype=np.float64)
            mesh.vertices.foreach_get("co", vco)
            vco = vco.reshape(nv, 3)
            o_mw = np.array(obj.matrix_world, dtype=np.float64)
            vworld = vco @ o_mw[:3, :3].T + o_mw[:3, 3]

            wm.progress_update(30)
            cloud_pcd = o3d.geometry.PointCloud()
            cloud_pcd.points = o3d.utility.Vector3dVector(np.ascontiguousarray(cloud))
            vpcd = o3d.geometry.PointCloud()
            vpcd.points = o3d.utility.Vector3dVector(np.ascontiguousarray(vworld))

            # Distance from each surface vertex to the nearest cloud point.
            _log(f"  measuring {nv} vertices against {len(cloud)} cloud points...")
            dist = np.asarray(vpcd.compute_point_cloud_distance(cloud_pcd))

            thresh = float(scene.roadway_trim_distance)
            if thresh <= 0:
                nn = np.asarray(cloud_pcd.compute_nearest_neighbor_distance())
                avg = float(np.mean(nn)) if nn.size else 0.0
                thresh = avg * 10.0
            far = dist > thresh
            if not far.any():
                self.report({'INFO'}, f"No surface lies beyond {thresh:.3g}; nothing trimmed.")
                return {'CANCELLED'}
            if far.all():
                self.report(
                    {'WARNING'},
                    f"Every vertex is beyond {thresh:.3g}; raise Trim Distance (0 = auto).",
                )
                return {'CANCELLED'}

            wm.progress_update(70)
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.verts.ensure_lookup_table()
            del_verts = [bm.verts[int(i)] for i in np.nonzero(far)[0]]
            bmesh.ops.delete(bm, geom=del_verts, context='VERTS')
            bm.to_mesh(mesh)
            bm.free()
            mesh.update()

            wm.progress_update(100)
            self.report(
                {'INFO'},
                f"Trimmed {int(far.sum())} vertices beyond {thresh:.3g} from the cloud. "
                "Rebake the texture if needed.",
            )
            return {'FINISHED'}
        finally:
            wm.progress_end()
            if window is not None:
                window.cursor_set('DEFAULT')


classes = [HVE_OT_ReconstructSurface3D, HVE_OT_BakeSurfaceTexture, HVE_OT_TrimSurfaceToCloud]
