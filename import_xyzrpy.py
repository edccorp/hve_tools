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
from bpy.props import FloatProperty
from bpy.types import PropertyGroup


class MotionDataEntry(PropertyGroup):
    time: FloatProperty(name="Time (s)", default=0.0)
    x: FloatProperty(name="X", default=0.0)
    y: FloatProperty(name="Y", default=0.0)
    z: FloatProperty(name="Z", default=0.0)
    roll: FloatProperty(name="Roll", default=0.0)
    pitch: FloatProperty(name="Pitch", default=0.0)
    yaw: FloatProperty(name="Yaw", default=0.0)


def get_target_object(context):
    """Get the motion target object, falling back to legacy target then active object."""
    anim_settings = getattr(context.scene, "anim_settings", None)
    if anim_settings and anim_settings.motion_anim_object:
        return anim_settings.motion_anim_object
    return context.object


def import_motion_data_entries(filepath, target_obj):
    """Import motion rows into the target object's stored entry collection."""
    target_obj.motion_data_entries.clear()

    with open(filepath, 'r', newline='') as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) < 7:
                continue
            try:
                time, x, y, z, roll, pitch, yaw = map(float, row)
            except ValueError:
                continue

            entry = target_obj.motion_data_entries.add()
            entry.time = time
            entry.x = x
            entry.y = y
            entry.z = z
            entry.roll = roll
            entry.pitch = pitch
            entry.yaw = yaw


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
    parent_empty.keyframe_insert(data_path="location", frame=-1)
    parent_empty.keyframe_insert(data_path="rotation_euler", frame=-1)

    obj.parent = parent_empty
    obj.matrix_parent_inverse = parent_empty.matrix_world.inverted()



class ImportCSVAnimationOperator(bpy.types.Operator, ImportHelper):
    """Import CSV and animate an object"""
    bl_idname = "import_anim.csv"
    bl_label = "Import CSV Animation"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".csv"
    filter_glob: bpy.props.StringProperty(default="*.csv", options={'HIDDEN'}, maxlen=255)

    def execute(self, context):
        obj = get_target_object(context)
        frame_rate = context.scene.render.fps  # User-defined FPS (synced with scene)
        unit_system = context.scene.unit_settings.system  # Get unit system (Metric or Imperial)
        scene = context.scene

        extrapolation_mode = context.scene.anim_settings.extrapolation_mode  # 🔹 Correct retrieval


        if obj is None:
            self.report({'ERROR'}, "No object selected")
            return {'CANCELLED'}

        ensure_origin_parent_empty(obj, context)

        filepath = self.filepath
        if not os.path.exists(filepath):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}

        # Update the scene FPS to match user input
        scene.render.fps = frame_rate

        # Clear existing animation data
        obj.animation_data_clear()

        # Persist imported source data on the animated object
        import_motion_data_entries(filepath, obj)

        # Set unit conversion factor
        unit_scale = 1.0
        if unit_system == 'METRIC':
            unit_scale = 1.0  # Assume data is in meters
        elif unit_system == 'IMPERIAL':
            unit_scale = 0.3048  # Convert feet to meters

        # Ensure start frame is set to 0
        scene.frame_start = 0

        frames = []

        for entry in obj.motion_data_entries:
            x = entry.x * unit_scale
            y = entry.y * unit_scale
            z = entry.z * unit_scale
            frame = int(entry.time * frame_rate)
            frames.append(frame)

            obj.location = (x, y, z)
            obj.keyframe_insert(data_path="location", frame=frame)

            obj.rotation_euler = Euler((radians(entry.roll), radians(entry.pitch), radians(entry.yaw)), 'XYZ')
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)

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
    MotionDataEntry,
    ImportCSVAnimationOperator,

]
