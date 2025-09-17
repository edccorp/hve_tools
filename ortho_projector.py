"""Tools for orthographic projection utilities used by the HVE toolkit."""

from __future__ import annotations

import math
import os
import tempfile
from typing import Iterable, List, Optional, Sequence, Tuple

try:
    import bpy
    from bpy.props import (
        BoolProperty,
        EnumProperty,
        IntVectorProperty,
        PointerProperty,
        StringProperty,
    )
    from bpy.types import Area, Context, Image, Object, Operator, Panel, PropertyGroup
    from mathutils import Matrix, Vector
    from bpy_extras.object_utils import world_to_camera_view
except ModuleNotFoundError:  # pragma: no cover - allows unit tests to import without Blender
    bpy = None  # type: ignore
    Area = Context = Image = Object = Operator = Panel = PropertyGroup = object  # type: ignore
    BoolProperty = EnumProperty = IntVectorProperty = PointerProperty = StringProperty = None  # type: ignore
    Matrix = Vector = None  # type: ignore
    world_to_camera_view = None  # type: ignore


# -----------------------------------------------------------------------------
# Helper utilities replicated from the reference add-on


def engine_items(self, context: Optional[Context]) -> List[Tuple[str, str, str]]:
    """Return the available render engines for the scene."""

    if bpy is None:  # pragma: no cover - Blender specific
        return []

    if context is None:
        context = bpy.context

    enum_prop = bpy.types.RenderSettings.bl_rna.properties.get("engine")
    if enum_prop is None:  # pragma: no cover - safety guard
        return []

    items = []
    for item in enum_prop.enum_items:
        if item.identifier:  # skip empty identifiers such as deprecated entries
            items.append((item.identifier, item.name, item.description))
    return items


def normalize_engine(context: Optional[Context], engine: str) -> str:
    """Ensure the requested engine exists, falling back to the current engine."""

    if bpy is None:  # pragma: no cover - Blender specific
        return engine

    if context is None:
        context = bpy.context

    valid = {identifier for identifier, _, _ in engine_items(None, context)}
    if engine in valid:
        return engine
    return context.scene.render.engine


def find_view3d_rv3d(context: Context) -> Tuple[Optional[Area], Optional[object], Optional[object]]:
    """Return the first available 3D view area and its regions."""

    if bpy is None:  # pragma: no cover - Blender specific
        return None, None, None

    window = context.window
    if window is None:
        return None, None, None

    for area in window.screen.areas:  # type: ignore[union-attr]
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type == 'WINDOW':
                space = area.spaces.active
                rv3d = getattr(space, "region_3d", None)
                return area, region, rv3d
    return None, None, None


def align_new_camera_to_active_view(context: Context, camera_obj: Object) -> None:
    """Align a freshly created camera to the active 3D viewport."""

    if bpy is None:  # pragma: no cover - Blender specific
        return

    area, region, rv3d = find_view3d_rv3d(context)
    if rv3d is None:
        return

    view_matrix: Matrix = rv3d.view_matrix.copy()  # type: ignore[assignment]
    camera_obj.matrix_world = view_matrix.inverted()

    if rv3d.view_perspective == 'ORTHO':  # type: ignore[union-attr]
        camera_obj.data.type = 'ORTHO'
        camera_obj.data.ortho_scale = rv3d.view_distance * 2.0  # type: ignore[union-attr]


def _world_bounds(objects: Sequence[Object]) -> Tuple[Vector, Vector]:
    """Compute the world-space bounding box for a set of objects."""

    if Vector is None:  # pragma: no cover - Blender specific
        raise RuntimeError("mathutils.Vector is required")

    min_corner = Vector((math.inf, math.inf, math.inf))
    max_corner = Vector((-math.inf, -math.inf, -math.inf))

    for obj in objects:
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            min_corner.x = min(min_corner.x, world_corner.x)
            min_corner.y = min(min_corner.y, world_corner.y)
            min_corner.z = min(min_corner.z, world_corner.z)
            max_corner.x = max(max_corner.x, world_corner.x)
            max_corner.y = max(max_corner.y, world_corner.y)
            max_corner.z = max(max_corner.z, world_corner.z)

    return min_corner, max_corner


def set_camera_ortho_and_fit(
    camera_obj: Object,
    targets: Sequence[Object],
    force_ortho: bool,
    scale_to_bounds: bool,
) -> None:
    """Configure a camera for orthographic projection and frame the targets."""

    if bpy is None:  # pragma: no cover - Blender specific
        return

    camera_data = camera_obj.data
    if force_ortho:
        camera_data.type = 'ORTHO'

    if camera_data.type != 'ORTHO' or not scale_to_bounds or not targets:
        return

    min_corner, max_corner = _world_bounds(targets)
    dimensions = max_corner - min_corner
    ortho_scale = max(dimensions.x, dimensions.y)
    camera_data.ortho_scale = max(ortho_scale, 0.001)

    centre = (min_corner + max_corner) * 0.5
    camera_obj.location = centre


def safe_render_to_image(
    context: Context,
    camera_obj: Object,
    render_engine: str,
    image_size: Sequence[int],
) -> Image:
    """Render the active scene with the supplied camera and return a packed image."""

    if bpy is None:  # pragma: no cover - Blender specific
        raise RuntimeError("bpy is required for rendering")

    scene = context.scene
    render = scene.render
    previous_camera = scene.camera
    previous_engine = render.engine
    previous_filepath = render.filepath
    previous_res_x = render.resolution_x
    previous_res_y = render.resolution_y

    tmp_dir = tempfile.mkdtemp(prefix="hve_ortho_")
    tmp_path = os.path.join(tmp_dir, "ortho_projection.png")

    try:
        scene.camera = camera_obj
        render.engine = normalize_engine(context, render_engine)
        render.resolution_x = int(image_size[0])
        render.resolution_y = int(image_size[1])
        render.filepath = tmp_path

        bpy.ops.render.render(write_still=True)

        image = bpy.data.images.load(tmp_path)
        image.pack()
    finally:
        scene.camera = previous_camera
        render.engine = previous_engine
        render.filepath = previous_filepath
        render.resolution_x = previous_res_x
        render.resolution_y = previous_res_y
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:  # pragma: no cover - best effort cleanup
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:  # pragma: no cover - directory may not be empty on failure
            pass

    return image


def project_uvs_from_camera(
    context: Context,
    target_obj: Object,
    camera_obj: Object,
    uv_map_name: str,
    clamp_uv: bool,
) -> None:
    """Project the object's UVs from the perspective of the supplied camera."""

    if bpy is None or world_to_camera_view is None:  # pragma: no cover - Blender specific
        return
    if target_obj.type != 'MESH':
        return

    mesh = target_obj.data
    uv_layer = mesh.uv_layers.get(uv_map_name)
    if uv_layer is None:
        uv_layer = mesh.uv_layers.new(name=uv_map_name)

    scene = context.scene

    for loop in mesh.loops:
        vertex = mesh.vertices[loop.vertex_index]
        world_coord = target_obj.matrix_world @ vertex.co
        co_ndc = world_to_camera_view(scene, camera_obj, world_coord)
        u = co_ndc.x
        v = co_ndc.y
        if clamp_uv:
            u = min(max(u, 0.0), 1.0)
            v = min(max(v, 0.0), 1.0)
        uv_layer.data[loop.index].uv = (u, v)


def _iter_visible_objects(context: Context) -> Iterable[Object]:
    """Return the visible objects in the scene."""

    for obj in context.scene.objects:
        if obj.visible_get():
            yield obj


# -----------------------------------------------------------------------------
# Property group definition


class OrthoProjectSettings(PropertyGroup):
    """Settings controlling orthographic projection behaviour."""

    target_object: PointerProperty(
        name="Target Mesh",
        description="Mesh object to project from the active camera",
        type=Object,
    )

    camera_source: EnumProperty(
        name="Camera Source",
        description="Choose which camera to render from",
        items=(
            ("SCENE", "Scene Camera", "Use the scene's active camera"),
            ("ACTIVE", "Active Object", "Use the active object if it is a camera"),
            ("NEW", "New Camera", "Create a new camera aligned to the viewport"),
        ),
        default="SCENE",
    )

    render_engine: EnumProperty(
        name="Render Engine",
        description="Render engine used to produce the baked image",
        items=engine_items,
    )

    image_size: IntVectorProperty(
        name="Image Size",
        description="Resolution of the generated orthographic render",
        size=2,
        default=(1024, 1024),
        min=4,
    )

    uv_map_name: StringProperty(
        name="UV Map",
        description="Name of the UV map that receives the projection",
        default="OrthoUV",
    )

    material_name: StringProperty(
        name="Material",
        description="Material to assign with the rendered image",
        default="Ortho Projection",
    )

    force_ortho: BoolProperty(
        name="Force Orthographic",
        description="Ensure the camera is set to orthographic mode",
        default=True,
    )

    scale_to_bounds: BoolProperty(
        name="Fit To Bounds",
        description="Scale and position the camera to enclose the mesh",
        default=True,
    )

    clamp_uv: BoolProperty(
        name="Clamp UV",
        description="Clamp projected UV coordinates to the [0, 1] range",
        default=True,
    )

    keep_new_as_scene_camera: BoolProperty(
        name="Keep As Scene Camera",
        description="Keep newly created cameras assigned as the scene camera",
        default=False,
    )

    @classmethod
    def register(cls) -> None:  # pragma: no cover - Blender registration hooks
        if bpy is None:
            return
        bpy.types.Scene.ortho_project_settings = PointerProperty(type=cls)

    @classmethod
    def unregister(cls) -> None:  # pragma: no cover - Blender registration hooks
        if bpy is None:
            return
        if hasattr(bpy.types.Scene, "ortho_project_settings"):
            del bpy.types.Scene.ortho_project_settings


# -----------------------------------------------------------------------------
# Operator logic


def _resolve_target_object(context: Context, settings: OrthoProjectSettings) -> Optional[Object]:
    if settings.target_object is not None and settings.target_object.type == 'MESH':
        return settings.target_object

    active = context.view_layer.objects.active
    if active is not None and active.type == 'MESH':
        return active

    for obj in _iter_visible_objects(context):
        if obj.type == 'MESH':
            return obj
    return None


def _resolve_camera(context: Context, settings: OrthoProjectSettings) -> Tuple[Optional[Object], bool]:
    """Return a camera object and whether it was freshly created."""

    if settings.camera_source == 'ACTIVE':
        active = context.view_layer.objects.active
        if active is not None and active.type == 'CAMERA':
            return active, False

    if settings.camera_source == 'NEW' or context.scene.camera is None:
        camera_data = bpy.data.cameras.new(name="HVE Ortho Camera")
        camera_obj = bpy.data.objects.new(camera_data.name, camera_data)
        context.scene.collection.objects.link(camera_obj)
        align_new_camera_to_active_view(context, camera_obj)
        if settings.keep_new_as_scene_camera or context.scene.camera is None:
            context.scene.camera = camera_obj
        return camera_obj, True

    return context.scene.camera, False


class HVE_OT_project_ortho(Operator):
    """Project a mesh to an orthographic render and bake to a material."""

    bl_idname = "hve.project_ortho"
    bl_label = "Project Ortho"
    bl_description = "Render an orthographic view and project it to the mesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context) -> bool:
        return bpy is not None and context.scene is not None

    def execute(self, context: Context):
        if bpy is None:  # pragma: no cover - Blender specific
            return {'CANCELLED'}

        settings: OrthoProjectSettings = context.scene.ortho_project_settings

        target_obj = _resolve_target_object(context, settings)
        if target_obj is None:
            self.report({'WARNING'}, "No mesh object available for projection")
            return {'CANCELLED'}

        camera_obj, _ = _resolve_camera(context, settings)
        if camera_obj is None:
            self.report({'WARNING'}, "Unable to determine a camera for rendering")
            return {'CANCELLED'}

        if settings.force_ortho or settings.scale_to_bounds:
            set_camera_ortho_and_fit(
                camera_obj,
                [target_obj],
                force_ortho=settings.force_ortho,
                scale_to_bounds=settings.scale_to_bounds,
            )

        image = safe_render_to_image(
            context,
            camera_obj,
            settings.render_engine,
            settings.image_size,
        )

        project_uvs_from_camera(
            context,
            target_obj,
            camera_obj,
            settings.uv_map_name or "UVMap",
            settings.clamp_uv,
        )

        self._ensure_material(target_obj, image, settings.material_name)

        self.report({'INFO'}, f"Projected orthographic image onto {target_obj.name}")
        return {'FINISHED'}

    def _ensure_material(self, target_obj: Object, image: Image, material_name: str) -> None:
        material = bpy.data.materials.get(material_name)
        if material is None:
            material = bpy.data.materials.new(material_name)
        material.use_nodes = True

        node_tree = material.node_tree
        nodes = node_tree.nodes
        links = node_tree.links

        output_node = nodes.get("Material Output")
        if output_node is None:
            output_node = nodes.new(type='ShaderNodeOutputMaterial')
            output_node.location = (400, 0)

        principled = None
        for node in nodes:
            if node.type == 'BSDF_PRINCIPLED':
                principled = node
                break
        if principled is None:
            principled = nodes.new(type='ShaderNodeBsdfPrincipled')
            principled.location = (0, 0)

        image_node = None
        for node in nodes:
            if node.type == 'TEX_IMAGE':
                image_node = node
                break
        if image_node is None:
            image_node = nodes.new(type='ShaderNodeTexImage')
            image_node.location = (-300, 0)
        image_node.image = image

        # Ensure the node links exist.
        def _has_link(output_socket, input_socket) -> bool:
            return any(link.from_socket == output_socket and link.to_socket == input_socket for link in links)

        if not _has_link(principled.outputs['BSDF'], output_node.inputs['Surface']):
            links.new(principled.outputs['BSDF'], output_node.inputs['Surface'])

        if not _has_link(image_node.outputs['Color'], principled.inputs['Base Color']):
            links.new(image_node.outputs['Color'], principled.inputs['Base Color'])

        if material.name not in [slot.material.name if slot.material else "" for slot in target_obj.material_slots]:
            if target_obj.data.materials:
                target_obj.data.materials[0] = material
            else:
                target_obj.data.materials.append(material)


# -----------------------------------------------------------------------------
# UI Panel


class HVE_PT_ortho_projector(Panel):
    bl_label = "Ortho Projector"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_parent_id = "HVE_PT_post"

    @classmethod
    def poll(cls, context: Context) -> bool:
        return bpy is not None and context.scene is not None

    def draw(self, context: Context) -> None:
        if bpy is None:  # pragma: no cover - Blender specific
            return

        layout = self.layout
        settings: OrthoProjectSettings = context.scene.ortho_project_settings

        box = layout.box()
        box.label(text="Target")
        box.prop(settings, "target_object")

        box = layout.box()
        box.label(text="Camera")
        box.prop(settings, "camera_source", text="Source")
        if settings.camera_source == 'NEW':
            box.prop(settings, "keep_new_as_scene_camera")
        box.prop(settings, "force_ortho")
        box.prop(settings, "scale_to_bounds")

        box = layout.box()
        box.label(text="Render")
        box.prop(settings, "render_engine", text="Engine")
        box.prop(settings, "image_size")

        box = layout.box()
        box.label(text="UV & Material")
        box.prop(settings, "uv_map_name")
        box.prop(settings, "clamp_uv")
        box.prop(settings, "material_name")

        layout.operator(HVE_OT_project_ortho.bl_idname, icon='CAMERA_DATA')


classes = (
    OrthoProjectSettings,
    HVE_OT_project_ortho,
    HVE_PT_ortho_projector,
)

