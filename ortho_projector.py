"""Tools for framing objects with an orthographic camera.

This module provides a property group that controls the framing behaviour,
operators that perform the framing, and a UI panel to expose the settings in
Blender's sidebar.  The functionality is intentionally self contained so the
main add-on can import and register the exposed classes tuple.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

try:
    import bpy
    from bpy.props import (
        BoolProperty,
        EnumProperty,
        FloatProperty,
        PointerProperty,
        StringProperty,
    )
    from bpy.types import Context, Object, Operator, Panel, PropertyGroup
    from mathutils import Vector
except ModuleNotFoundError:  # pragma: no cover - makes tests runnable without Blender
    bpy = None  # type: ignore
    BoolProperty = EnumProperty = FloatProperty = PointerProperty = StringProperty = None  # type: ignore
    Context = Object = Operator = Panel = PropertyGroup = object  # type: ignore
    Vector = None  # type: ignore


_GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT", "GPENCIL", "VOLUME"}
_AXIS_TO_ROTATION = {
    "TOP": (math.radians(90.0), 0.0, 0.0),
    "BOTTOM": (math.radians(-90.0), 0.0, 0.0),
    "FRONT": (math.radians(90.0), 0.0, math.radians(180.0)),
    "BACK": (math.radians(90.0), 0.0, 0.0),
    "RIGHT": (math.radians(90.0), 0.0, math.radians(-90.0)),
    "LEFT": (math.radians(90.0), 0.0, math.radians(90.0)),
}
_AXIS_TO_DIRECTION = {
    "TOP": Vector((0.0, 0.0, 1.0)) if Vector else (0.0, 0.0, 1.0),
    "BOTTOM": Vector((0.0, 0.0, -1.0)) if Vector else (0.0, 0.0, -1.0),
    "FRONT": Vector((0.0, -1.0, 0.0)) if Vector else (0.0, -1.0, 0.0),
    "BACK": Vector((0.0, 1.0, 0.0)) if Vector else (0.0, 1.0, 0.0),
    "RIGHT": Vector((1.0, 0.0, 0.0)) if Vector else (1.0, 0.0, 0.0),
    "LEFT": Vector((-1.0, 0.0, 0.0)) if Vector else (-1.0, 0.0, 0.0),
}


def _iter_target_objects(context: Context, use_selection: bool) -> List[Object]:
    """Return the objects that should influence the projection bounds."""

    if bpy is None:  # pragma: no cover - executed only outside Blender
        return []

    if use_selection and context.selected_objects:
        objects = list(context.selected_objects)
    else:
        objects = [obj for obj in context.scene.objects if obj.visible_get()]

    geometry_objects = [obj for obj in objects if obj.type in _GEOMETRY_TYPES]

    # Fall back to the active object if nothing matched the geometry set.
    if not geometry_objects and context.active_object is not None:
        geometry_objects = [context.active_object]

    return geometry_objects


def _calculate_world_bounds(objects: Sequence[Object]) -> Tuple[Vector, Vector]:
    """Compute a world-space bounding box for the supplied objects."""

    if bpy is None or Vector is None:  # pragma: no cover - only relevant without Blender
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)  # type: ignore

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


def _ensure_camera(context: Context, settings: "OrthoProjectSettings") -> Object:
    """Return a camera object to update, creating it when required."""

    if bpy is None:  # pragma: no cover - executed only outside Blender
        raise RuntimeError("bpy is not available")

    if settings.use_active_camera and context.scene.camera is not None:
        return context.scene.camera

    camera_obj = bpy.data.objects.get(settings.camera_name)
    if camera_obj is None or camera_obj.type != "CAMERA":
        camera_data = bpy.data.cameras.get(settings.camera_name)
        if camera_data is None:
            camera_data = bpy.data.cameras.new(settings.camera_name)
        camera_obj = bpy.data.objects.new(settings.camera_name, camera_data)
        context.scene.collection.objects.link(camera_obj)

    if settings.make_active_camera:
        context.scene.camera = camera_obj

    return camera_obj


def _ortho_scale_for_bounds(min_corner: Vector, max_corner: Vector, margin: float) -> float:
    dimensions = max_corner - min_corner
    max_dim = max(dimensions.x, dimensions.y)
    scale = max_dim * (1.0 + margin)
    # Guard against extremely small geometry: Blender clamps at near-zero.
    return max(scale, 0.001)


def _position_camera(
    camera_obj: Object,
    min_corner: Vector,
    max_corner: Vector,
    axis: str,
    margin: float,
    distance_multiplier: float,
) -> None:
    """Align the supplied camera object to frame the bounding box."""

    if bpy is None:  # pragma: no cover - executed only outside Blender
        return
    if Vector is None:  # pragma: no cover - Blender always provides mathutils
        return

    camera_data = camera_obj.data
    if camera_data.type != 'ORTHO':
        camera_data.type = 'ORTHO'

    ortho_scale = _ortho_scale_for_bounds(min_corner, max_corner, margin)
    camera_data.ortho_scale = ortho_scale

    centre = (min_corner + max_corner) * 0.5
    direction = _AXIS_TO_DIRECTION[axis]

    if isinstance(direction, Vector):
        unit_direction = direction
    else:  # pragma: no cover - only relevant when the direction is a tuple
        unit_direction = Vector(direction)

    box_size = max((max_corner - min_corner).length, 0.001)
    offset = unit_direction.normalized() * box_size * distance_multiplier
    camera_obj.location = centre + offset

    rotation = _AXIS_TO_ROTATION[axis]
    camera_obj.rotation_euler = rotation


class OrthoProjectSettings(PropertyGroup):
    """Settings that control how the orthographic projection is calculated."""

    use_selection: BoolProperty(
        name="Use Selection",
        description="Limit the projection bounds to the current selection",
        default=True,
    )

    use_active_camera: BoolProperty(
        name="Use Active Camera",
        description="Update the existing active camera when available",
        default=True,
    )

    make_active_camera: BoolProperty(
        name="Set As Active",
        description="Assign the updated camera as the scene's active camera",
        default=True,
    )

    camera_name: StringProperty(
        name="Camera Name",
        description="Name for a camera created by the operator",
        default="HVE Ortho Camera",
    )

    axis: EnumProperty(
        name="Axis",
        description="Direction to look when creating the orthographic shot",
        items=(
            ("TOP", "Top (+Z)", "Look towards the negative Z axis"),
            ("BOTTOM", "Bottom (-Z)", "Look towards the positive Z axis"),
            ("FRONT", "Front (-Y)", "Look towards the positive Y axis"),
            ("BACK", "Back (+Y)", "Look towards the negative Y axis"),
            ("RIGHT", "Right (+X)", "Look towards the negative X axis"),
            ("LEFT", "Left (-X)", "Look towards the positive X axis"),
        ),
        default="TOP",
    )

    margin: FloatProperty(
        name="Margin",
        description="Additional scale applied to the computed orthographic size",
        default=0.1,
        min=0.0,
        soft_max=1.0,
    )

    distance_multiplier: FloatProperty(
        name="Distance",
        description=(
            "How far away from the bounding box to place the camera, "
            "expressed as a multiple of the box size"
        ),
        default=1.5,
        min=0.01,
    )

    @classmethod
    def register(cls) -> None:  # pragma: no cover - Blender registration
        if bpy is None:
            return
        bpy.types.Scene.ortho_project_settings = PointerProperty(type=cls)

    @classmethod
    def unregister(cls) -> None:  # pragma: no cover - Blender registration
        if bpy is None:
            return
        if hasattr(bpy.types.Scene, "ortho_project_settings"):
            del bpy.types.Scene.ortho_project_settings


class HVE_OT_project_ortho(Operator):
    """Frame the chosen objects with an orthographic camera."""

    bl_idname = "hve.project_ortho"
    bl_label = "Update Ortho Camera"
    bl_description = "Create or update an orthographic camera that frames the selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context) -> bool:
        return bpy is not None and context is not None and context.scene is not None

    def execute(self, context: Context):
        if bpy is None:  # pragma: no cover - executed only outside Blender
            return {'CANCELLED'}

        settings: OrthoProjectSettings = context.scene.ortho_project_settings
        targets = _iter_target_objects(context, settings.use_selection)
        if not targets:
            self.report({'WARNING'}, "No valid objects to frame")
            return {'CANCELLED'}

        min_corner, max_corner = _calculate_world_bounds(targets)
        camera_obj = _ensure_camera(context, settings)
        _position_camera(
            camera_obj,
            min_corner,
            max_corner,
            settings.axis,
            settings.margin,
            settings.distance_multiplier,
        )

        self.report({'INFO'}, f"Updated {camera_obj.name} for an orthographic shot")
        return {'FINISHED'}


class HVE_PT_ortho_projector(Panel):
    bl_label = "Ortho Projector"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_parent_id = "HVE_PT_other_tools"

    @classmethod
    def poll(cls, context: Context) -> bool:
        return bpy is not None and context.scene is not None

    def draw(self, context: Context) -> None:
        if bpy is None:  # pragma: no cover - executed only outside Blender
            return

        layout = self.layout
        settings: OrthoProjectSettings = context.scene.ortho_project_settings

        col = layout.column(align=True)
        col.prop(settings, "axis")
        col.prop(settings, "margin")
        col.prop(settings, "distance_multiplier")

        layout.separator()

        col = layout.column(align=True)
        col.prop(settings, "use_selection")
        col.prop(settings, "use_active_camera")
        col.prop(settings, "make_active_camera")
        col.prop(settings, "camera_name")

        layout.separator()
        layout.operator(HVE_OT_project_ortho.bl_idname, icon='CAMERA_DATA')


classes = (
    OrthoProjectSettings,
    HVE_OT_project_ortho,
    HVE_PT_ortho_projector,
)
