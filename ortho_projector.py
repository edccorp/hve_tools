import bpy
from mathutils import Vector
from bpy.types import Operator, Panel
from bpy.props import (
    StringProperty, BoolProperty, IntProperty, EnumProperty
)

# -----------------------------------------------------------------------------
# Helpers (kept simple to match the requested operator behaviour)


def get_view3d_override(context):
    """Find a VIEW_3D + WINDOW region for operators that need UI context."""
    for win in context.window_manager.windows:
        screen = win.screen
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return {
                            "window": win,
                            "screen": screen,
                            "area": area,
                            "region": region,
                            "scene": context.scene,
                            "blend_data": bpy.data,
                        }
    return None


def bbox_world_corners(obj):
    mw = obj.matrix_world
    return [mw @ Vector(corner) for corner in obj.bound_box]


def approx_xy_extent(obj):
    cs = bbox_world_corners(obj)
    xs = [c.x for c in cs]
    ys = [c.y for c in cs]
    return max(max(xs) - min(xs), max(ys) - min(ys))


# -----------------------------------------------------------------------------
# Main operator (API and behaviour mirror the provided reference code)


class OBJECT_OT_project_ortho_bake(Operator):
    bl_idname = "object.project_ortho_bake"
    bl_label = "Project Ortho Image to UV"
    bl_options = {'REGISTER', 'UNDO'}

    # Camera selection exactly as requested
    camera_source: EnumProperty(
        name="Camera Source",
        items=[
            ('SELECTED', "Use Selected Camera", "Use the active object (must be a Camera)"),
            ('ACTIVE',   "Use Scene Active Camera", "Use scene.camera"),
            ('NEW',      "Create New Camera", "Create a new camera aligned to current view"),
        ],
        default='ACTIVE',
    )
    keep_new_as_scene_camera: BoolProperty(
        name="Keep New Camera As Scene Camera",
        description="If creating a new camera, keep it as scene.camera after finishing",
        default=False,
    )

    # Texture source exactly as requested
    source_mode: EnumProperty(
        name="Texture Source",
        items=[
            ('RENDER', "Render From Camera", "Render current camera view and use that image"),
            ('IMAGE',  "Use Existing Image", "Use an existing image in bpy.data.images"),
        ],
        default='RENDER',
    )
    existing_image_name: StringProperty(
        name="Existing Image",
        description="Name of an existing image in bpy.data.images (if Source=IMAGE)",
        default="",
    )

    # Render controls
    render_engine: EnumProperty(
        name="Render Engine",
        items=[('CYCLES', 'Cycles', ''), ('BLENDER_EEVEE', 'Eevee', '')],
        default='BLENDER_EEVEE',
    )
    make_camera_ortho: BoolProperty(
        name="Force Camera Orthographic",
        default=True,
    )
    image_size: IntProperty(
        name="Image Size",
        description="Square size (px) for render or new image",
        default=2048,
        min=64,
        max=16384,
    )

    # UV & material
    uv_map_name: StringProperty(name="UV Map Name", default="OrthoProjUV")
    material_name: StringProperty(name="Material Name", default="OrthoProj_MAT")
    create_new_material: BoolProperty(name="Create/Assign Material", default=True)

    # Project From View options
    use_bounds: BoolProperty(name="Project From View (Bounds)", default=True)
    correct_aspect: BoolProperty(name="Correct Aspect", default=True)
    scale_to_bounds: BoolProperty(name="Scale To Bounds", default=True)

    # ------------------------------------------------------------------
    # Camera resolution helpers

    def _resolve_camera(self, context, obj):
        scene = context.scene
        created_cam = None
        previous_scene_cam = scene.camera

        if self.camera_source == 'SELECTED':
            sel = context.view_layer.objects.active
            if not sel or sel.type != 'CAMERA':
                self.report({'ERROR'}, "Active object must be a Camera when Camera Source = Use Selected Camera.")
                return None, None
            scene.camera = sel
            return sel, previous_scene_cam

        elif self.camera_source == 'ACTIVE':
            if not scene.camera or scene.camera.type != 'CAMERA':
                self.report({'ERROR'}, "Scene needs an active Camera (scene.camera).")
                return None, None
            return scene.camera, None

        elif self.camera_source == 'NEW':
            cam_data = bpy.data.cameras.new("OrthoProjCam")
            created_cam = bpy.data.objects.new("OrthoProjCam", cam_data)
            context.scene.collection.objects.link(created_cam)
            scene.camera = created_cam

            # Try to align the new camera to the current 3D view
            override = get_view3d_override(context)
            if override:
                try:
                    bpy.ops.view3d.view_camera(override)
                    bpy.ops.view3d.camera_to_view(override)
                except Exception:
                    pass

            # Fallback: position above target if alignment failed
            if created_cam.matrix_world.translation.length == 0.0:
                bb = bbox_world_corners(obj)
                center = sum(bb, Vector((0, 0, 0))) / 8.0
                created_cam.location = center + Vector((0, 0, 5.0))
                created_cam.rotation_euler = (0.0, 0.0, 0.0)

            return created_cam, previous_scene_cam

        return None, None

    # ------------------------------------------------------------------

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object.")
            return {'CANCELLED'}

        scene = context.scene

        # Resolve camera
        cam, prev_scene_cam = self._resolve_camera(context, obj)
        if not cam:
            return {'CANCELLED'}

        # Ortho and framing
        if self.make_camera_ortho:
            cam.data.type = 'ORTHO'
            try:
                extent = max(approx_xy_extent(obj), 0.001)
                cam.data.ortho_scale = extent * 1.2
            except Exception:
                pass

        # Render settings
        scene.render.engine = self.render_engine
        scene.render.resolution_x = self.image_size
        scene.render.resolution_y = self.image_size
        scene.render.resolution_percentage = 100

        # Ensure viewport is through chosen camera for 1:1 UV projection
        override = get_view3d_override(context)
        if override:
            try:
                bpy.ops.view3d.view_camera(override)
            except Exception:
                pass

        # Source image
        if self.source_mode == 'RENDER':
            bpy.ops.render.render(write_still=False)
            src_img = bpy.data.images.get("Render Result")
            if not src_img:
                self.report({'ERROR'}, "Couldn't get Render Result.")
                return {'CANCELLED'}
            baked_name = f"OrthoRender_{self.image_size:d}"
            new_img = bpy.data.images.new(baked_name, width=self.image_size, height=self.image_size, alpha=True, float_buffer=False)
            new_img.pixels = src_img.pixels[:]
            src_img = new_img
        else:
            if not self.existing_image_name:
                self.report({'ERROR'}, "Provide an existing image name or switch Source to Render.")
                return {'CANCELLED'}
            src_img = bpy.data.images.get(self.existing_image_name)
            if not src_img:
                self.report({'ERROR'}, f"Image '{self.existing_image_name}' not found.")
                return {'CANCELLED'}

        # UV setup
        uv_layer = obj.data.uv_layers.get(self.uv_map_name)
        if not uv_layer:
            uv_layer = obj.data.uv_layers.new(name=self.uv_map_name)
        obj.data.uv_layers.active = uv_layer

        # Project From View
        prev_mode = obj.mode
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='FACE')
        bpy.ops.mesh.select_all(action='SELECT')

        try:
            if override:
                bpy.ops.uv.project_from_view(
                    override,
                    camera_bounds=self.use_bounds,
                    correct_aspect=self.correct_aspect,
                    scale_to_bounds=self.scale_to_bounds,
                )
            else:
                bpy.ops.uv.project_from_view(
                    camera_bounds=self.use_bounds,
                    correct_aspect=self.correct_aspect,
                    scale_to_bounds=self.scale_to_bounds,
                )
        except Exception as e:
            bpy.ops.object.mode_set(mode=prev_mode)
            self.report({'ERROR'}, f"Project From View failed: {e}")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode=prev_mode)

        # Create/assign simple material
        if self.create_new_material:
            mat = bpy.data.materials.get(self.material_name)
            if not mat:
                mat = bpy.data.materials.new(self.material_name)
                mat.use_nodes = True
            nt = mat.node_tree
            nodes = nt.nodes
            links = nt.links

            principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if not principled:
                principled = nodes.new("ShaderNodeBsdfPrincipled")
                principled.location = (200, 0)
            out = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if not out:
                out = nodes.new("ShaderNodeOutputMaterial")
                out.location = (400, 0)

            # remove previous labelled image nodes to avoid clutter
            for n in [n for n in nodes if n.type == 'TEX_IMAGE' and n.label == "OrthoProjImage"]:
                nodes.remove(n)

            tex = nodes.new("ShaderNodeTexImage")
            tex.label = "OrthoProjImage"
            tex.image = src_img
            tex.location = (-200, 0)

            # ensure links
            for l in list(principled.inputs['Base Color'].links):
                links.remove(l)
            links.new(tex.outputs['Color'], principled.inputs['Base Color'])
            if not principled.outputs['BSDF'].links:
                links.new(principled.outputs['BSDF'], out.inputs['Surface'])

            # assign
            if obj.data.materials:
                if obj.active_material is None:
                    obj.data.materials[0] = mat
                else:
                    obj.active_material = mat
            else:
                obj.data.materials.append(mat)

        # Show the image in any open Image Editor
        try:
            for area in context.screen.areas:
                if area.type == 'IMAGE_EDITOR':
                    for space in area.spaces:
                        if space.type == 'IMAGE_EDITOR':
                            space.image = src_img
        except Exception:
            pass

        # Restore previous scene camera when needed
        if prev_scene_cam and prev_scene_cam != cam:
            if self.camera_source == 'NEW':
                if not self.keep_new_as_scene_camera:
                    context.scene.camera = prev_scene_cam
            else:
                context.scene.camera = prev_scene_cam

        self.report({'INFO'}, f"Projected image '{src_img.name}' with camera '{cam.name}' onto UV '{self.uv_map_name}'.")
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Panel (reintroduces UI controls for the operator)


class HVE_PT_ortho_projector(Panel):
    bl_idname = "HVE_PT_ortho_projector"
    bl_label = "Ortho Projector"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.label(text="Project mesh UVs from an orthographic view")

        op_props = layout.operator(
            OBJECT_OT_project_ortho_bake.bl_idname,
            text="Project Ortho Image",
            icon='IMAGE_DATA',
        )

        box = layout.box()
        box.label(text="Camera")
        box.prop(op_props, "camera_source")
        box.prop(op_props, "keep_new_as_scene_camera")

        box = layout.box()
        box.label(text="Image Source")
        box.prop(op_props, "source_mode")
        box.prop(op_props, "existing_image_name")

        box = layout.box()
        box.label(text="Render")
        box.prop(op_props, "render_engine")
        box.prop(op_props, "make_camera_ortho")
        box.prop(op_props, "image_size")

        box = layout.box()
        box.label(text="UV & Material")
        box.prop(op_props, "uv_map_name")
        box.prop(op_props, "material_name")
        box.prop(op_props, "create_new_material")

        box = layout.box()
        box.label(text="Project From View")
        box.prop(op_props, "use_bounds")
        box.prop(op_props, "correct_aspect")
        box.prop(op_props, "scale_to_bounds")


# -----------------------------------------------------------------------------
# Simple menu hook (kept identical to the provided reference)


def menu_func(self, context):
    self.layout.operator(OBJECT_OT_project_ortho_bake.bl_idname, icon='RENDER_STILL')


classes = (
    OBJECT_OT_project_ortho_bake,

    HVE_PT_ortho_projector,

)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_object.remove(menu_func)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
