
"""
Blender Ortho Projector add-on ported to match the provided reference script.
"""

bl_info = {
    "name": "Ortho Projector",
    "author": "ChatGPT",
    "version": (1, 6, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Ortho Projector",
    "description": "Render from a camera and project the image onto mesh UVs (viewport-independent)",
    "category": "UV",
}

import os
import tempfile

import bpy
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def engine_items(_self, _context):
    """Dynamic engine list from RenderSettings enum (works with Eevee Next in 4.5)."""
    try:
        enum_items = bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items
        supported = {'CYCLES', 'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT', 'BLENDER_WORKBENCH'}
        items = []
        for e in enum_items:
            if e.identifier in supported:
                label = 'Eevee' if e.identifier.startswith('BLENDER_EEVEE') else e.name
                items.append((e.identifier, label, ''))
        if items:
            return items
    except Exception:
        pass
    return [('CYCLES', 'Cycles', '')]


def normalize_engine(identifier: str) -> str:
    """Map requested engine to one actually available in this Blender."""
    try:
        available = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
    except Exception:
        available = {'CYCLES'}
    eng = identifier if isinstance(identifier, str) else 'CYCLES'
    if eng == 'BLENDER_EEVEE' and 'BLENDER_EEVEE' not in available and 'BLENDER_EEVEE_NEXT' in available:
        eng = 'BLENDER_EEVEE_NEXT'
    if eng not in available:
        eng = 'CYCLES' if 'CYCLES' in available else next(iter(available))
    return eng


def find_view3d_rv3d(context):
    """Return (window, area, region, rv3d) for a VIEW_3D WINDOW region, else (None, None, None, None)."""
    for win in context.window_manager.windows:
        screen = win.screen
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return win, area, region, area.spaces.active.region_3d
    return None, None, None, None


def align_new_camera_to_active_view(context, cam_obj):
    """
    Align cam_obj to the current 3D View WITHOUT using operators:
    cam.matrix_world = view_matrix.inverted()
    If no VIEW_3D is available, aim from +Z world toward scene/mesh center.
    """
    win, area, region, rv3d = find_view3d_rv3d(context)
    if rv3d:
        # viewport view_matrix transforms from world to view; invert for camera world transform
        cam_obj.matrix_world = rv3d.view_matrix.inverted()
        return True
    # Fallback: point from +Z toward scene origin
    cam_obj.location = Vector((0, 0, 10))
    cam_obj.rotation_euler = (0.0, 0.0, 0.0)
    return False


def set_camera_ortho_and_fit(obj, cam):
    """Switch camera to ORTHO and fit ortho_scale to XY extent of obj."""
    cam.data.type = 'ORTHO'
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    extent = max(max(xs) - min(xs), max(ys) - min(ys))
    cam.data.ortho_scale = max(extent * 1.2, 0.001)


def safe_render_to_image(scene, base_name="OrthoProject", size=2048):
    """Render to a temp PNG, then load & pack it. Returns an Image datablock."""
    tmp_dir = bpy.app.tempdir or tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, base_name + ".png")

    # Save/restore render props
    old_path = scene.render.filepath
    old_fmt = scene.render.image_settings.file_format
    old_rx = scene.render.resolution_x
    old_ry = scene.render.resolution_y
    old_rp = scene.render.resolution_percentage

    # Square render
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100

    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = tmp_path
    bpy.ops.render.render(write_still=True)

    # Restore
    scene.render.filepath = old_path
    scene.render.image_settings.file_format = old_fmt
    scene.render.resolution_x = old_rx
    scene.render.resolution_y = old_ry
    scene.render.resolution_percentage = old_rp

    if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
        raise RuntimeError("Rendered file not found or empty.")

    img = bpy.data.images.load(tmp_path)
    try:
        img.pack()
    except Exception:
        pass
    return img


def _mesh_poll(_self, obj):
    return obj and obj.type == 'MESH'


# -------------------------------------------------------------------
# Core UV projection (no operators, no viewport dependency)
# -------------------------------------------------------------------


def project_uvs_from_camera(scene, obj, cam_obj, uv_map_name,
                            scale_to_bounds=True, clamp_01=False):
    """
    For each loop on the mesh, compute UV by projecting the loop's vertex world position
    into the camera's normalized frame with world_to_camera_view.
    If scale_to_bounds=True, normalize UVs so the projected bbox of the mesh fills 0..1.
    """
    if obj.type != 'MESH' or cam_obj.type != 'CAMERA':
        raise TypeError("project_uvs_from_camera: needs a mesh object and a camera object.")

    # Ensure UV layer
    uv_layer = obj.data.uv_layers.get(uv_map_name)
    if not uv_layer:
        uv_layer = obj.data.uv_layers.new(name=uv_map_name)
    obj.data.uv_layers.active = uv_layer

    mw = obj.matrix_world
    verts = obj.data.vertices
    loops = obj.data.loops

    # First pass: compute projected UVs per loop
    uv_values = [None] * len(loops)
    umin = vmin = float('inf')
    umax = vmax = float('-inf')

    for li, loop in enumerate(loops):
        v = verts[loop.vertex_index]
        world_co = mw @ v.co
        uvw = world_to_camera_view(scene, cam_obj, world_co)  # (u,v,wdepth)
        u, v = float(uvw.x), float(uvw.y)
        uv_values[li] = (u, v)
        if scale_to_bounds:
            if u < umin:
                umin = u
            if v < vmin:
                vmin = v
            if u > umax:
                umax = u
            if v > vmax:
                vmax = v

    # Normalize to 0..1 based on projected bbox if requested
    if scale_to_bounds:
        du = max(umax - umin, 1e-8)
        dv = max(vmax - vmin, 1e-8)
        for li, (u, v) in enumerate(uv_values):
            u = (u - umin) / du
            v = (v - vmin) / dv
            if clamp_01:
                u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
                v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
            uv_layer.data[li].uv = (u, v)
    else:
        for li, (u, v) in enumerate(uv_values):
            if clamp_01:
                u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
                v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
            uv_layer.data[li].uv = (u, v)


# -------------------------------------------------------------------
# Properties
# -------------------------------------------------------------------


class OrthoProjectSettings(bpy.types.PropertyGroup):
    @classmethod
    def register(cls):
        if not hasattr(bpy.types.Scene, "ortho_project_settings"):
            bpy.types.Scene.ortho_project_settings = bpy.props.PointerProperty(type=cls)

    @classmethod
    def unregister(cls):
        if hasattr(bpy.types.Scene, "ortho_project_settings"):
            del bpy.types.Scene.ortho_project_settings

    target_object: bpy.props.PointerProperty(
        name="Target Mesh",
        type=bpy.types.Object,
        poll=_mesh_poll
    )
    camera_source: bpy.props.EnumProperty(
        name="Camera",
        items=[
            ('ACTIVE', "Scene Active", "Use scene.camera"),
            ('SELECTED', "Selected Camera", "Use the active object (must be Camera)"),
            ('NEW', "New Camera (from View)", "Create a new camera aligned to current 3D View"),
        ],
        default='ACTIVE'
    )
    # When items is a function: default must be an integer index
    render_engine: bpy.props.EnumProperty(
        name="Engine",
        items=engine_items,
        default=0
    )
    image_size: bpy.props.IntProperty(name="Image Size", default=2048, min=64, max=16384)
    uv_map_name: bpy.props.StringProperty(name="UV Map", default="OrthoProjUV")
    material_name: bpy.props.StringProperty(name="Material", default="OrthoProj_MAT")
    force_ortho: bpy.props.BoolProperty(name="Force Ortho", default=True)
    scale_to_bounds: bpy.props.BoolProperty(name="Scale to Bounds", default=True)
    clamp_uv: bpy.props.BoolProperty(name="Clamp UVs 0..1", default=False)
    keep_new_as_scene_camera: bpy.props.BoolProperty(
        name="Keep New Camera",
        description="If a new camera is created, keep it as scene.camera after projection",
        default=False
    )


# -------------------------------------------------------------------
# Operator
# -------------------------------------------------------------------


class OBJECT_OT_ortho_project(bpy.types.Operator):
    bl_idname = "object.ortho_project"
    bl_label = "Execute Projection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.ortho_project_settings

        # Resolve target mesh
        obj = s.target_object or context.object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh or pick one in 'Target Mesh'.")
            return {'CANCELLED'}

        # Ensure selectable/active
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.select_set(True)
        context.view_layer.objects.active = obj

        # Resolve camera
        scene = context.scene
        cam_obj = None
        prev_scene_cam = scene.camera

        if s.camera_source == 'ACTIVE':
            cam_obj = scene.camera
            if not cam_obj or cam_obj.type != 'CAMERA':
                self.report({'ERROR'}, "scene.camera must be a Camera.")
                return {'CANCELLED'}

        elif s.camera_source == 'SELECTED':
            a = context.view_layer.objects.active
            if not a or a.type != 'CAMERA':
                self.report({'ERROR'}, "Active object must be a Camera when using 'Selected Camera'.")
                return {'CANCELLED'}
            cam_obj = a

        elif s.camera_source == 'NEW':
            bpy.ops.object.camera_add()
            cam_obj = context.view_layer.objects.active
            # Align to current viewport (matrix-level), so render truly matches the view
            align_new_camera_to_active_view(context, cam_obj)

        if not cam_obj:
            self.report({'ERROR'}, "Could not resolve a camera.")
            return {'CANCELLED'}

        # Force orthographic + fit to object (keeps alignment/rotation from above)
        if s.force_ortho:
            try:
                set_camera_ortho_and_fit(obj, cam_obj)
            except Exception:
                cam_obj.data.type = 'ORTHO'

        # Ensure the render uses THIS camera
        scene.camera = cam_obj

        # Render (to temp file), load image
        scene.render.engine = normalize_engine(s.render_engine)
        try:
            img = safe_render_to_image(scene, base_name=s.material_name, size=s.image_size)
        except Exception as e:
            self.report({'ERROR'}, f"Render failed: {e}")
            return {'CANCELLED'}

        # Compute UVs directly from camera — no operators, no viewport dependency
        try:
            project_uvs_from_camera(
                scene, obj, cam_obj, s.uv_map_name,
                scale_to_bounds=s.scale_to_bounds,
                clamp_01=s.clamp_uv
            )
        except Exception as e:
            self.report({'ERROR'}, f"UV projection failed: {e}")
            return {'CANCELLED'}

        # Build/assign material with the rendered image
        mat = bpy.data.materials.get(s.material_name)
        if not mat:
            mat = bpy.data.materials.new(s.material_name)
            mat.use_nodes = True
        nt = mat.node_tree
        nodes = nt.nodes
        links = nt.links

        principled = nodes.get("Principled BSDF")
        if not principled:
            principled = nodes.new("ShaderNodeBsdfPrincipled")
            principled.location = (200, 0)
        out = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if not out:
            out = nodes.new("ShaderNodeOutputMaterial")
            out.location = (400, 0)

        # Remove prior labeled image nodes
        for n in [n for n in nodes if n.type == 'TEX_IMAGE' and n.label == "OrthoProjImage"]:
            nodes.remove(n)

        tex = nodes.new("ShaderNodeTexImage")
        tex.label = "OrthoProjImage"
        tex.image = img
        tex.location = (-200, 0)

        # Rewire
        for l in list(principled.inputs['Base Color'].links):
            links.remove(l)
        links.new(tex.outputs['Color'], principled.inputs['Base Color'])
        if not principled.outputs['BSDF'].links:
            links.new(principled.outputs['BSDF'], out.inputs['Surface'])

        if obj.data.materials:
            obj.active_material = mat
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

        # Restore previous scene camera if we created a new one and the user doesn't want to keep it
        if s.camera_source == 'NEW' and prev_scene_cam and not s.keep_new_as_scene_camera:
            scene.camera = prev_scene_cam

        self.report({'INFO'}, f"Rendered from '{cam_obj.name}' and projected onto '{obj.name}'.")
        return {'FINISHED'}


# -------------------------------------------------------------------
# Panel
# -------------------------------------------------------------------


class VIEW3D_PT_ortho_projector(bpy.types.Panel):
    bl_label = "Ortho Projector"
    bl_idname = "VIEW3D_PT_ortho_projector"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Ortho Projector"

    def draw(self, context):
        layout = self.layout
        s = getattr(context.scene, "ortho_project_settings", None)

        if not s:
            layout.label(text="Ortho Project settings unavailable.", icon='ERROR')
            layout.label(text="Reload the add-on to continue.")
            return

        col = layout.column(align=True)
        col.prop(s, "target_object")
        col.prop(s, "camera_source")
        if s.camera_source == 'NEW':
            col.prop(s, "keep_new_as_scene_camera")
        col.separator()

        col.prop(s, "force_ortho")
        col.prop(s, "render_engine")
        col.prop(s, "image_size")
        col.separator()

        col.prop(s, "uv_map_name")
        col.prop(s, "material_name")
        col.separator()

        col.prop(s, "scale_to_bounds")
        col.prop(s, "clamp_uv")
        col.separator()

        col.operator("object.ortho_project", icon='RENDER_STILL', text="Execute Projection")


# -------------------------------------------------------------------
# Register
# -------------------------------------------------------------------


classes = (
    OrthoProjectSettings,
    OBJECT_OT_ortho_project,
    VIEW3D_PT_ortho_projector,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
