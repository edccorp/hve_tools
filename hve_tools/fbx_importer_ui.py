
bl_info = {
    "name": "FBX Importer",
    "author": "EDC",
    "version": (1, 1, 0),
    "blender": (2, 83, 0),
    "location": "File > Import-Export",
    "description": "Import HVE motion and variables",
    "warning": "",    
    "category": "HVE",
}

if "bpy" in locals():
    import importlib
    if "fbx_importer" in locals():
        importlib.reload(fbx_importer)

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
        
class FBX_PT_fbx_importer_include(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "IMPORT_FBX_OT_fbx"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator




class ImportFBX(bpy.types.Operator, ExportHelper):
    """Import motion FBX from HVE"""
    bl_idname = "import_hve.fbx"
    bl_label = 'Import FBX from HVE'
    bl_options = {'PRESET'}

    filename_ext = ".fbx"

    filter_glob: StringProperty(
            default="*.fbx",
            options={'HIDDEN'},
            maxlen=255,  # Max internal buffer length, longer would be clamped.
            )


    def execute(self, context):
        from . import fbx_importer

        from mathutils import Matrix

        return fbx_importer.load(context, self.filepath)

    def draw(self, context):
        pass



def menu_func_export(self, context):
    self.layout.operator(ImportFBX.bl_idname,
                         text="FBX (.fbx)")


classes = (
    ImportFBX,  
    FBX_PT_fbx_importer_include,    
)