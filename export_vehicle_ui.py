
bl_info = {
    "name": "H3D format",
    "author": "EDC",
    "version": (1, 1, 0),
    "blender": (2, 83, 0),
    "location": "File > Import-Export",
    "description": "Export H3D",
    "warning": "",    
    "category": "HVE",
}

if "bpy" in locals():
    import importlib
    if "export_vehicle" in locals():
        importlib.reload(export_vehicle)

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




class H3D_PT_export_include(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_VEHICLE_OT_h3d"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "use_selection")
        layout.prop(operator, "use_hierarchy")
        layout.prop(operator, "name_decorations")



class H3D_PT_export_transform(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Transform"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_VEHICLE_OT_h3d"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "global_scale")
        layout.prop(operator, "axis_forward")
        layout.prop(operator, "axis_up")


class H3D_PT_export_geometry(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Geometry"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_VEHICLE_OT_h3d"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "use_mesh_modifiers")
        layout.prop(operator, "use_normals")
        layout.prop(operator, "use_compress")


@orientation_helper(axis_forward='-Y', axis_up='-Z')
class ExportVehicle(bpy.types.Operator, ExportHelper):
    """Export selection to OpenInventor 3D file (.h3d)"""
    bl_idname = "export_vehicle.h3d"
    bl_label = 'Export to HVE'
    bl_options = {'PRESET'}

    filename_ext = ".h3d"
    filter_glob: StringProperty(default="*.h3d", options={'HIDDEN'})

    use_selection: BoolProperty(
            name="Selection Only",
            description="Export selected objects only",
            default=True,
            )
    use_mesh_modifiers: BoolProperty(
            name="Apply Modifiers",
            description="Use transformed mesh data from each object",
            default=True,
            )
    use_normals: BoolProperty(
            name="Normals",
            description="Write normals with geometry",
            default=True,
            )
    use_compress: BoolProperty(
            name="Compress",
            description="Compress the exported file",
            default=False,
            )
    use_hierarchy: BoolProperty(
            name="Hierarchy",
            description="Export parent child relationships",
            default=True,
            )
    name_decorations: BoolProperty(
            name="Name decorations",
            description=("Add prefixes to the names of exported nodes to "
                         "indicate their type"),
            default=True,
            )


    global_scale: FloatProperty(
            name="Scale",
            min=0.01, max=1000.0,
            default=39.37,
            )

    path_mode: path_reference_mode

    def execute(self, context):
        from . import export_vehicle

        from mathutils import Matrix

        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "global_scale",
                                            "check_existing",
                                            "filter_glob",
                                            ))
        global_matrix = axis_conversion(to_forward=self.axis_forward,
                                        to_up=self.axis_up,
                                        ).to_4x4() @ Matrix.Scale(self.global_scale, 4)
        keywords["global_matrix"] = global_matrix

        return export_vehicle.save(context, **keywords)

    def draw(self, context):
        pass



def menu_func_export(self, context):
    self.layout.operator(ExportVehicle.bl_idname,
                         text="H3D Extensible 3D (.h3d)")


classes = (
    ExportVehicle,
    H3D_PT_export_include,
    H3D_PT_export_transform,
    H3D_PT_export_geometry,
)
