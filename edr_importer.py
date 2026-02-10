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
import numpy as np
import csv
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
    """Get the object selected in animation settings, falling back to active object."""
    anim_settings = getattr(context.scene, "anim_settings", None)
    if anim_settings and anim_settings.anim_object:
        return anim_settings.anim_object
    return context.object


def get_vehicle_path_entries(context):
    """Get path entries bound to the selected target object."""
    target_obj = get_target_object(context)
    if not target_obj:
        return None, None
    return target_obj, target_obj.vehicle_path_entries



### Property Group for Time-Speed-Yaw Rate Table ###
class VehiclePathEntry(PropertyGroup):
    time: FloatProperty(name="Time (s)", default=0.0)
    speed: FloatProperty(name="Speed", default=10.0, description="Speed (m/s or mph, based on unit system)")
    yaw_rate: FloatProperty(name="Yaw Rate (deg/s)", default=0.0)


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
                yaw_rate_val = float(row[2])

                valid_rows.append((time_val, speed_val, yaw_rate_val))
            except ValueError:
                # Skip any row that can't be converted to numbers
                continue

    # If no valid data was found
    if not valid_rows:
        print("ERROR: No valid numerical data found in CSV file. Check formatting.")
        return

    # Populate scene properties
    for time_val, speed_val, yaw_rate_val in valid_rows:
        entry = entries.add()
        entry.time = time_val
        entry.speed = speed_val
        entry.yaw_rate = yaw_rate_val
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

    # Extract arrays
    speed_conversion = get_speed_conversion_factor()
    time = np.array([e.time for e in entries], dtype=float)
    speed = np.array([e.speed for e in entries], dtype=float) * speed_conversion          # m/s
    yaw_rate = np.array([e.yaw_rate for e in entries], dtype=float) * DEG_TO_RAD          # rad/s

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

        # Step through frames within this segment
        for step in range(num_steps):
            # 2nd-order yaw integration with constant rdot
            r_prev = r
            psi = psi + r_prev * dt + 0.5 * rdot * dt * dt
            r = r_prev + rdot * dt

            # 2nd-order speed integration with constant a
            v_prev = v
            ds = v_prev * dt + 0.5 * a * dt * dt
            v = v_prev + a * dt

            # Project to world X/Y
            x += ds * float(np.cos(psi))
            y += ds * float(np.sin(psi))

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



### Registering Add-on ###
classes = [
    HVE_OT_ImportCSV,
    HVE_OT_AddPathEntry,
    HVE_OT_RemovePathEntry,
    HVE_OT_RemoveAllPathEntries,
    HVE_OT_AnimateVehicle,

]

