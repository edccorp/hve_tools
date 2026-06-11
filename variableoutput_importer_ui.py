
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
        CollectionProperty,
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
        


class VariableOutputVariableItem(bpy.types.PropertyGroup):
    enabled: BoolProperty(
        name="Import",
        description="Import this VariableOutput column",
        default=True,
    )
    variable_id: StringProperty(options={'HIDDEN'})
    display_name: StringProperty(name="Variable")
    vehicle_name: StringProperty(name="Vehicle")
    source_name: StringProperty(name="Source")
    translated_name: StringProperty(name="Translated")
    unit: StringProperty(name="Unit")
    required: BoolProperty(
        name="Required",
        description="Required for vehicle motion and cannot be disabled",
        default=False,
    )


class IMPORT_VARIABLES_OT_refresh_variable_list(bpy.types.Operator):
    """Scan the selected VariableOutput file and populate the variable toggles"""
    bl_idname = "import_variables.refresh_variable_list"
    bl_label = "Scan Variables"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        sfile = context.space_data
        operator = getattr(sfile, "active_operator", None) if sfile else None
        if not operator or operator.bl_idname != "IMPORT_VARIABLES_OT_csv":
            self.report({'WARNING'}, "Open the VariableOutput importer to scan variables.")
            return {'CANCELLED'}

        operator.refresh_variable_list()
        count = len(operator.variable_items)
        if count:
            self.report({'INFO'}, f"Found {count} VariableOutput variable column(s).")
        else:
            self.report({'WARNING'}, "No VariableOutput variables found in the selected file.")
        return {'FINISHED'}

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

        layout.separator()
        row = layout.row(align=True)
        row.operator(IMPORT_VARIABLES_OT_refresh_variable_list.bl_idname, icon='FILE_REFRESH')
        if operator.variable_items:
            row.label(text=f"{len(operator.variable_items)} variable columns")
        else:
            layout.label(text="Scan the selected file to disable variables before import.")

        if operator.variable_items:
            controls = layout.row(align=True)
            controls.operator("import_variables.enable_all_variables", text="Enable All")
            controls.operator("import_variables.disable_optional_variables", text="Disable Optional")

            box = layout.box()
            for item in operator.variable_items:
                row = box.row(align=True)
                row.enabled = not item.required
                row.prop(item, "enabled", text="")
                label = item.display_name
                if item.unit:
                    label = f"{label} [{item.unit}]"
                if item.required:
                    label = f"{label} (required)"
                row.label(text=label)


class IMPORT_VARIABLES_OT_enable_all_variables(bpy.types.Operator):
    """Enable every scanned VariableOutput variable"""
    bl_idname = "import_variables.enable_all_variables"
    bl_label = "Enable All Variables"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        operator = context.space_data.active_operator
        for item in operator.variable_items:
            item.enabled = True
        return {'FINISHED'}


class IMPORT_VARIABLES_OT_disable_optional_variables(bpy.types.Operator):
    """Disable every non-required scanned VariableOutput variable"""
    bl_idname = "import_variables.disable_optional_variables"
    bl_label = "Disable Optional Variables"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        operator = context.space_data.active_operator
        for item in operator.variable_items:
            item.enabled = item.required
        return {'FINISHED'}


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

    variable_items: CollectionProperty(type=VariableOutputVariableItem)

    variable_scan_filepath: StringProperty(options={'HIDDEN'})

    disabled_variables: StringProperty(
        name="Disabled Variables",
        description="Internal newline-delimited VariableOutput column identifiers to skip",
        default="",
        options={'HIDDEN'},
    )

    def refresh_variable_list(self):
        from . import variableoutput_importer

        previously_disabled = {item.variable_id for item in self.variable_items if not item.enabled}
        self.variable_items.clear()
        self.variable_scan_filepath = self.filepath

        for variable in variableoutput_importer.inspect_variable_columns(self.filepath):
            item = self.variable_items.add()
            item.variable_id = variable["id"]
            item.vehicle_name = variable["vehicle_name"]
            item.source_name = variable["source_name"]
            item.translated_name = variable["translated_name"]
            item.unit = variable["unit"]
            item.required = variable["required"]
            display_name = variable["translated_name"] or variable["source_name"]
            if variable["vehicle_name"]:
                display_name = f"{variable['vehicle_name']}: {display_name}"
            item.display_name = display_name
            item.enabled = item.required or item.variable_id not in previously_disabled

    def update_disabled_variables(self):
        disabled = []
        for item in self.variable_items:
            if item.required:
                item.enabled = True
            elif not item.enabled:
                disabled.append(item.variable_id)
        self.disabled_variables = "\n".join(disabled)

    def execute(self, context):
        from . import variableoutput_importer

        from mathutils import Matrix
       
        self.update_disabled_variables()
        keywords = self.as_keywords(ignore=("check_existing",
                                            "filter_glob",
                                            "variable_items",
                                            "variable_scan_filepath",
                                            ))

        return variableoutput_importer.load(context, **keywords)

    def draw(self, context):
        pass



def menu_func_export(self, context):
    self.layout.operator(ImportVariables.bl_idname,
                         text="VariableOutput (.csv)")


classes = (
    VariableOutputVariableItem,
    IMPORT_VARIABLES_OT_refresh_variable_list,
    IMPORT_VARIABLES_OT_enable_all_variables,
    IMPORT_VARIABLES_OT_disable_optional_variables,
    ImportVariables,
    CSV_PT_variableoutput_importer_include,
)
