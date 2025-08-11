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



### Property Group for Time-Speed-Yaw Rate Table ###
class VehiclePathEntry(PropertyGroup):
    time: FloatProperty(name="Time (s)", default=0.0)
    speed: FloatProperty(name="Speed", default=10.0, description="Speed (m/s or mph, based on unit system)")
    yaw_rate: FloatProperty(name="Yaw Rate (deg/s)", default=0.0)


def import_csv_data(filepath, context):
    """Reads CSV and fills the Speed-Time table"""
    scene = context.scene

    # Clear existing entries
    scene.vehicle_path_entries.clear()

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
        entry = scene.vehicle_path_entries.add()
        entry.time = time_val
        entry.speed = speed_val
        entry.yaw_rate = yaw_rate_val
        times.append(time_val)

    # Offset time if the first entry is negative
    min_time = min(times)
    if min_time < 0:
        for entry in scene.vehicle_path_entries:
            entry.time -= min_time  # Shift all times so the first is at 0

    # Adjust Blender timeline to start at frame 0
    context.scene.frame_start = 0
    print(f"Imported {len(scene.vehicle_path_entries)} entries from {filepath}, time offset applied: {min_time:.2f}, timeline set to start at frame 0.")

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
    """Processes UI Table Data and Animates the Selected Object Using Acceleration"""
    entries = context.scene.vehicle_path_entries
    obj = context.object  # Get selected object
    scene = context.scene
    if not obj:
        self.report({"WARNING"}, "No object selected! Please select an object to animate.")
        return

    if len(entries) < 2:
        self.report({"WARNING"}, "At least two data points are required.")
        return

    speed_conversion = get_speed_conversion_factor()

    # Clear previous animation keyframes
    obj.animation_data_clear()


    # Extract values from UI table
    time = np.array([entry.time for entry in entries])
    speed = np.array([entry.speed * speed_conversion for entry in entries])
    yaw_rate = np.array([entry.yaw_rate * DEG_TO_RAD for entry in entries])   # Convert degrees to radians

    # Compute time steps (dt) and acceleration
    dt = np.diff(time, prepend=time[0])
    acceleration = np.zeros_like(speed)
    yaw_rate_dot = np.zeros_like(yaw_rate)
    
    for i in range(1, len(speed)):
        acceleration[i-1] = (speed[i] - speed[i - 1]) / dt[i] if dt[i] > 0 else 0

    for i in range(1, len(yaw_rate)):
        yaw_rate_dot[i-1] = (yaw_rate[i] - yaw_rate[i-1]) / dt[i] if dt[i] > 0 else 0
    
    # Get the object's initial position and rotation
    x0, y0, z0 = obj.location  # Initial position
    heading0 = obj.rotation_euler.z  # Initial Z rotation (yaw angle)
    
    # Initialize position tracking
    x = [x0]
    y = [y0]
    heading = [heading0]
    current_speed = speed[0]
    current_yaw_rate = yaw_rate[0]  # Initialize yaw rate properly

    fps = context.scene.render.fps
    
    # 🔹 **Set Initial Keyframe (First Frame)**
    obj.location = (x0, y0, 0)  # Set object initial position
    obj.rotation_euler.z = heading0  # Set object initial rotation
    obj.keyframe_insert(data_path="location", frame=0)
    obj.keyframe_insert(data_path="rotation_euler", frame=0)
    
    # Apply animation keyframes for every frame
    for i in range(len(time) - 1):
        start_frame = int(time[i] * fps)+1
        end_frame = int(time[i + 1] * fps) + 1
        num_frames = end_frame - start_frame

        for frame in range(num_frames):
            dt_frame = 1.0 / fps  # Time step per frame
            current_speed += acceleration[i] * dt_frame  # Update speed
            current_yaw_rate += yaw_rate_dot[i] *dt_frame #Update yaw rate
            heading.append(heading[-1] + current_yaw_rate * dt_frame)  # Update heading
            
            x.append(x[-1] + current_speed * np.cos(heading[-1]) * dt_frame + 0.5 * acceleration[i] * dt_frame**2)
            y.append(y[-1] + current_speed * np.sin(heading[-1]) * dt_frame + 0.5 * acceleration[i] * dt_frame**2)

            obj.location = (x[-1], y[-1], 0)  # Set object position
            obj.keyframe_insert(data_path="location", frame=start_frame + frame)

            obj.rotation_euler.z = heading[-1]  # Rotate object
            obj.keyframe_insert(data_path="rotation_euler", frame=start_frame + frame)
        # Adjust end frame if last animated frame is beyond the current scene frame_end
        update_motion_path(obj)
        if end_frame > scene.frame_end:
            scene.frame_end = end_frame
    print(f"Animation created with {len(time)} keyframes!")

class HVE_OT_ImportCSV(Operator, ImportHelper):
    """Import CSV with Time, Speed, and Yaw Rate"""
    bl_idname = "object.import_csv"
    bl_label = "Import CSV"
    filename_ext = ".csv"

    filter_glob: StringProperty(default="*.csv", options={'HIDDEN'})

    def execute(self, context):
        import_csv_data(self.filepath, context)
        return {'FINISHED'}


class HVE_OT_AddPathEntry(Operator):
    """Add a new Time-Speed-Yaw Rate entry"""
    bl_idname = "object.add_path_entry"
    bl_label = "Add Entry"

    def execute(self, context):
        context.scene.vehicle_path_entries.add()
        return {"FINISHED"}

### Operator to Remove the Last Row ###
class HVE_OT_RemovePathEntry(Operator):
    """Remove the last Time-Speed-Yaw Rate entry"""
    bl_idname = "object.remove_path_entry"
    bl_label = "Remove Last Entry"

    def execute(self, context):
        if len(context.scene.vehicle_path_entries) > 0:
            context.scene.vehicle_path_entries.remove(len(context.scene.vehicle_path_entries) - 1)
        return {"FINISHED"}
        
### Operator to Remove the Last Row ###
class HVE_OT_RemoveAllPathEntries(Operator):
    """Remove the last Time-Speed-Yaw Rate entry"""
    bl_idname = "object.remove_all_entries"
    bl_label = "Remove All Entries"

    def execute(self, context):
        if len(context.scene.vehicle_path_entries) > 0:
            # Clear existing entries
            context.scene.vehicle_path_entries.clear()
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


