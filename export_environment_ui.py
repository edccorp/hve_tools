
bl_info = {
    "name": "Environment format",
    "author": "EDC",
    "version": (1, 1, 0),
    "blender": (2, 83, 0),
    "location": "File > Import-Export",
    "description": "Export Environment",
    "warning": "",    
    "category": "HVE",
}

if "bpy" in locals():
    import importlib
    if "export_environment" in locals():
        importlib.reload(export_environment)

import bpy
from bpy.props import (
        BoolProperty,
        StringProperty,
        )
from bpy_extras.io_utils import (
        ExportHelper,
        path_reference_mode,
        )




class H3D_PT_export_environment_include(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"
    
    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_ENVIRONMENT_OT_h3d"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "use_selection")
        layout.prop(operator, "name_decorations")



class H3D_PT_export_environment_geometry(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Geometry"
    bl_parent_id = "FILE_PT_operator"
    
    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_ENVIRONMENT_OT_h3d"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "use_normals")
        layout.prop(operator, "use_compress")


class ExportEnvironment(bpy.types.Operator, ExportHelper):
    """Export selection to OpenInventor 3D file (.h3d)"""
    bl_idname = "export_environment.h3d"
    bl_label = 'Export to HVE'
    bl_options = {'PRESET'}

    filename_ext = ".h3d"
    filter_glob: StringProperty(default="*.h3d", options={'HIDDEN'})

    use_selection: BoolProperty(
            name="Selection Only",
            description="Export selected objects only",
            default=True,
            )
    use_normals: BoolProperty(
            name="Normals",
            description="Write normals with geometry",
            default=False,
            )
    use_compress: BoolProperty(
            name="Compress",
            description="Compress the exported file",
            default=False,
            )
    name_decorations: BoolProperty(
            name="Name decorations",
            description=("Add prefixes to the names of exported nodes to "
                         "indicate their type"),
            default=True,
            )


    path_mode: path_reference_mode

    def execute(self, context):
        from . import export_environment

        keywords = self.as_keywords(ignore=("check_existing",
                                            "filter_glob",
                                            ))
        # HVE environment exports use a fixed inches conversion.  Axis changes
        # are intentionally not exposed because the HVE coordinate conversion is
        # baked by the mesh exporter itself.
        keywords["global_matrix"] = export_environment.hve_global_scale_matrix()

        return export_environment.save(context, **keywords)

    def draw(self, context):
        pass



def menu_func_export(self, context):
    self.layout.operator(ExportEnvironment.bl_idname,
                         text="H3D Extensible 3D (.h3d)")


classes = (
    ExportEnvironment,
    H3D_PT_export_environment_include,
    H3D_PT_export_environment_geometry,
)
