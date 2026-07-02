
bl_info = {
    "name": "Contacts Exporter",
    "author": "EDC",
    "version": (1, 1, 0),
    "blender": (2, 83, 0),
    "location": "File > Import-Export",
    "description": "Export Contact Points",
    "warning": "",    
    "category": "HVE",
}

if "bpy" in locals():
    import importlib
    if "contacts_exporter" in locals():
        importlib.reload(contacts_exporter)

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


class CSV_PT_export_contacts_transform(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Transform"
    bl_parent_id = "FILE_PT_operator"
    
    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_CONTACTS_OT_csv"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "global_scale")
   
class ExportContacts(bpy.types.Operator, ExportHelper):
    """Export contacts point to csv and txt"""
    bl_idname = "export_contacts.csv"
    bl_label = 'Export to csv'
    bl_options = {'PRESET'}

    filename_ext = ".csv"
    filter_glob: StringProperty(default="*.csv", options={'HIDDEN'})

    global_scale: FloatProperty(
            name="Scale",
            min=0.01, max=1000.0,
            default=39.37,
            )


    def execute(self, context):
        from . import contacts_exporter

        from mathutils import Matrix

        keywords = self.as_keywords(ignore=("check_existing",
                                            "filter_glob",
                                            ))


        return contacts_exporter.save(context, **keywords)

    def draw(self, context):
        pass



def menu_func_export(self, context):
    self.layout.operator(ExportContacts.bl_idname,
                         text="Contacts (.csv)")


classes = (
    ExportContacts, 
    CSV_PT_export_contacts_transform,    
)