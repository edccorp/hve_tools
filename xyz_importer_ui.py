bl_info = {
    "name": "Import XYZ Points",
    "author": "EDC",
    "version": (1, 0, 3),
    "blender": (2, 93, 0),
    "location": "View3D > Sidebar > Import XYZ Points",
    "description": "Imports XYZ points from a CSV file, creates circles, text, and optionally connects points.",
    "category": "Import-Export",
}

if "bpy" in locals():
    import importlib
    if "xyz_importer" in locals():
        importlib.reload(xyz_importer)

import os
import bpy
from bpy.props import (
        BoolProperty,
        EnumProperty,
        FloatProperty,
        StringProperty,
        )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper,
        axis_conversion,
        path_reference_mode,
        )
         
class CSV_PT_xyz_importer_include(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "IMPORT_XYZ_OT_csv"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator
        layout.prop(operator, "scale_factor")

# Blender Operator Class
class ImportPoints(bpy.types.Operator, ImportHelper):
    """Import XYZ Points from CSV and Create Circles with Text"""
    bl_idname = "import_xyz.csv"
    bl_label = "Import XYZ Points"
    bl_options = {'PRESET'}
    
    filename_ext = ".csv"

    filter_glob: StringProperty(
            default="*.csv",
            options={'HIDDEN'},
            maxlen=255,  # Max internal buffer length, longer would be clamped.
            )
    
    scale_factor: FloatProperty(
            name="Scale Factor",
            description="Assign a scale factor",
            default=.3048,
            precision = 6,
            )    
            
    def execute(self, context):
        from . import xyz_importer
        
        from mathutils import Matrix 
        
        keywords = self.as_keywords(ignore=("check_existing",
                                            "filter_glob",
                                            ))         
        return xyz_importer.load(context, **keywords)

    def draw(self, context):
        pass

class HVE_OT_LoadPointCSVHeaders(bpy.types.Operator, ImportHelper):
    """Load a points CSV file and auto-map its columns (Point Number, X, Y, Z, Description) by header name"""
    bl_idname = "import_xyz.load_point_csv_headers"
    bl_label = "Load CSV File"
    filename_ext = ".csv"
    filter_glob: StringProperty(default="*.csv", options={'HIDDEN'}, maxlen=255)

    def execute(self, context):
        from . import xyz_importer

        settings = context.scene.anim_settings

        try:
            has_header, headers = xyz_importer.read_csv_headers(self.filepath)
        except Exception as exc:  # noqa: BLE001 - surface any read error to the user
            self.report({'ERROR'}, f"Could not read CSV file: {exc}")
            return {'CANCELLED'}

        if not headers:
            self.report({'WARNING'}, "CSV file appears to be empty.")
            return {'CANCELLED'}

        # Store the loaded state so the panel dropdowns can list the columns.
        settings.point_csv_filepath = self.filepath
        settings.point_csv_has_header = has_header
        settings.point_csv_headers = "\t".join(headers)

        if has_header:
            mapping = xyz_importer.auto_map_point_columns(headers)
        else:
            mapping = xyz_importer.default_point_positional_mapping(len(headers))

        # Assign enum values after the headers string is stored so the items
        # callback already exposes these identifiers.
        settings.point_col_number = str(mapping["point_number"])
        settings.point_col_x = str(mapping["x"])
        settings.point_col_y = str(mapping["y"])
        settings.point_col_z = str(mapping["z"])
        settings.point_col_description = str(mapping["description"])

        if has_header:
            self.report({'INFO'}, "Headers detected and auto-mapped. Review the columns, then Import.")
        else:
            self.report({'INFO'}, "No header row found; using positional columns. Adjust if needed, then Import.")
        return {'FINISHED'}


class HVE_OT_ImportMappedPoints(bpy.types.Operator):
    """Import the loaded points CSV using the selected column mapping"""
    bl_idname = "import_xyz.import_mapped_points"
    bl_label = "Import Points"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import xyz_importer

        settings = context.scene.anim_settings

        filepath = settings.point_csv_filepath
        if not filepath:
            self.report({'WARNING'}, "Load a CSV file first.")
            return {'CANCELLED'}
        if not os.path.exists(filepath):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}

        mapping = {
            "point_number": int(settings.point_col_number),
            "x": int(settings.point_col_x),
            "y": int(settings.point_col_y),
            "z": int(settings.point_col_z),
            "description": int(settings.point_col_description),
        }

        points, error = xyz_importer.read_points_mapped(filepath, mapping, settings.point_csv_has_header)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}

        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        xyz_importer.create_point_objects(context, points, settings.point_scale_factor)
        self.report({'INFO'}, f"Imported {len(points)} points.")
        return {'FINISHED'}


def menu_func_export(self, context):
    self.layout.operator(ImportPoints.bl_idname,
                         text="Points (.csv)")
classes = (
ImportPoints,
CSV_PT_xyz_importer_include,
HVE_OT_LoadPointCSVHeaders,
HVE_OT_ImportMappedPoints,
)