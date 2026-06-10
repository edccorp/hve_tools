import math

import bpy
from mathutils import Vector

bl_info = {
    'name': 'Motion Path to Curve',
    'category': 'Converter',
    'author': 'EDC',
    'version': (1, 7),
    'blender': (4, 3, 0),
    'description': 'Generates motion paths and converts them into curves, organizing them in a collection.',
}

FORWARD_AXIS_VECTORS = {
    'LOCAL_X': (1.0, 0.0, 0.0),
    'LOCAL_NEG_X': (-1.0, 0.0, 0.0),
    'LOCAL_Y': (0.0, 1.0, 0.0),
    'LOCAL_NEG_Y': (0.0, -1.0, 0.0),
    'LOCAL_Z': (0.0, 0.0, 1.0),
    'LOCAL_NEG_Z': (0.0, 0.0, -1.0),
}


def get_or_create_motion_path_collection():
    """Creates a collection called 'Motion Paths' if it doesn't exist."""
    collection_name = "Motion Paths"
    if collection_name in bpy.data.collections:
        return bpy.data.collections[collection_name]

    new_collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(new_collection)
    return new_collection


def create_motion_path(ob):
    """Generates a motion path for the given object."""
    bpy.context.view_layer.objects.active = ob
    if ob.motion_path:
        bpy.ops.object.paths_clear()  # Clear any existing motion path

    bpy.ops.object.paths_calculate()

    return ob.motion_path is not None


def delete_motion_path(ob):
    """Clears a motion path from the given object."""
    bpy.context.view_layer.objects.active = ob
    if ob.motion_path:
        bpy.ops.object.paths_clear()  # Clear any existing motion path

    return ob.motion_path is not None


def create_curve_from_motion_path(ob, context):
    """Creates a curve based on an object's motion path and adds it to the 'Motion Paths' collection."""
    if not ob.motion_path or not ob.motion_path.points:
        print(f"Skipping {ob.name}: No valid motion path found.")
        return None

    mp = ob.motion_path

    path = bpy.data.curves.new(name=f"{ob.name}_path", type='CURVE')
    curve_obj = bpy.data.objects.new(name=f"{ob.name}_path", object_data=path)

    motion_path_collection = get_or_create_motion_path_collection()
    motion_path_collection.objects.link(curve_obj)

    path.dimensions = '3D'
    spline = path.splines.new(type='BEZIER')
    spline.bezier_points.add(len(mp.points) - 1)

    for i, p in enumerate(spline.bezier_points):
        p.co = mp.points[i].co
        p.handle_right_type = 'VECTOR'
        p.handle_left_type = 'VECTOR'

    return curve_obj


def toggle_motion_path_visibility():
    """Toggles the visibility of motion paths for selected objects."""
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.overlay.show_motion_paths = not space.overlay.show_motion_paths
                    state = "enabled" if space.overlay.show_motion_paths else "disabled"
                    print(f"Motion Paths overlay {state}.")


def get_scene_fps(scene):
    """Return the effective scene frame rate, respecting Blender's fps_base."""
    render = scene.render
    fps_base = getattr(render, "fps_base", 1.0) or 1.0
    return render.fps / fps_base


def iter_marker_frame_times(frame_start, frame_end, fps, interval_seconds):
    """Yield sample frame values from the start to end frame at a time interval."""
    interval_seconds = max(float(interval_seconds), 1.0 / fps)
    frame_step = interval_seconds * fps
    frame_value = float(frame_start)

    while frame_value <= frame_end + 1e-6:
        yield frame_value
        frame_value += frame_step


def split_frame_value(frame_value):
    """Split a floating frame value into Blender frame and subframe arguments."""
    whole_frame = math.floor(frame_value)
    subframe = frame_value - whole_frame
    return whole_frame, subframe


def get_forward_axis_vector(axis_name):
    return Vector(FORWARD_AXIS_VECTORS.get(axis_name, FORWARD_AXIS_VECTORS['LOCAL_X']))


def get_object_forward_direction(eval_obj, forward_axis, yaw_offset_deg):
    """Return a normalized world-space XY forward direction for an evaluated object."""
    rot = eval_obj.matrix_world.to_3x3()
    fwd = rot @ get_forward_axis_vector(forward_axis)
    fwd.z = 0.0

    if fwd.length < 1e-8:
        fwd = Vector((0.0, 1.0, 0.0))
    else:
        fwd.normalize()

    angle = math.radians(yaw_offset_deg)
    c = math.cos(angle)
    s = math.sin(angle)
    fwd = Vector((
        c * fwd.x - s * fwd.y,
        s * fwd.x + c * fwd.y,
        0.0,
    ))

    if fwd.length < 1e-8:
        return Vector((0.0, 1.0, 0.0))

    fwd.normalize()
    return fwd


def build_triangle_marker_vertices(location, forward_direction, size):
    """Return world-space vertices for a triangular direction marker."""
    size = max(float(size), 0.001)
    right = Vector((forward_direction.y, -forward_direction.x, 0.0))

    if right.length < 1e-8:
        right = Vector((1.0, 0.0, 0.0))
    else:
        right.normalize()

    tip = location + forward_direction * size
    base_center = location - forward_direction * (size * 0.5)
    half_width = size * 0.45

    return (
        tip,
        base_center + right * half_width,
        base_center - right * half_width,
    )


def remove_existing_marker_object(name):
    old_obj = bpy.data.objects.get(name)
    if old_obj is None:
        return

    old_mesh = old_obj.data
    bpy.data.objects.remove(old_obj, do_unlink=True)

    if old_mesh and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)


def create_timed_location_markers(
    context,
    ob,
    interval_seconds,
    marker_size,
    forward_axis,
    yaw_offset_deg,
    replace_existing=True,
):
    """Create a mesh of triangular markers at the object's animated location over time."""
    scene = context.scene
    depsgraph = context.evaluated_depsgraph_get()
    fps = get_scene_fps(scene)
    marker_name = f"{ob.name}_time_markers"

    if replace_existing:
        remove_existing_marker_object(marker_name)

    original_frame = scene.frame_current
    original_subframe = getattr(scene, "frame_subframe", 0.0)
    verts = []
    faces = []

    try:
        for frame_value in iter_marker_frame_times(
            scene.frame_start,
            scene.frame_end,
            fps,
            interval_seconds,
        ):
            frame, subframe = split_frame_value(frame_value)
            scene.frame_set(frame, subframe=subframe)
            eval_obj = ob.evaluated_get(depsgraph)
            location = eval_obj.matrix_world.translation.copy()
            forward = get_object_forward_direction(eval_obj, forward_axis, yaw_offset_deg)
            marker_verts = build_triangle_marker_vertices(location, forward, marker_size)
            start_index = len(verts)
            verts.extend(marker_verts)
            faces.append((start_index, start_index + 1, start_index + 2))
    finally:
        scene.frame_set(original_frame, subframe=original_subframe)

    if not verts:
        return None

    mesh = bpy.data.meshes.new(marker_name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()

    marker_obj = bpy.data.objects.new(marker_name, mesh)
    marker_obj["source_object"] = ob.name
    marker_obj["interval_seconds"] = interval_seconds
    marker_obj["forward_axis"] = forward_axis
    marker_obj["yaw_offset_deg"] = yaw_offset_deg

    motion_path_collection = get_or_create_motion_path_collection()
    motion_path_collection.objects.link(marker_obj)

    return marker_obj


class GenerateMotionPathOperator(bpy.types.Operator):
    """Generates motion paths for selected objects"""
    bl_idname = "object.generate_motion_path"
    bl_label = "Generate Motion Paths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for ob in bpy.context.selected_objects:
            if create_motion_path(ob):
                count += 1

        self.report({'INFO'}, f"Generated motion paths for {count} objects.")
        return {'FINISHED'}


class RemoveMotionPathOperator(bpy.types.Operator):
    """Removes motion paths from selected objects"""
    bl_idname = "object.remove_motion_path"
    bl_label = "Remove Motion Paths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for ob in bpy.context.selected_objects:
            had_path = ob.motion_path is not None
            delete_motion_path(ob)
            if had_path:
                count += 1

        self.report({'INFO'}, f"Removed motion paths from {count} objects.")
        return {'FINISHED'}


class ConvertAllObjectsOperator(bpy.types.Operator):
    """Converts all objects' motion paths to curves"""
    bl_idname = "object.convert_motion_path_all"
    bl_label = "Convert All Objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for ob in bpy.data.objects:
            if create_curve_from_motion_path(ob, context):
                count += 1

        self.report({'INFO'}, f"Converted {count} motion paths to curves.")
        return {'FINISHED'}


class ConvertSelectedObjectsOperator(bpy.types.Operator):
    """Converts selected objects' motion paths to curves"""
    bl_idname = "object.convert_motion_path_selected"
    bl_label = "Convert Selected Objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for ob in bpy.context.selected_objects:
            if create_curve_from_motion_path(ob, context):
                count += 1

        self.report({'INFO'}, f"Converted {count} motion paths to curves.")
        return {'FINISHED'}


class ToggleMotionPathVisibilityOperator(bpy.types.Operator):
    """Toggles the visibility of motion paths for selected objects"""
    bl_idname = "object.toggle_motion_path_visibility"
    bl_label = "Toggle Motion Paths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        toggle_motion_path_visibility()
        self.report({'INFO'}, "Toggled motion path visibility.")
        return {'FINISHED'}


class CreateTimedLocationMarkersOperator(bpy.types.Operator):
    """Creates triangular location markers for selected animated objects at a time interval"""
    bl_idname = "object.create_timed_location_markers"
    bl_label = "Create Time Location Markers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        selected_objects = list(context.selected_objects)

        if not selected_objects:
            self.report({'ERROR'}, "Select at least one object to mark.")
            return {'CANCELLED'}

        count = 0
        for ob in selected_objects:
            marker_obj = create_timed_location_markers(
                context=context,
                ob=ob,
                interval_seconds=scene.motion_marker_interval_seconds,
                marker_size=scene.motion_marker_size,
                forward_axis=scene.motion_marker_forward_axis,
                yaw_offset_deg=scene.motion_marker_yaw_offset,
                replace_existing=scene.motion_marker_replace_existing,
            )
            if marker_obj is not None:
                count += 1

        self.report({'INFO'}, f"Created timed location markers for {count} object(s).")
        return {'FINISHED'}


classes = (
    GenerateMotionPathOperator,
    RemoveMotionPathOperator,
    ConvertAllObjectsOperator,
    ConvertSelectedObjectsOperator,
    ToggleMotionPathVisibilityOperator,
    CreateTimedLocationMarkersOperator,
)
