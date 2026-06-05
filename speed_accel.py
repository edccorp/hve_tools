"""Speed and acceleration baking tools for animated Blender objects."""

import math

import bpy
from mathutils import Vector


PROP_AVG_V = "avg_speed_mph"
PROP_AVG_U = "avg_forward_speed_mph"
PROP_FWD_A = "forward_accel_g"
PROP_LAT_A = "lateral_accel_g"
PROP_VERT_A = "vertical_accel_g"
HELPER_NAME = "SpeedData"
FEET_PER_SECOND_TO_MPH = 3600.0 / 5280.0
METERS_PER_SECOND_TO_MPH = 2.2369362921
METERS_PER_SECOND_SQUARED_TO_G = 1.0 / 9.80665
FEET_PER_SECOND_SQUARED_TO_G = 1.0 / 32.174
OUTPUT_PROPS = [
    PROP_AVG_V,
    PROP_AVG_U,
    PROP_FWD_A,
    PROP_LAT_A,
    PROP_VERT_A,
]

FORWARD_AXIS_VECTORS = {
    'LOCAL_X': Vector((1.0, 0.0, 0.0)),
    'LOCAL_NEG_X': Vector((-1.0, 0.0, 0.0)),
    'LOCAL_Y': Vector((0.0, 1.0, 0.0)),
    'LOCAL_NEG_Y': Vector((0.0, -1.0, 0.0)),
    'LOCAL_Z': Vector((0.0, 0.0, 1.0)),
    'LOCAL_NEG_Z': Vector((0.0, 0.0, -1.0)),
}


class SpeedAccelerationBakeOperator(bpy.types.Operator):
    """Calculate speed and acceleration from an object's animation and bake results to a helper empty."""

    bl_idname = "object.calculate_speed_acceleration"
    bl_label = "Calculate Speed + Acceleration"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        source_obj = scene.speed_accel_target_object or context.active_object

        if source_obj is None:
            self.report({'ERROR'}, "Select a source object for speed/acceleration calculation")
            return {'CANCELLED'}

        try:
            result = bake_speed_acceleration(
                context=context,
                source_obj=source_obj,
                forward_axis=scene.speed_accel_forward_axis,
                forward_yaw_offset_deg=scene.speed_accel_forward_yaw_offset,
                window_frames=scene.speed_accel_window_frames,
                unit_mode=scene.speed_accel_unit_mode,
                use_xy_only=scene.speed_accel_use_xy_only,
                remove_existing_output_curves=scene.speed_accel_remove_old_curves,
                parent_helper_to_source=scene.speed_accel_parent_helper,
            )
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"Baked speed/accel for {source_obj.name} to {result['helper_name']} "
            f"using {result['window_frames']} frame window",
        )
        return {'FINISHED'}


def iter_action_fcurves_for_object(obj):
    ad = obj.animation_data
    if not ad or not ad.action:
        return

    action = ad.action

    if hasattr(action, "fcurves"):
        for fc in action.fcurves:
            yield action.fcurves, fc
        return

    if hasattr(action, "layers"):
        action_slot = getattr(ad, "action_slot", None)

        for layer in action.layers:
            for strip in getattr(layer, "strips", []):
                channelbags = getattr(strip, "channelbags", None)
                if channelbags is None:
                    continue

                for channelbag in channelbags:
                    bag_slot = getattr(channelbag, "slot", None)

                    if action_slot is not None and bag_slot is not None:
                        if bag_slot != action_slot:
                            continue

                    for fc in getattr(channelbag, "fcurves", []):
                        yield channelbag.fcurves, fc


def ensure_action_exists(obj):
    if obj.animation_data is None:
        obj.animation_data_create()

    if obj.animation_data.action is None:
        obj.animation_data.action = bpy.data.actions.new(name=f"{obj.name}_Action")


def remove_old_output_curves(obj, prop_names):
    ad = obj.animation_data
    if not ad or not ad.action:
        return

    target_paths = {f'["{p}"]' for p in prop_names}

    to_remove = []
    for container, fc in iter_action_fcurves_for_object(obj) or []:
        if fc.data_path in target_paths:
            to_remove.append((container, fc))

    for container, fc in to_remove:
        try:
            container.remove(fc)
        except Exception:
            pass


def force_output_curves_linear(obj, prop_names):
    target_paths = {f'["{p}"]' for p in prop_names}

    for container, fc in iter_action_fcurves_for_object(obj) or []:
        if fc.data_path in target_paths:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'
            fc.update()


def xy_only(vec):
    return Vector((vec.x, vec.y, 0.0))


def get_world_position(eval_obj, use_xy_only):
    pos = eval_obj.matrix_world.translation.copy()
    if use_xy_only:
        pos = xy_only(pos)
    return pos


def get_forward_axis_vector(axis_name):
    return FORWARD_AXIS_VECTORS.get(axis_name, FORWARD_AXIS_VECTORS['LOCAL_X'])


def get_forward_direction(eval_obj, forward_axis, forward_yaw_offset_deg):
    rot = eval_obj.matrix_world.to_3x3()
    fwd = rot @ get_forward_axis_vector(forward_axis)
    fwd.z = 0.0

    if fwd.length < 1e-8:
        fwd = Vector((0.0, 1.0, 0.0))
    else:
        fwd.normalize()

    ang = math.radians(forward_yaw_offset_deg)
    c = math.cos(ang)
    s = math.sin(ang)

    fwd = Vector((
        c * fwd.x - s * fwd.y,
        s * fwd.x + c * fwd.y,
        0.0,
    ))

    if fwd.length < 1e-8:
        return Vector((0.0, 1.0, 0.0))

    fwd.normalize()
    return fwd


def get_lateral_direction(fwd):
    right = Vector((fwd.y, -fwd.x, 0.0))

    if right.length < 1e-8:
        return Vector((1.0, 0.0, 0.0))

    right.normalize()
    return right


def get_or_create_helper(scene, source_obj):
    name = f"{HELPER_NAME}_{source_obj.name}"
    helper = bpy.data.objects.get(name)

    if helper is None:
        helper = bpy.data.objects.new(name, None)
        helper.empty_display_type = 'PLAIN_AXES'
        helper.empty_display_size = 1.0
        scene.collection.objects.link(helper)

    return helper


def get_window_for_frame(f, frame_start, frame_end, window_frames):
    """Return f0 and f1 for a centered constant-size frame window."""

    window_frames = max(1, int(window_frames))
    half = window_frames // 2

    f0 = f - half
    f1 = f0 + window_frames

    if f0 < frame_start:
        shift = frame_start - f0
        f0 += shift
        f1 += shift

    if f1 > frame_end:
        shift = f1 - frame_end
        f0 -= shift
        f1 -= shift

    f0 = max(frame_start, f0)
    f1 = min(frame_end, f1)

    return f0, f1


def get_unit_conversions(scene, unit_mode):
    unit_settings = scene.unit_settings
    resolved_mode = unit_mode

    if unit_mode == 'AUTO':
        scale_length = float(getattr(unit_settings, "scale_length", 1.0) or 1.0)
        return (
            scale_length * METERS_PER_SECOND_TO_MPH,
            scale_length * METERS_PER_SECOND_SQUARED_TO_G,
            'SCENE',
        )

    if resolved_mode == 'FEET':
        return FEET_PER_SECOND_TO_MPH, FEET_PER_SECOND_SQUARED_TO_G, resolved_mode
    if resolved_mode == 'METERS':
        return METERS_PER_SECOND_TO_MPH, METERS_PER_SECOND_SQUARED_TO_G, resolved_mode

    raise RuntimeError('Unit mode must be Auto, Feet, or Meters.')


def bake_speed_acceleration(
    context,
    source_obj,
    forward_axis,
    forward_yaw_offset_deg,
    window_frames,
    unit_mode,
    use_xy_only,
    remove_existing_output_curves,
    parent_helper_to_source,
):
    scene = context.scene
    frame_start = scene.frame_start
    frame_end = scene.frame_end
    fps = scene.render.fps / scene.render.fps_base

    if fps <= 0.0:
        raise RuntimeError("Scene FPS must be greater than zero.")

    window_frames = max(1, int(window_frames))
    if frame_end - frame_start < window_frames:
        raise RuntimeError("Scene frame range is shorter than the average window.")

    speed_to_mph, accel_to_g, resolved_unit_mode = get_unit_conversions(scene, unit_mode)
    depsgraph = context.evaluated_depsgraph_get()

    helper_obj = get_or_create_helper(scene, source_obj)
    if parent_helper_to_source:
        helper_obj.parent = source_obj
    else:
        helper_obj.parent = None
    helper_obj.matrix_world.translation = source_obj.matrix_world.translation.copy()

    cur_frame = scene.frame_current
    positions = {}
    forwards = {}
    laterals = {}

    try:
        for f in range(frame_start, frame_end + 1):
            scene.frame_set(f)
            eval_obj = source_obj.evaluated_get(depsgraph)

            positions[f] = get_world_position(eval_obj, use_xy_only)

            fwd = get_forward_direction(eval_obj, forward_axis, forward_yaw_offset_deg)
            lat = get_lateral_direction(fwd)

            forwards[f] = fwd
            laterals[f] = lat

        velocity_vectors = {}
        for f in range(frame_start, frame_end + 1):
            f0, f1 = get_window_for_frame(f, frame_start, frame_end, window_frames)

            dt = (f1 - f0) / fps
            if dt <= 0.0:
                continue

            dp = positions[f1] - positions[f0]
            velocity_vectors[f] = dp / dt

        frames_out = []
        speeds = []
        forward_speeds = []
        forward_accels = []
        lateral_accels = []
        vertical_accels = []

        for f in range(frame_start, frame_end + 1):
            if f not in velocity_vectors:
                continue

            v = velocity_vectors[f]
            fwd = forwards[f]
            lat = laterals[f]

            speed = float(v.length * speed_to_mph)
            fwd_speed = float(v.dot(fwd) * speed_to_mph)

            if (f - 1 in velocity_vectors) and (f + 1 in velocity_vectors):
                v0 = velocity_vectors[f - 1]
                v1 = velocity_vectors[f + 1]
                dt_a = 2.0 / fps
            elif f + 1 in velocity_vectors:
                v0 = velocity_vectors[f]
                v1 = velocity_vectors[f + 1]
                dt_a = 1.0 / fps
            elif f - 1 in velocity_vectors:
                v0 = velocity_vectors[f - 1]
                v1 = velocity_vectors[f]
                dt_a = 1.0 / fps
            else:
                v0 = velocity_vectors[f]
                v1 = velocity_vectors[f]
                dt_a = 1.0 / fps

            a_vec = (v1 - v0) / dt_a

            frames_out.append(f)
            speeds.append(speed)
            forward_speeds.append(fwd_speed)
            forward_accels.append(float(a_vec.dot(fwd) * accel_to_g))
            lateral_accels.append(float(a_vec.dot(lat) * accel_to_g))
            vertical_accels.append(float(a_vec.z * accel_to_g))

        ensure_action_exists(helper_obj)

        if remove_existing_output_curves:
            remove_old_output_curves(helper_obj, OUTPUT_PROPS)

        for f, v, u, af, al, av in zip(
            frames_out,
            speeds,
            forward_speeds,
            forward_accels,
            lateral_accels,
            vertical_accels,
        ):
            scene.frame_set(f)

            helper_obj[PROP_AVG_V] = v
            helper_obj.keyframe_insert(data_path=f'["{PROP_AVG_V}"]', frame=f)

            helper_obj[PROP_AVG_U] = u
            helper_obj.keyframe_insert(data_path=f'["{PROP_AVG_U}"]', frame=f)

            helper_obj[PROP_FWD_A] = af
            helper_obj.keyframe_insert(data_path=f'["{PROP_FWD_A}"]', frame=f)

            helper_obj[PROP_LAT_A] = al
            helper_obj.keyframe_insert(data_path=f'["{PROP_LAT_A}"]', frame=f)

            helper_obj[PROP_VERT_A] = av
            helper_obj.keyframe_insert(data_path=f'["{PROP_VERT_A}"]', frame=f)

        force_output_curves_linear(helper_obj, OUTPUT_PROPS)
    finally:
        scene.frame_set(cur_frame)

    bpy.context.view_layer.update()

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
            for region in area.regions:
                region.tag_redraw()

    bpy.ops.object.select_all(action='DESELECT')
    source_obj.select_set(True)
    bpy.context.view_layer.objects.active = source_obj

    print(f"Window: {window_frames} frames ({window_frames / fps:.3f} sec)")
    print(f"Source object: {source_obj.name}")
    print(f"Helper object: {helper_obj.name}")
    print(f"Unit mode: {resolved_unit_mode}")
    print("Baked:")
    for prop_name in OUTPUT_PROPS:
        print(f"  {prop_name}")
    print("Done.")

    return {
        'helper_name': helper_obj.name,
        'window_frames': window_frames,
        'unit_mode': resolved_unit_mode,
        'frame_count': len(frames_out),
    }


classes = (
    SpeedAccelerationBakeOperator,
)
