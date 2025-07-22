bl_info = {
    "name": "Motion Data Importer",
    "blender": (2, 80, 0),
    "category": "Animation",
    "description": "Import CSV data and animate an object",
    "author": "YEDC",
    "version": (2, 0),
    "location": "Sidebar > Animation > CSV Importer",
}

import bpy
import csv
import os
from mathutils import Euler
from math import radians
from bpy_extras.io_utils import ImportHelper



class ImportCSVAnimationOperator(bpy.types.Operator, ImportHelper):
    """Import CSV and animate an object"""
    bl_idname = "import_anim.csv"
    bl_label = "Import CSV Animation"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".csv"
    filter_glob: bpy.props.StringProperty(default="*.csv", options={'HIDDEN'}, maxlen=255)

    def execute(self, context):
        obj = context.scene.anim_settings.anim_object
        frame_rate = context.scene.render.fps  # User-defined FPS (synced with scene)
        unit_system = context.scene.unit_settings.system  # Get unit system (Metric or Imperial)
        scene = context.scene

        extrapolation_mode = context.scene.anim_settings.extrapolation_mode  # 🔹 Correct retrieval


        if obj is None:
            self.report({'ERROR'}, "No object selected")
            return {'CANCELLED'}

        filepath = self.filepath
        if not os.path.exists(filepath):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}

        # Update the scene FPS to match user input
        scene.render.fps = frame_rate

        # Clear existing animation data
        obj.animation_data_clear()

        # Set unit conversion factor
        unit_scale = 1.0
        if unit_system == 'METRIC':
            unit_scale = 1.0  # Assume data is in meters
        elif unit_system == 'IMPERIAL':
            unit_scale = 0.3048  # Convert feet to meters

        # Ensure start frame is set to 0
        scene.frame_start = 0

        frames = []

        # Read CSV data
        with open(filepath, 'r', newline='') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) < 7:
                    continue
                try:
                    time, x, y, z, roll, pitch, yaw = map(float, row)
                    x *= unit_scale
                    y *= unit_scale
                    z *= unit_scale
                    frame = int(time * frame_rate)
                    frames.append(frame)

                    obj.location = (x, y, z)
                    obj.keyframe_insert(data_path="location", frame=frame)

                    obj.rotation_euler = Euler((radians(roll), radians(pitch), radians(yaw)), 'XYZ')
                    obj.keyframe_insert(data_path="rotation_euler", frame=frame)

                except ValueError:
                    continue

        if frames:
            # 🔹 Apply the selected extrapolation mode
            if extrapolation_mode == 'LINEAR':
                self.set_extrapolation(obj, 'LINEAR')
            elif extrapolation_mode == 'CONSTANT':
                self.set_extrapolation(obj, 'CONSTANT')

            last_frame = max(frames)
            if last_frame > scene.frame_end:
                scene.frame_end = last_frame

        self.report({'INFO'}, "CSV Animation Imported Successfully")
        return {'FINISHED'}
   
    def set_extrapolation(self, obj, mode):
        """Sets the extrapolation mode for all animation curves"""
        if obj.animation_data and obj.animation_data.action:
            for fcurve in obj.animation_data.action.fcurves:
                fcurve.extrapolation = mode  # 🔹 Apply chosen extrapolation mode


### Registering Add-on ###
classes = [
    ImportCSVAnimationOperator,

]


