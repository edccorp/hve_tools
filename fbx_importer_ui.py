
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

        return operator and operator.bl_idname == "IMPORT_HVE_OT_fbx"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, "merge_body_mesh")
        layout.prop(operator, "deformation_storage")
        layout.prop(operator, "apply_mesh_cleanup")
        layout.prop(operator, "find_missing_files")



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

    merge_body_mesh: BoolProperty(
            name="Merge Body Mesh",
            description="Join each vehicle's body mesh parts into one object after import",
            default=False,
            )

    deformation_storage: EnumProperty(
            name="Deformation Storage",
            description="How imported body mesh deformation should be stored",
            items=(
                ('SHAPE_KEYS', "Shape Keys", "Keep deformation in Blender shape keys; merged meshes are rebuilt with reduced sampled shape keys"),
                ('MDD', "External MDD File", "Bake deformation to external .mdd point-cache files and attach Mesh Cache modifiers"),
            ),
            default='SHAPE_KEYS',
            )

    apply_mesh_cleanup: BoolProperty(
            name="Apply Merge by Distance and Smooth",
            description="Add Geometry Nodes modifiers that merge nearby vertices and smooth mesh shading; disable for faster renders",
            default=False,
            )

    find_missing_files: BoolProperty(
            name="Find Missing Files",
            description="Search the public HVE support-files folder for missing assets after import; disable for faster imports",
            default=False,
            )


    def execute(self, context):
        from . import fbx_importer

        from mathutils import Matrix

        return fbx_importer.load(
            context,
            self.filepath,
            merge_body_mesh=self.merge_body_mesh,
            deformation_storage=self.deformation_storage,
            apply_mesh_cleanup=self.apply_mesh_cleanup,
            find_missing_files=self.find_missing_files,
        )

    def draw(self, context):
        pass



def menu_func_export(self, context):
    self.layout.operator(ImportFBX.bl_idname,
                         text="FBX (.fbx)")


classes = (
    ImportFBX,  
    FBX_PT_fbx_importer_include,    
)