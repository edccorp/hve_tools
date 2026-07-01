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

# Reuse the bpy-free CSV helpers from the EDR importer so the column-mapping
# behaviour (header detection, normalisation, file reading) stays consistent.
from .edr_importer import normalize_header, detect_header_row, read_csv_headers


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


# ---------------------------------------------------------------------------
# Flexible CSV column mapping
#
# Lets a motion CSV (with or without a header row) provide Time, X, Y, Z, Roll,
# Pitch and Yaw columns in any order. Columns are auto-matched by header name
# when possible, and the user can override the mapping in the panel. The helpers
# below are plain-Python and unit tested.
# ---------------------------------------------------------------------------

MOTION_COLUMN_FIELDS = ("time", "x", "y", "z", "roll", "pitch", "yaw")

MOTION_COLUMN_KEYWORDS = {
    "time": ["time", "timestamp", "elapsed", "seconds", "second", "sec", "t"],
    "x": ["x position", "position x", "pos x", "easting", "x"],
    "y": ["y position", "position y", "pos y", "northing", "y"],
    "z": ["z position", "position z", "pos z", "elevation", "height", "z"],
    "roll": ["roll", "phi", "r"],
    "pitch": ["pitch", "theta", "p"],
    "yaw": ["yaw", "heading", "psi", "y"],
}


def auto_map_motion_columns(headers):
    """Best-effort map of motion fields to column indices using header names.

    Returns a dict ``{field: index}`` where ``index`` is -1 when no column
    matched. Positional x/y/z fields are resolved before the roll/pitch/yaw
    fields so that, e.g., in an ``X, Y, Z, R, P, Y`` file the positional "Y"
    claims its column first and only the leftover "Y" falls through to yaw
    (roll/pitch/yaw also accept the short "r"/"p"/"y" abbreviations).
    """
    normalized = [normalize_header(h) for h in headers]
    mapping = {field: -1 for field in MOTION_COLUMN_FIELDS}
    used = set()

    def find(keywords):
        for kw in keywords:
            for i, header in enumerate(normalized):
                if i in used or not header:
                    continue
                tokens = header.split()
                # Short keywords must match a whole token (avoids "x" hitting
                # "max"); longer ones may match as a substring.
                if kw in tokens or (len(kw) > 2 and kw in header):
                    return i
        return -1

    for field in ("time", "x", "y", "z", "roll", "pitch", "yaw"):
        idx = find(MOTION_COLUMN_KEYWORDS[field])
        mapping[field] = idx
        if idx >= 0:
            used.add(idx)
    return mapping


def default_motion_positional_mapping(num_columns):
    """Fallback mapping for header-less CSVs: Time, X, Y, Z, Roll, Pitch, Yaw."""
    order = ("time", "x", "y", "z", "roll", "pitch", "yaw")
    mapping = {field: -1 for field in MOTION_COLUMN_FIELDS}
    for i, field in enumerate(order):
        if num_columns > i:
            mapping[field] = i
    return mapping


def import_mapped_motion_data(filepath, mapping, has_header, target_obj):
    """Fill ``target_obj.motion_data_entries`` from ``filepath`` using ``mapping``.

    ``mapping`` maps each motion field to a 0-based column index (or -1 to skip).
    Time, X, Y and Z are required; Roll, Pitch and Yaw default to 0 when absent.
    Returns ``(count, error_message)``; ``error_message`` is None on success.
    """
    time_idx = mapping.get("time", -1)
    x_idx = mapping.get("x", -1)
    y_idx = mapping.get("y", -1)
    z_idx = mapping.get("z", -1)

    if min(time_idx, x_idx, y_idx, z_idx) < 0:
        return 0, "Assign Time, X, Y and Z columns before importing."

    roll_idx = mapping.get("roll", -1)
    pitch_idx = mapping.get("pitch", -1)
    yaw_idx = mapping.get("yaw", -1)

    with open(filepath, newline='') as csvfile:
        rows = list(csv.reader(csvfile))

    if has_header and rows:
        rows = rows[1:]

    target_obj.motion_data_entries.clear()
    max_idx = max(time_idx, x_idx, y_idx, z_idx, roll_idx, pitch_idx, yaw_idx)

    count = 0
    for row in rows:
        if len(row) <= max_idx:
            continue
        try:
            time = float(row[time_idx])
            x = float(row[x_idx])
            y = float(row[y_idx])
            z = float(row[z_idx])
        except (ValueError, IndexError):
            continue

        def optional(idx):
            if idx < 0:
                return 0.0
            try:
                return float(row[idx])
            except (ValueError, IndexError):
                return 0.0

        entry = target_obj.motion_data_entries.add()
        entry.time = time
        entry.x = x
        entry.y = y
        entry.z = z
        entry.roll = optional(roll_idx)
        entry.pitch = optional(pitch_idx)
        entry.yaw = optional(yaw_idx)
        count += 1

    if count == 0:
        return 0, "No valid numerical rows found with the selected columns."
    return count, None


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


def iter_action_fcurves(action):
    """Iterate over action F-Curves across classic and layered action layouts."""
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        for fcurve in fcurves:
            yield fcurve
        return

    layers = getattr(action, "layers", None) or ()
    for layer in layers:
        strips = getattr(layer, "strips", None) or ()
        for strip in strips:
            channelbags = getattr(strip, "channelbags", None) or ()
            for bag in channelbags:
                for fcurve in getattr(bag, "fcurves", None) or ():
                    yield fcurve



def set_extrapolation(obj, mode):
    """Sets the extrapolation mode for all animation curves on ``obj``."""
    if obj.animation_data and obj.animation_data.action:
        for fcurve in iter_action_fcurves(obj.animation_data.action):
            fcurve.extrapolation = mode


def animate_object_from_entries(context, obj, extrapolation_mode):
    """Keyframe ``obj`` from its stored ``motion_data_entries`` collection.

    Position values are converted from feet to meters under an Imperial unit
    system. Returns the number of keyframed rows.
    """
    scene = context.scene
    frame_rate = scene.render.fps  # User-defined FPS (synced with scene)
    unit_system = scene.unit_settings.system  # Metric or Imperial

    ensure_origin_parent_empty(obj, context)

    # Clear existing animation data
    obj.animation_data_clear()

    # Set unit conversion factor
    unit_scale = 0.3048 if unit_system == 'IMPERIAL' else 1.0  # feet -> meters

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
        if extrapolation_mode in {'LINEAR', 'CONSTANT'}:
            set_extrapolation(obj, extrapolation_mode)

        last_frame = max(frames)
        if last_frame > scene.frame_end:
            scene.frame_end = last_frame

    return len(frames)


class ImportCSVAnimationOperator(bpy.types.Operator, ImportHelper):
    """Import CSV and animate an object"""
    bl_idname = "import_anim.csv"
    bl_label = "Import CSV Animation"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".csv"
    filter_glob: bpy.props.StringProperty(default="*.csv", options={'HIDDEN'}, maxlen=255)

    def execute(self, context):
        obj = get_target_object(context)

        if obj is None:
            self.report({'ERROR'}, "No object selected")
            return {'CANCELLED'}

        filepath = self.filepath
        if not os.path.exists(filepath):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}

        # Persist imported source data on the animated object
        import_motion_data_entries(filepath, obj)

        extrapolation_mode = context.scene.anim_settings.extrapolation_mode
        animate_object_from_entries(context, obj, extrapolation_mode)

        self.report({'INFO'}, "CSV Animation Imported Successfully")
        return {'FINISHED'}


class HVE_OT_LoadMotionCSVHeaders(bpy.types.Operator, ImportHelper):
    """Load a motion CSV file and auto-map its columns (Time, X, Y, Z, Roll, Pitch, Yaw) by header name"""
    bl_idname = "import_anim.load_motion_csv_headers"
    bl_label = "Load CSV File"
    filename_ext = ".csv"
    filter_glob: bpy.props.StringProperty(default="*.csv", options={'HIDDEN'}, maxlen=255)

    def execute(self, context):
        settings = context.scene.anim_settings

        try:
            has_header, headers = read_csv_headers(self.filepath)
        except Exception as exc:  # noqa: BLE001 - surface any read error to the user
            self.report({'ERROR'}, f"Could not read CSV file: {exc}")
            return {'CANCELLED'}

        if not headers:
            self.report({'WARNING'}, "CSV file appears to be empty.")
            return {'CANCELLED'}

        # Store the loaded state so the panel dropdowns can list the columns.
        settings.motion_csv_filepath = self.filepath
        settings.motion_csv_has_header = has_header
        settings.motion_csv_headers = "\t".join(headers)

        if has_header:
            mapping = auto_map_motion_columns(headers)
        else:
            mapping = default_motion_positional_mapping(len(headers))

        # Assign enum values after the headers string is stored so the items
        # callback already exposes these identifiers.
        settings.motion_col_time = str(mapping["time"])
        settings.motion_col_x = str(mapping["x"])
        settings.motion_col_y = str(mapping["y"])
        settings.motion_col_z = str(mapping["z"])
        settings.motion_col_roll = str(mapping["roll"])
        settings.motion_col_pitch = str(mapping["pitch"])
        settings.motion_col_yaw = str(mapping["yaw"])

        if has_header:
            self.report({'INFO'}, "Headers detected and auto-mapped. Review the columns, then Import.")
        else:
            self.report({'INFO'}, "No header row found; using positional columns. Adjust if needed, then Import.")
        return {'FINISHED'}


class HVE_OT_ImportMappedMotionCSV(bpy.types.Operator):
    """Import the loaded motion CSV using the selected column mapping and animate the object"""
    bl_idname = "import_anim.import_mapped_motion_csv"
    bl_label = "Import and Animate"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.anim_settings

        obj = get_target_object(context)
        if obj is None:
            self.report({'ERROR'}, "No object selected")
            return {'CANCELLED'}

        filepath = settings.motion_csv_filepath
        if not filepath:
            self.report({'WARNING'}, "Load a CSV file first.")
            return {'CANCELLED'}
        if not os.path.exists(filepath):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}

        mapping = {
            "time": int(settings.motion_col_time),
            "x": int(settings.motion_col_x),
            "y": int(settings.motion_col_y),
            "z": int(settings.motion_col_z),
            "roll": int(settings.motion_col_roll),
            "pitch": int(settings.motion_col_pitch),
            "yaw": int(settings.motion_col_yaw),
        }

        count, error = import_mapped_motion_data(filepath, mapping, settings.motion_csv_has_header, obj)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}

        animate_object_from_entries(context, obj, settings.extrapolation_mode)
        self.report({'INFO'}, f"Imported {count} rows from the mapped CSV.")
        return {'FINISHED'}


### Registering Add-on ###
classes = [
    MotionDataEntry,
    ImportCSVAnimationOperator,
    HVE_OT_LoadMotionCSVHeaders,
    HVE_OT_ImportMappedMotionCSV,

]
