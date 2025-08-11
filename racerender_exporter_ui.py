
bl_info = {
    "name": "RaceRender Exporter",
    "author": "EDC",
    "version": (1, 1, 0),
    "blender": (2, 83, 0),
    "location": "File > Import-Export",
    "description": "Export to csv for RaceRender",
    "warning": "",    
    "category": "HVE",
}

if "bpy" in locals():
    import importlib
    if "racerender_exporter" in locals():
        importlib.reload(racerender_exporter)

import bpy
import os
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

class CSV_PT_export_racerender_transform(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_RACERENDER_OT_csv"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        
class ExportRaceRender(bpy.types.Operator, ExportHelper):
    """Import motion variables from CSV"""
    bl_idname = "export_racerender.csv"
    bl_label = 'Export to csv for RaceRender'
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
            default=1,
            precision = 6,
            )    

    def execute(self, context):
        from . import racerender_exporter
        from mathutils import Matrix 
        
        keywords = self.as_keywords(ignore=("check_existing",
                                            "filter_glob",
                                            ))         
        return racerender_exporter.save(context, **keywords)

    def draw(self, context):
        pass



def menu_func_export(self, context):
    self.layout.operator(ExportRaceRender.bl_idname,  # Corrected class reference
                         text="RaceRender (.csv)")


classes = (
    ExportRaceRender,
    CSV_PT_export_racerender_transform,    
)