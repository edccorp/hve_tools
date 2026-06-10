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

OVERLAY_MARKERS_LABEL = "Overlay Markers"
MARKER_MATERIAL_NAME = "HVE_Overlay_Markers"
TEXT_MATERIAL_NAME = "BLACK"
MARKER_MATERIAL_COLOR = (1.0, 0.35, 0.0, 1.0)
TEXT_MATERIAL_COLOR = (0.0, 0.0, 0.0, 1.0)


def set_principled_material_color(material, color):
    """Set a material's viewport and Principled BSDF colors when available."""
    material.diffuse_color = color

    if not material.use_nodes:
        material.use_nodes = True

    node_tree = getattr(material, "node_tree", None)
    if node_tree is None:
        return

    principled = node_tree.nodes.get("Principled BSDF")
    if principled is None:
        return

    base_color = principled.inputs.get("Base Color")
    if base_color is not None:
        base_color.default_value = color

    alpha = principled.inputs.get("Alpha")
    if alpha is not None:
        alpha.default_value = color[3]


def get_or_create_overlay_material(name, color):
    """Return an HVE overlay material with the requested display color."""
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name=name)

    set_principled_material_color(material, color)
    return material


def assign_hve_overlay_environment_props(obj):
    """Tag generated marker objects as HVE environment overlay surfaces."""
    hve_type = getattr(getattr(obj, "hve_type", None), "set_type", None)
    if hve_type is not None and hasattr(hve_type, "type"):
        hve_type.type = "ENVIRONMENT"

    env_props = getattr(getattr(obj, "hve_env_props", None), "set_env_props", None)
    if env_props is not None:
        if hasattr(env_props, "poSurfaceType"):
            env_props.poSurfaceType = "EdTypeOther"
        if hasattr(env_props, "polabel"):
            env_props.polabel = OVERLAY_MARKERS_LABEL


def assign_single_material(obj, material):
    """Replace an object's material list with a single material."""
    materials = getattr(getattr(obj, "data", None), "materials", None)
    if materials is None:
        return

    materials.clear()
    materials.append(material)



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


def iter_marker_frame_times(frame_start, frame_end, fps, interval_seconds, zero_frame=None):
    """Yield sample frame values at an interval, centered on a zero frame."""
    interval_seconds = max(float(interval_seconds), 1.0 / fps)
    frame_step = interval_seconds * fps
    zero_frame = float(frame_start if zero_frame is None else zero_frame)

    first_step = math.ceil((float(frame_start) - zero_frame) / frame_step - 1e-9)
    last_step = math.floor((float(frame_end) - zero_frame) / frame_step + 1e-9)

    for step_index in range(first_step, last_step + 1):
        yield zero_frame + (step_index * frame_step)


def split_frame_value(frame_value):
    """Split a floating frame value into Blender frame and subframe arguments."""
    whole_frame = math.floor(frame_value)
    subframe = frame_value - whole_frame
    return whole_frame, subframe


def get_marker_relative_seconds(frame_value, zero_frame, fps):
    """Return marker time in seconds relative to the zero frame."""
    return (float(frame_value) - float(zero_frame)) / float(fps)


def format_marker_relative_time(relative_seconds):
    """Format marker label text as signed seconds relative to zero."""
    if math.isclose(relative_seconds, 0.0, abs_tol=1e-9):
        relative_seconds = 0.0

    return f"{relative_seconds:+.2f}s"


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

    old_data = old_obj.data
    bpy.data.objects.remove(old_obj, do_unlink=True)

    if old_data and old_data.users == 0:
        if old_data.__class__.__name__ == "Curve":
            bpy.data.curves.remove(old_data)
        else:
            bpy.data.meshes.remove(old_data)


def remove_existing_marker_labels(source_object_name):
    """Remove previously generated time label text objects for a source object."""
    for old_obj in list(bpy.data.objects):
        if old_obj.get("source_object") != source_object_name:
            continue
        if old_obj.get("marker_type") != "time_label":
            continue
        remove_existing_marker_object(old_obj.name)


def create_marker_time_label(collection, source_object_name, location, label_text, label_size, marker_index):
    """Create a text object labeling a marker's time relative to the zero frame."""
    curve = bpy.data.curves.new(
        name=f"{source_object_name}_time_label_{marker_index:03d}",
        type='FONT',
    )
    curve.body = label_text
    curve.align_x = 'CENTER'
    curve.align_y = 'CENTER'
    curve.size = max(float(label_size), 0.001)

    text_obj = bpy.data.objects.new(curve.name, curve)
    text_obj.location = location
    text_obj["source_object"] = source_object_name
    text_obj["marker_type"] = "time_label"
    text_obj["relative_time"] = label_text
    assign_hve_overlay_environment_props(text_obj)
    assign_single_material(
        text_obj,
        get_or_create_overlay_material(TEXT_MATERIAL_NAME, TEXT_MATERIAL_COLOR),
    )
    collection.objects.link(text_obj)
    return text_obj


def create_timed_location_markers(
    context,
    ob,
    interval_seconds,
    marker_size,
    forward_axis,
    yaw_offset_deg,
    zero_frame,
    create_time_labels=True,
    label_size=0.5,
    replace_existing=True,
):
    """Create triangular markers at an object's location, timed around a zero frame."""
    scene = context.scene
    depsgraph = context.evaluated_depsgraph_get()
    fps = get_scene_fps(scene)
    marker_name = f"{ob.name}_time_markers"

    if replace_existing:
        remove_existing_marker_object(marker_name)
        remove_existing_marker_labels(ob.name)

    original_frame = scene.frame_current
    original_subframe = getattr(scene, "frame_subframe", 0.0)
    verts = []
    faces = []
    label_specs = []
    zero_frame = float(zero_frame)

    try:
        for frame_value in iter_marker_frame_times(
            scene.frame_start,
            scene.frame_end,
            fps,
            interval_seconds,
            zero_frame=zero_frame,
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

            if create_time_labels:
                relative_seconds = get_marker_relative_seconds(frame_value, zero_frame, fps)
                label_text = format_marker_relative_time(relative_seconds)
                label_location = location + Vector((0.0, 0.0, marker_size * 0.75))
                label_specs.append((label_location.copy(), label_text))
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
    marker_obj["zero_frame"] = zero_frame
    marker_obj["forward_axis"] = forward_axis
    marker_obj["yaw_offset_deg"] = yaw_offset_deg
    assign_hve_overlay_environment_props(marker_obj)
    assign_single_material(
        marker_obj,
        get_or_create_overlay_material(MARKER_MATERIAL_NAME, MARKER_MATERIAL_COLOR),
    )

    motion_path_collection = get_or_create_motion_path_collection()
    motion_path_collection.objects.link(marker_obj)

    for marker_index, (label_location, label_text) in enumerate(label_specs):
        create_marker_time_label(
            motion_path_collection,
            ob.name,
            label_location,
            label_text,
            label_size,
            marker_index,
        )

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
                zero_frame=scene.motion_marker_zero_frame,
                create_time_labels=scene.motion_marker_create_time_labels,
                label_size=scene.motion_marker_label_size,
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
