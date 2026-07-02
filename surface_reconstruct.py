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

import os

import bpy
import numpy as np

from .roadway_surface import (
    _log,
    _read_point_cloud,
    _run_prefilters,
    _clip_object_box,
    _clip_object_triangles,
    points_in_local_box,
    clip_box_axis_count,
    points_in_mesh_volume,
)

__all__ = ["HVE_OT_ReconstructSurface3D", "ball_pivoting_radii", "classes"]


def ball_pivoting_radii(avg_spacing, multipliers=(0.75, 1.5, 3.0)):
    """Ball-pivoting radii derived from a cloud's average point spacing.

    A short ladder of increasing ball sizes lets the algorithm bridge both dense
    and sparse regions. Returns a plain list of floats (bpy-free, so it can be
    unit-tested without Open3D).
    """
    s = max(float(avg_spacing), 0.0)
    return [s * m for m in multipliers]


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

    k = max(int(getattr(scene, "roadway_recon_normals_k", 30)), 4)
    _log("  estimating and orienting point normals...")
    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=k))
    # Consistently orient normals so Poisson gets a coherent inside/outside.
    try:
        pcd.orient_normals_consistent_tangent_plane(k)
    except Exception:  # noqa: BLE001 - fall back to a simple up-ish orientation
        pcd.orient_normals_to_align_with_direction(np.array([0.0, 0.0, 1.0]))

    method = getattr(scene, "roadway_recon_method", 'POISSON')
    _log(f"  reconstructing ({method})... this can take a while")
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
        radii = ball_pivoting_radii(avg)
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

            if vcols is not None and len(vcols) == len(verts):
                layer = new_mesh.color_attributes.new(name="Col", type='FLOAT_COLOR', domain='POINT')
                rgba = np.hstack([vcols, np.ones((len(vcols), 1))])
                layer.data.foreach_set("color", np.ascontiguousarray(rgba, dtype=np.float32).ravel())
                # Assign a material that shows the colour attribute, so the mesh
                # renders coloured in Material Preview / Rendered view.
                new_mesh.materials.append(
                    _build_color_attribute_material(f"3D Surface: {source.name}", "Col")
                )

            new_obj = bpy.data.objects.new(mesh_name, new_mesh)
            context.collection.objects.link(new_obj)
            try:
                new_obj.hve_type.set_type.type = 'ENVIRONMENT'
            except (AttributeError, TypeError):
                pass

            for obj in list(context.selected_objects):
                obj.select_set(False)
            new_obj.select_set(True)
            context.view_layer.objects.active = new_obj

            wm.progress_update(100)
            method = getattr(scene, "roadway_recon_method", 'POISSON')
            self.report(
                {'INFO'},
                f"3D surface ({method}): {len(verts)} verts, {len(tris)} tris "
                f"from {len(points)} points.{clip_note} Classified as Environment.",
            )
            return {'FINISHED'}
        finally:
            wm.progress_end()
            if window is not None:
                window.cursor_set('DEFAULT')


classes = [HVE_OT_ReconstructSurface3D]
