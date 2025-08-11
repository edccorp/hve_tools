
bl_info = {
    "name": "VariableOutput Importer",
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
    if "variableoutput_importer" in locals():
        importlib.reload(variableoutput_importer)

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
# Function to update scale_factor based on the selected unit
def update_scale_factor(self, context):
    if self.scale_unit == 'FEET':
        self.scale_factor = 0.3048  # Convert feet to meters
    else:
        self.scale_factor = 1.0  # Meters remain the same
        
class CSV_PT_variableoutput_importer_include(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "IMPORT_VARIABLES_OT_csv"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator
        layout.prop(operator, "scale_unit")
        layout.prop(operator, "scale_factor")
        layout.prop(operator, "save_separate_csv")


class ImportVariables(bpy.types.Operator, ExportHelper):
    """Import motion variables from CSV"""
    bl_idname = "import_variables.csv"
    bl_label = 'Import motion variables from CSV'
    bl_options = {'PRESET'}

    filename_ext = ".csv"

    filter_glob: StringProperty(
            default="*.hvo;*.csv",
            options={'HIDDEN'},
            maxlen=255,  # Max internal buffer length, longer would be clamped.
            )

    save_separate_csv: BoolProperty(
            name="Save Vehicle CSVs",
            description="Export csv for each vehcile",
            default=False,
            )    
            
    scale_unit: EnumProperty(
        name="Scale Unit",
        description="Choose scale unit",
        items=[
            ('METERS', "Meters", "Use meters as scale"),
            ('FEET', "Feet", "Use feet as scale"),
        ],
        default='FEET',
        update=update_scale_factor
    )

    scale_factor: FloatProperty(
        name="Scale Factor",
        description="Assigned scale factor",
        default=0.3048,  # Default to feet conversion
        precision=6,
    )

    def execute(self, context):
        from . import variableoutput_importer

        from mathutils import Matrix
       
        keywords = self.as_keywords(ignore=("check_existing",
                                            "filter_glob",
                                            ))
                                            
        return variableoutput_importer.load(context, **keywords)

    def draw(self, context):
        pass



def menu_func_export(self, context):
    self.layout.operator(ImportVariables.bl_idname,
                         text="VariableOutput (.csv)")


classes = (
    ImportVariables,  
    CSV_PT_variableoutput_importer_include,    
)