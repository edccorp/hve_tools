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

def menu_func_export(self, context):
    self.layout.operator(ImportPoints.bl_idname,
                         text="Points (.csv)")
classes = (
ImportPoints,
CSV_PT_xyz_importer_include
)