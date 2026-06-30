bl_info = {
    "name": "Vehicle Path Animator",
    "blender": (3, 0, 0),
    "category": "Object",
    "version": (2, 4),
    "author": "EDC",
    "description": "Animates an object using Speed-Time data, with an option to import a CSV file and manually edit entries",
    "location": "View3D > Sidebar > Vehicle Animation",
}

import bpy
import math
import numpy as np
import csv
import mathutils
from bpy.props import FloatProperty, CollectionProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ImportHelper

# Conversion constants
MPH_TO_MPS = 0.44704  # Convert mph to m/s
DEG_TO_RAD = np.pi / 180  # Convert degrees to radians

def get_speed_conversion_factor():
    """Checks Blender's unit system and returns the appropriate speed conversion factor."""
    scene = bpy.context.scene
    unit_system = scene.unit_settings.system

    if unit_system == 'IMPERIAL':
        print("Blender is set to IMPERIAL units. Converting mph to m/s.")
        return MPH_TO_MPS  # Convert mph to m/s
    else:
        print("Blender is set to METRIC units. Using m/s directly.")
        return 1.0  # No conversion needed


def get_target_object(context):
    """Get the EDR target object, falling back to legacy target then active object."""
    anim_settings = getattr(context.scene, "anim_settings", None)
    if anim_settings and anim_settings.edr_anim_object:
        return anim_settings.edr_anim_object
    return context.object


def get_vehicle_path_entries(context):
    """Get path entries bound to the selected target object."""
    target_obj = get_target_object(context)
    if not target_obj:
        return None, None
    return target_obj, target_obj.vehicle_path_entries


def get_object_edr_setting(obj, scene_settings, setting_name, object_preference_name):
    """Read per-object EDR setting, falling back to scene setting."""
    if obj is not None and object_preference_name in obj:
        return obj[object_preference_name]
    return getattr(scene_settings, setting_name)


### Property Group for Time-Speed-Yaw Rate Table ###
class VehiclePathEntry(PropertyGroup):
    time: FloatProperty(name="Time (s)", default=0.0)
    speed: FloatProperty(name="Speed", default=10.0, description="Speed (m/s or mph, based on unit system)")
    yaw_rate: FloatProperty(name="Yaw Rate (deg/s)", default=0.0)
    steering_wheel_angle: FloatProperty(name="Steering Wheel Angle (deg)", default=0.0)


def estimate_yaw_rate_from_steering(speed_mps, steering_wheel_angle_deg, wheelbase_m, steering_gear_ratio):
    """Estimate yaw rate (rad/s) using bicycle model and steering wheel angle."""
    if wheelbase_m <= 0 or steering_gear_ratio <= 0:
        raise ValueError("Wheelbase and steering gear ratio must be greater than zero.")

    road_wheel_angle_rad = np.deg2rad(steering_wheel_angle_deg / steering_gear_ratio)
    return (speed_mps / wheelbase_m) * np.tan(road_wheel_angle_rad)


def estimate_slip_angle_from_yaw_rate(speed_mps, yaw_rate_rps, wheelbase_m, slip_gain=1.0, max_abs_deg=12.0):
    """Estimate an apparent body slip angle beta (rad) from speed and yaw-rate only.

    This uses the no-slip front-wheel angle proxy ``atan(L*r/v)`` and scales it
    by ``slip_gain``. Result is clipped to ``max_abs_deg`` for stability.
    """
    if wheelbase_m <= 0:
        raise ValueError("Wheelbase must be greater than zero.")

    speed_safe = np.maximum(np.asarray(speed_mps, dtype=float), 0.1)
    yaw_rate = np.asarray(yaw_rate_rps, dtype=float)
    beta = float(slip_gain) * np.arctan((wheelbase_m * yaw_rate) / speed_safe)
    beta_max = np.deg2rad(max_abs_deg)
    return np.clip(beta, -beta_max, beta_max)


def integrate_step(x, y, psi, v, r, dt, a, rdot, beta_prev=0.0, beta_next=0.0):
    """Integrate one frame/sub-step from instantaneous samples.

    Inputs ``v`` and ``r`` are interpreted as *instantaneous* values at the
    start of the step. Under the per-segment linear interpolation assumption:
    - speed uses constant acceleration ``a``
    - yaw-rate uses constant ``rdot``

    This means step-end instantaneous values are ``v_next`` and ``r_next`` and
    the integrated heading and distance over ``dt`` are trapezoidal integrals of
    those endpoint rates.
    """
    psi_prev = psi
    v_prev = v
    r_prev = r

    v_next = v_prev + a * dt
    r_next = r_prev + rdot * dt

    # Integrals of linearly varying instantaneous signals on [t, t + dt].
    psi_next = psi_prev + 0.5 * (r_prev + r_next) * dt
    ds = 0.5 * (v_prev + v_next) * dt

    # Midpoint heading gives second-order-consistent translation direction.
    psi_mid = 0.5 * (psi_prev + psi_next)
    beta_mid = 0.5 * (beta_prev + beta_next)
    velocity_heading = psi_mid + beta_mid
    x_next = x + ds * float(np.cos(velocity_heading))
    y_next = y + ds * float(np.sin(velocity_heading))

    return x_next, y_next, psi_next, v_next, r_next


def import_csv_data(filepath, context):
    """Reads CSV and fills the Speed-Time table"""
    scene = context.scene
    target_obj, entries = get_vehicle_path_entries(context)

    if target_obj is None:
        print("ERROR: No target object selected for EDR import.")
        return

    # Clear existing entries
    entries.clear()

    times = []
    mode = scene.anim_settings.edr_input_mode

    # Read CSV file without relying on headers
    with open(filepath, newline='') as csvfile:
        reader = csv.reader(csvfile)  # Read raw rows
        valid_rows = []

        for row in reader:
            if len(row) < 3:  # Ensure there are at least three columns
                continue

            try:
                # Attempt to parse the first three columns as floats
                time_val = float(row[0])
                speed_val = float(row[1])
                third_col_val = float(row[2])

                valid_rows.append((time_val, speed_val, third_col_val))
            except ValueError:
                # Skip any row that can't be converted to numbers
                continue

    # If no valid data was found
    if not valid_rows:
        print("ERROR: No valid numerical data found in CSV file. Check formatting.")
        return

    # Populate scene properties
    for time_val, speed_val, third_col_val in valid_rows:
        entry = entries.add()
        entry.time = time_val
        entry.speed = speed_val
        if mode == 'STEERING_WHEEL_ANGLE':
            entry.steering_wheel_angle = third_col_val
            entry.yaw_rate = 0.0
        else:
            entry.yaw_rate = third_col_val
            entry.steering_wheel_angle = 0.0
        times.append(time_val)

    # Offset time if the first entry is negative
    min_time = min(times)
    if min_time < 0:
        for entry in entries:
            entry.time -= min_time  # Shift all times so the first is at 0

    # Adjust Blender timeline to start at frame 0
    context.scene.frame_start = 0
    print(f"Imported {len(entries)} entries to '{target_obj.name}' from {filepath}, time offset applied: {min_time:.2f}, timeline set to start at frame 0.")

def update_motion_path(obj):
    """Check if an object has a motion path and update it."""
    if obj.animation_data and obj.animation_data.action:
        # Check if the motion path exists
        if obj.motion_path:
            print(f"Updating motion path for {obj.name}")
            bpy.ops.object.paths_update()
    else:
        print(f"No animation data found for {obj.name}")   


def ensure_origin_parent_empty(obj, context):
    """Create an origin empty and parent the object only if it has no existing parent."""
    if obj.parent is not None:
        return

    empty_name = f"{obj.name}_origin"
    parent_empty = bpy.data.objects.get(empty_name)

    if parent_empty is None:
        parent_empty = bpy.data.objects.new(empty_name, None)
        parent_empty.empty_display_type = 'PLAIN_AXES'
        context.collection.objects.link(parent_empty)

    parent_empty.location = (0.0, 0.0, 0.0)
    parent_empty.rotation_euler = (0.0, 0.0, 0.0)
    parent_empty.scale = (1.0, 1.0, 1.0)

    obj.parent = parent_empty
    obj.matrix_parent_inverse = parent_empty.matrix_world.inverted()


def animate_vehicle(self, context):
    """Animates selected object from time/speed/yaw-rate samples (quick estimate).
    - Integrates yaw_rate -> heading
    - Integrates speed -> forward distance -> x/y
    - Uses per-interval linear change (constant accel and constant yaw-accel per segment)
    - Distributes dt exactly across frames in each segment to avoid drift from rounding
    """
    obj, entries = get_vehicle_path_entries(context)
    scene = context.scene

    if not obj:
        self.report({"WARNING"}, "No object selected! Please select an object to animate.")
        return

    if len(entries) < 2:
        self.report({"WARNING"}, "At least two data points are required.")
        return

    ensure_origin_parent_empty(obj, context)

    # Extract arrays
    speed_conversion = get_speed_conversion_factor()
    time = np.array([e.time for e in entries], dtype=float)
    speed = np.array([e.speed for e in entries], dtype=float) * speed_conversion          # m/s

    settings = scene.anim_settings
    mode = settings.edr_input_mode
    wheelbase = float(get_object_edr_setting(obj, settings, "edr_wheelbase", "edr_wheelbase_preference"))
    steering_gear_ratio = float(get_object_edr_setting(
        obj, settings, "edr_steering_gear_ratio", "edr_steering_gear_ratio_preference"
    ))
    use_slip = bool(get_object_edr_setting(obj, settings, "edr_use_slip_estimate", "edr_use_slip_estimate_preference"))
    slip_gain = float(get_object_edr_setting(obj, settings, "edr_slip_gain", "edr_slip_gain_preference"))
    slip_max_deg = float(get_object_edr_setting(obj, settings, "edr_slip_max_deg", "edr_slip_max_deg_preference"))

    steering_wheel_angle = None
    if mode == 'STEERING_WHEEL_ANGLE':
        if wheelbase <= 0 or steering_gear_ratio <= 0:
            self.report({"WARNING"}, "Wheelbase and steering gear ratio must be greater than 0.")
            return
        steering_wheel_angle = np.array([e.steering_wheel_angle for e in entries], dtype=float)
        yaw_rate = estimate_yaw_rate_from_steering(speed, steering_wheel_angle, wheelbase, steering_gear_ratio)
    else:
        yaw_rate = np.array([e.yaw_rate for e in entries], dtype=float) * DEG_TO_RAD      # rad/s

    if use_slip and wheelbase <= 0:
        self.report({"WARNING"}, "Wheelbase must be greater than 0 when slip estimate is enabled.")
        return

    # Basic validation / sorting (optional but safer): ensure strictly nondecreasing time
    # If you prefer to enforce sort, uncomment this block.
    # idx = np.argsort(time)
    # time, speed, yaw_rate = time[idx], speed[idx], yaw_rate[idx]

    # Guard against bad time data
    if np.any(~np.isfinite(time)) or np.any(~np.isfinite(speed)) or np.any(~np.isfinite(yaw_rate)):
        self.report({"WARNING"}, "Non-finite values found in table (NaN/Inf).")
        return

    # Clear previous animation
    obj.animation_data_clear()

    fps = scene.render.fps

    # Initial pose
    x0, y0, z0 = obj.location
    psi0 = obj.rotation_euler.z

    x = float(x0)
    y = float(y0)
    psi = float(psi0)

    # Keyframe initial pose at frame 0
    obj.location = (x, y, 0.0)
    obj.rotation_euler.z = psi
    obj.keyframe_insert(data_path="location", frame=0)
    obj.keyframe_insert(data_path="rotation_euler", frame=0)

    # Helper: map seconds -> frame index (keep consistent)
    def t_to_frame(tsec: float) -> int:
        # frame 0 corresponds to t=0
        return int(round(tsec * fps))

    last_keyed_frame = 0

    # Integrate segment-by-segment
    for i in range(len(time) - 1):
        t0 = float(time[i])
        t1 = float(time[i + 1])
        dt_interval = t1 - t0
        if dt_interval <= 0:
            # Skip non-forward intervals
            continue

        # Frames spanning this interval
        f0 = t_to_frame(t0)
        f1 = t_to_frame(t1)

        # Ensure at least 1 step so something happens even for tiny dt
        num_steps = max(f1 - f0, 1)

        # Distribute dt exactly across steps to match the interval duration
        dt = dt_interval / num_steps

        # Snap to the sample values at the start of the segment
        v = float(speed[i])
        r = float(yaw_rate[i])

        # Per-interval constant rates (linear interpolation of v and r over the segment)
        a = (float(speed[i + 1]) - float(speed[i])) / dt_interval
        rdot = (float(yaw_rate[i + 1]) - float(yaw_rate[i])) / dt_interval

        if use_slip:
            # Use a single beta model for both input modes based on yaw-rate.
            # In steering mode, yaw_rate was already estimated from steering above.
            beta_start = float(estimate_slip_angle_from_yaw_rate(
                speed[i], yaw_rate[i], wheelbase, slip_gain, slip_max_deg
            ))
            beta_end = float(estimate_slip_angle_from_yaw_rate(
                speed[i + 1], yaw_rate[i + 1], wheelbase, slip_gain, slip_max_deg
            ))
        else:
            beta_start = 0.0
            beta_end = 0.0

        # Step through frames within this segment
        for step in range(num_steps):
            frac_prev = step / num_steps
            frac_next = (step + 1) / num_steps
            beta_prev = beta_start + (beta_end - beta_start) * frac_prev
            beta_next = beta_start + (beta_end - beta_start) * frac_next
            x, y, psi, v, r = integrate_step(x, y, psi, v, r, dt, a, rdot, beta_prev, beta_next)

            frame_num = f0 + step + 1  # +1 so motion begins after initial key at frame 0
            obj.location = (x, y, 0.0)
            obj.rotation_euler.z = psi
            obj.keyframe_insert(data_path="location", frame=frame_num)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame_num)

            last_keyed_frame = max(last_keyed_frame, frame_num)

        # Optional: update motion path after each segment (can be slow on large data)
        update_motion_path(obj)

    # Ensure a key at the final sample time (exact end)
    final_frame = t_to_frame(float(time[-1]))
    # If final_frame is behind last keyed because of rounding, keep last_keyed_frame
    final_frame = max(final_frame, last_keyed_frame)

    obj.location = (x, y, 0.0)
    obj.rotation_euler.z = psi
    obj.keyframe_insert(data_path="location", frame=final_frame)
    obj.keyframe_insert(data_path="rotation_euler", frame=final_frame)

    # Extend timeline if needed
    if final_frame > scene.frame_end:
        scene.frame_end = final_frame

    print(f"Animation created from {len(time)} samples, last frame: {final_frame}")

# ---------------------------------------------------------------------------
# Path-following from a speed-time profile
#
# These helpers are intentionally written with plain Python numbers/tuples (no
# bpy / mathutils dependency) so they can be unit tested outside Blender, the
# same way the integrate_step / slip helpers above are tested.
# ---------------------------------------------------------------------------

def _vector_sub(a, b):
    """Component-wise a - b for 3-tuples."""
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def order_vertices_along_edges(edges, vert_count):
    """Return vertex indices ordered as a connected chain following ``edges``.

    ``edges`` is a list of (a, b) index pairs. Works for an open polyline
    (starts from an endpoint with a single edge) or a closed loop (starts at
    index 0). Any vertices not reachable through the edge chain are appended at
    the end so no point is silently dropped.
    """
    adjacency = {}
    for a, b in edges:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    start = None
    for v in range(vert_count):
        if len(adjacency.get(v, [])) == 1:
            start = v
            break
    if start is None:
        start = 0

    order = [start]
    visited = {start}
    prev = None
    current = start
    while True:
        neighbors = [n for n in adjacency.get(current, []) if n != prev and n not in visited]
        if not neighbors:
            neighbors = [n for n in adjacency.get(current, []) if n not in visited]
        if not neighbors:
            break
        nxt = neighbors[0]
        order.append(nxt)
        visited.add(nxt)
        prev, current = current, nxt

    if len(order) < vert_count:
        for v in range(vert_count):
            if v not in visited:
                order.append(v)
    return order


def cumulative_path_lengths(points):
    """Cumulative arc length at each point along the polyline ``points``."""
    cum = [0.0]
    for i in range(1, len(points)):
        dx = points[i][0] - points[i - 1][0]
        dy = points[i][1] - points[i - 1][1]
        dz = points[i][2] - points[i - 1][2]
        cum.append(cum[-1] + math.sqrt(dx * dx + dy * dy + dz * dz))
    return cum


def cumulative_distance_from_speed(time_arr, speed_arr):
    """Trapezoidal cumulative distance travelled at each sample time."""
    cum = [0.0]
    for i in range(1, len(time_arr)):
        dt = time_arr[i] - time_arr[i - 1]
        if dt < 0:
            dt = 0.0
        cum.append(cum[-1] + 0.5 * (speed_arr[i - 1] + speed_arr[i]) * dt)
    return cum


def distance_at_time(time_arr, speed_arr, cum_dist, t):
    """Distance travelled at time ``t`` assuming piecewise-linear speed.

    ``cum_dist`` is the output of :func:`cumulative_distance_from_speed`.
    Times before the first / after the last sample clamp to the endpoints.
    """
    n = len(time_arr)
    if t <= time_arr[0]:
        return 0.0
    if t >= time_arr[-1]:
        return cum_dist[-1]

    # Locate segment i with time_arr[i] <= t < time_arr[i + 1].
    lo, hi = 0, n - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if time_arr[mid] <= t:
            lo = mid + 1
        else:
            hi = mid
    i = lo - 1

    seg_dt = time_arr[i + 1] - time_arr[i]
    tau = t - time_arr[i]
    if seg_dt <= 0:
        return cum_dist[i]
    accel = (speed_arr[i + 1] - speed_arr[i]) / seg_dt
    return cum_dist[i] + speed_arr[i] * tau + 0.5 * accel * tau * tau


def sample_point_on_path(points, cum, dist):
    """Return ``(point, tangent)`` at arc length ``dist`` along the polyline.

    ``point`` is the interpolated (x, y, z) position; ``tangent`` is the
    (unnormalized) direction of the segment containing ``dist``. ``cum`` is the
    output of :func:`cumulative_path_lengths`.
    """
    total = cum[-1]
    n = len(points)
    if dist <= 0.0:
        return points[0], _vector_sub(points[1], points[0])
    if dist >= total:
        return points[-1], _vector_sub(points[-1], points[-2])

    lo, hi = 0, n - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < dist:
            lo = mid + 1
        else:
            hi = mid
    i = lo  # cum[i] >= dist
    seg = i - 1
    seg_len = cum[i] - cum[seg]
    frac = 0.0 if seg_len <= 0 else (dist - cum[seg]) / seg_len
    p0 = points[seg]
    p1 = points[i]
    point = (
        p0[0] + (p1[0] - p0[0]) * frac,
        p0[1] + (p1[1] - p0[1]) * frac,
        p0[2] + (p1[2] - p0[2]) * frac,
    )
    return point, _vector_sub(p1, p0)


def extract_path_points(path_obj, depsgraph):
    """Return ordered world-space (x, y, z) tuples for a curve or mesh path.

    Returns ``None`` if the object has fewer than two usable points.
    """
    eval_obj = path_obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        coords = [v.co.copy() for v in mesh.vertices]
        edges = [tuple(e.vertices) for e in mesh.edges]
    finally:
        eval_obj.to_mesh_clear()

    if len(coords) < 2:
        return None

    if edges:
        order = order_vertices_along_edges(edges, len(coords))
    else:
        order = list(range(len(coords)))

    matrix = path_obj.matrix_world
    return [tuple(matrix @ coords[i]) for i in order]


def animate_path_from_speed(self, context):
    """Animate the EDR object along an existing path using the speed-time table.

    The path geometry (a curve or polyline mesh) defines *where* the object
    travels; the imported Speed vs. Time data defines *how far* along the path
    it has travelled at each frame (distance = integral of speed). Yaw rate /
    steering columns are ignored here - the path itself supplies the heading.
    """
    obj, entries = get_vehicle_path_entries(context)
    scene = context.scene
    settings = scene.anim_settings

    if not obj:
        self.report({"WARNING"}, "No EDR target object selected to animate.")
        return

    path_obj = settings.edr_path_object
    if not path_obj:
        self.report({"WARNING"}, "Select a path object for the object to follow.")
        return
    if path_obj == obj:
        self.report({"WARNING"}, "Path object must be different from the animated object.")
        return
    if len(entries) < 2:
        self.report({"WARNING"}, "At least two speed-time data points are required.")
        return

    # Build sorted, unit-converted (m/s) speed-time samples.
    speed_conversion = get_speed_conversion_factor()
    samples = sorted(
        ((float(e.time), float(e.speed) * speed_conversion) for e in entries),
        key=lambda s: s[0],
    )
    time_arr = [s[0] for s in samples]
    speed_arr = [s[1] for s in samples]

    if not all(math.isfinite(t) for t in time_arr) or not all(math.isfinite(v) for v in speed_arr):
        self.report({"WARNING"}, "Non-finite values found in the speed-time table (NaN/Inf).")
        return

    # Offset so the first sample sits at t = 0.
    t0 = time_arr[0]
    if t0 != 0.0:
        time_arr = [t - t0 for t in time_arr]

    depsgraph = context.evaluated_depsgraph_get()
    points = extract_path_points(path_obj, depsgraph)
    if not points:
        self.report({"WARNING"}, f"Path object '{path_obj.name}' needs at least two connected points.")
        return

    path_cum = cumulative_path_lengths(points)
    total_len = path_cum[-1]
    if total_len <= 0:
        self.report({"WARNING"}, "Selected path has zero length.")
        return

    speed_cum = cumulative_distance_from_speed(time_arr, speed_arr)
    distance_needed = speed_cum[-1]

    # Clear previous animation so we start clean.
    obj.animation_data_clear()

    # Convert world-space path points into the object's local space so the
    # keyframed location is correct even when the object has a parent.
    if obj.parent is not None:
        basis = obj.parent.matrix_world @ obj.matrix_parent_inverse
        basis_inv = basis.inverted()
    else:
        basis_inv = None

    fps = scene.render.fps
    align = bool(settings.edr_path_align_orientation)
    yaw_offset = math.radians(float(settings.edr_path_yaw_offset))

    end_frame = int(round(time_arr[-1] * fps))
    if end_frame < 1:
        end_frame = 1

    prev_yaw = None
    overran = False

    scene.frame_start = 0

    for frame in range(0, end_frame + 1):
        t = frame / fps
        dist = distance_at_time(time_arr, speed_arr, speed_cum, t)
        if dist > total_len:
            dist = total_len
            overran = True
        elif dist < 0.0:
            dist = 0.0

        point, tangent = sample_point_on_path(points, path_cum, dist)

        world_loc = mathutils.Vector(point)
        local_loc = basis_inv @ world_loc if basis_inv is not None else world_loc
        obj.location = local_loc
        obj.keyframe_insert(data_path="location", frame=frame)

        if align:
            if tangent[0] != 0.0 or tangent[1] != 0.0:
                yaw = math.atan2(tangent[1], tangent[0]) + yaw_offset
                # Unwrap relative to the previous yaw to avoid a fast spin when
                # the heading crosses the +/-pi boundary.
                if prev_yaw is not None:
                    while yaw - prev_yaw > math.pi:
                        yaw -= 2.0 * math.pi
                    while yaw - prev_yaw < -math.pi:
                        yaw += 2.0 * math.pi
                prev_yaw = yaw
            elif prev_yaw is not None:
                yaw = prev_yaw
            else:
                yaw = yaw_offset
            obj.rotation_euler.z = yaw
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)

    if end_frame > scene.frame_end:
        scene.frame_end = end_frame

    if overran:
        self.report(
            {'WARNING'},
            f"Speed profile covers {distance_needed:.2f} m but path is only "
            f"{total_len:.2f} m; object stops at the path end.",
        )

    print(
        f"Path-follow animation created on '{obj.name}' along '{path_obj.name}': "
        f"{end_frame + 1} keyframes, path length {total_len:.2f} m, "
        f"distance travelled {min(distance_needed, total_len):.2f} m."
    )


class HVE_OT_ImportCSV(Operator, ImportHelper):
    """Import CSV with Time, Speed, and Yaw Rate"""
    bl_idname = "object.import_csv"
    bl_label = "Import CSV"
    filename_ext = ".csv"

    filter_glob: StringProperty(default="*.csv", options={'HIDDEN'})

    def execute(self, context):
        if get_target_object(context) is None:
            self.report({'WARNING'}, "Select a target object before importing CSV data.")
            return {'CANCELLED'}

        import_csv_data(self.filepath, context)
        return {'FINISHED'}


class HVE_OT_AddPathEntry(Operator):
    """Add a new Time-Speed-Yaw Rate entry"""
    bl_idname = "object.add_path_entry"
    bl_label = "Add Entry"

    def execute(self, context):
        target_obj = get_target_object(context)
        if target_obj is None:
            self.report({'WARNING'}, "Select a target object before adding entries.")
            return {'CANCELLED'}

        target_obj.vehicle_path_entries.add()
        return {"FINISHED"}

### Operator to Remove the Last Row ###
class HVE_OT_RemovePathEntry(Operator):
    """Remove the last Time-Speed-Yaw Rate entry"""
    bl_idname = "object.remove_path_entry"
    bl_label = "Remove Last Entry"

    def execute(self, context):
        target_obj = get_target_object(context)
        if target_obj is None:
            self.report({'WARNING'}, "Select a target object before removing entries.")
            return {'CANCELLED'}

        if len(target_obj.vehicle_path_entries) > 0:
            target_obj.vehicle_path_entries.remove(len(target_obj.vehicle_path_entries) - 1)
        return {"FINISHED"}
        
### Operator to Remove the Last Row ###
class HVE_OT_RemoveAllPathEntries(Operator):
    """Remove the last Time-Speed-Yaw Rate entry"""
    bl_idname = "object.remove_all_entries"
    bl_label = "Remove All Entries"

    def execute(self, context):
        target_obj = get_target_object(context)
        if target_obj is None:
            self.report({'WARNING'}, "Select a target object before removing entries.")
            return {'CANCELLED'}

        if len(target_obj.vehicle_path_entries) > 0:
            # Clear existing entries
            target_obj.vehicle_path_entries.clear()
        return {"FINISHED"}
        

### Operator to Animate Object ###
class HVE_OT_AnimateVehicle(Operator):
    """Animate Object from Speed-Time Table"""
    bl_idname = "object.animate_vehicle"
    bl_label = "Animate Object"

    def execute(self, context):
        animate_vehicle(self, context)
        return {"FINISHED"}


### Operator to Animate Object Along an Existing Path ###
class HVE_OT_AnimatePathFromSpeed(Operator):
    """Animate the EDR object along a selected path, using the Speed-Time table to set how far along the path it travels"""
    bl_idname = "object.animate_path_from_speed"
    bl_label = "Animate Along Path"

    def execute(self, context):
        animate_path_from_speed(self, context)
        return {"FINISHED"}



### Registering Add-on ###
classes = [
    HVE_OT_ImportCSV,
    HVE_OT_AddPathEntry,
    HVE_OT_RemovePathEntry,
    HVE_OT_RemoveAllPathEntries,
    HVE_OT_AnimateVehicle,
    HVE_OT_AnimatePathFromSpeed,

]
