
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

import os

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


def _active_import_variables_operator(context):
    sfile = getattr(context, "space_data", None)
    operator = getattr(sfile, "active_operator", None) if sfile else None
    if operator and getattr(operator, "bl_idname", "") == "IMPORT_VARIABLES_OT_csv":
        return operator
    return None


def _set_group_variables_enabled(group_item, context):
    operator = _active_import_variables_operator(context)
    if not operator:
        return

    for variable_item in operator.variable_items:
        if variable_item.group_id != group_item.group_id:
            continue
        variable_item.enabled = True if variable_item.required else group_item.enabled


def _selected_create_options(operator):
    return {
        "create_tire_paths": operator.create_tire_paths,
        "create_skids": operator.create_skids,
        "create_paths": operator.create_paths,
        "create_velocities": operator.create_velocities,
        "create_accelerations": operator.create_accelerations,
        "create_forces": operator.create_forces,
    }


def _update_required_variable_flags(operator, context):
    if not getattr(operator, "variable_items", None):
        return

    from . import variableoutput_importer

    create_options = _selected_create_options(operator)
    required_count_by_group = {}
    for variable_item in operator.variable_items:
        variable_item.required = variableoutput_importer.is_required_variable(
            variable_item.source_name,
            **create_options,
        )
        if variable_item.required:
            variable_item.enabled = True
            required_count_by_group[variable_item.group_id] = required_count_by_group.get(variable_item.group_id, 0) + 1

    for group_item in operator.group_items:
        required_count = required_count_by_group.get(group_item.group_id, 0)
        group_item.required_count = str(required_count) if required_count else ""


def _create_object_option_updated(operator, context):
    _update_required_variable_flags(operator, context)


def _variable_scan_path(operator):
    filepath = getattr(operator, "filepath", "")
    if filepath:
        filepath = bpy.path.abspath(filepath)
    return filepath if filepath and os.path.isfile(filepath) else ""
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
    group_id: StringProperty(options={'HIDDEN'})
    group_name: StringProperty(name="Group")
    source_name: StringProperty(name="Source")
    translated_name: StringProperty(name="Translated")
    unit: StringProperty(name="Unit")
    required: BoolProperty(
        name="Required",
        description="Required for vehicle motion and cannot be disabled",
        default=False,
    )


class VariableOutputGroupItem(bpy.types.PropertyGroup):
    enabled: BoolProperty(
        name="Import",
        description="Import optional variables in this VariableOutput group",
        default=True,
        update=_set_group_variables_enabled,
    )
    group_id: StringProperty(options={'HIDDEN'})
    display_name: StringProperty(name="Group")
    vehicle_name: StringProperty(name="Vehicle")
    group_name: StringProperty(name="Group")
    required_count: StringProperty(options={'HIDDEN'})


class VariableOutputVehicleItem(bpy.types.PropertyGroup):
    enabled: BoolProperty(
        name="Import",
        description="Import this entire VariableOutput vehicle",
        default=True,
    )
    vehicle_id: StringProperty(options={'HIDDEN'})
    display_name: StringProperty(name="Vehicle")
    vehicle_name: StringProperty(name="Vehicle")


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

        if not _variable_scan_path(operator):
            operator.clear_variable_list()
            self.report({'WARNING'}, "Select a VariableOutput .hvo or .csv file before scanning variables.")
            return {'CANCELLED'}

        count = operator.refresh_variable_list()
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

        creation_box = layout.box()
        creation_box.label(text="Create Objects")
        creation_box.prop(operator, "create_tire_paths")
        creation_box.prop(operator, "create_skids")
        creation_box.prop(operator, "create_paths")
        creation_box.prop(operator, "create_velocities")
        creation_box.prop(operator, "create_accelerations")
        creation_box.prop(operator, "create_forces")

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

            if operator.vehicle_items:
                vehicle_box = layout.box()
                vehicle_box.label(text="Vehicles")
                for vehicle in operator.vehicle_items:
                    row = vehicle_box.row(align=True)
                    row.prop(vehicle, "enabled", text="")
                    row.label(text=vehicle.display_name)

            if operator.group_items:
                group_box = layout.box()
                group_box.label(text="Groups (optional variables only)")
                for group in operator.group_items:
                    row = group_box.row(align=True)
                    row.enabled = operator.is_vehicle_enabled(group.vehicle_name)
                    row.prop(group, "enabled", text="")
                    label = group.display_name
                    if group.required_count:
                        label = f"{label} ({group.required_count} required kept)"
                    row.label(text=label)

            box = layout.box()
            box.label(text="Variables")
            for item in operator.variable_items:
                row = box.row(align=True)
                row.enabled = (not item.required
                               and operator.is_vehicle_enabled(item.vehicle_name)
                               and operator.is_group_enabled(item.group_id))
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
        for item in operator.group_items:
            item.enabled = True
        for item in operator.vehicle_items:
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
        for item in operator.group_items:
            item.enabled = False
        for item in operator.vehicle_items:
            item.enabled = True
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

    create_tire_paths: BoolProperty(
        name="Tire Paths",
        description="Create tire path objects",
        default=True,
        update=_create_object_option_updated,
    )

    create_skids: BoolProperty(
        name="Skids",
        description="Create skid trace objects",
        default=True,
        update=_create_object_option_updated,
    )

    create_paths: BoolProperty(
        name="Paths",
        description="Create vehicle CG and accelerometer path curve objects",
        default=True,
        update=_create_object_option_updated,
    )

    create_velocities: BoolProperty(
        name="Velocities",
        description="Create velocity vector and component objects",
        default=True,
        update=_create_object_option_updated,
    )

    create_accelerations: BoolProperty(
        name="Accelerations",
        description="Create acceleration vector and component objects",
        default=True,
        update=_create_object_option_updated,
    )

    create_forces: BoolProperty(
        name="Forces",
        description="Create force vector objects",
        default=True,
        update=_create_object_option_updated,
    )

    variable_items: CollectionProperty(type=VariableOutputVariableItem)
    group_items: CollectionProperty(type=VariableOutputGroupItem)
    vehicle_items: CollectionProperty(type=VariableOutputVehicleItem)

    variable_scan_filepath: StringProperty(options={'HIDDEN'})

    disabled_variables: StringProperty(
        name="Disabled Variables",
        description="Internal newline-delimited VariableOutput column identifiers to skip",
        default="",
        options={'HIDDEN'},
    )

    disabled_groups: StringProperty(
        name="Disabled Groups",
        description="Internal newline-delimited VariableOutput group identifiers to skip",
        default="",
        options={'HIDDEN'},
    )

    disabled_vehicles: StringProperty(
        name="Disabled Vehicles",
        description="Internal newline-delimited VariableOutput vehicle identifiers to skip",
        default="",
        options={'HIDDEN'},
    )

    def clear_variable_list(self):
        self.variable_items.clear()
        self.group_items.clear()
        self.vehicle_items.clear()
        self.variable_scan_filepath = ""

    def refresh_variable_list(self):
        from . import variableoutput_importer

        scan_filepath = _variable_scan_path(self)
        if not scan_filepath:
            self.clear_variable_list()
            return 0

        previously_disabled = {item.variable_id for item in self.variable_items if not item.enabled}
        previously_disabled_groups = {item.group_id for item in self.group_items if not item.enabled}
        previously_disabled_vehicles = {item.vehicle_id for item in self.vehicle_items if not item.enabled}
        self.clear_variable_list()
        self.variable_scan_filepath = scan_filepath

        variables = variableoutput_importer.inspect_variable_columns(scan_filepath, **_selected_create_options(self))
        vehicle_names = []
        group_data = {}
        for variable in variables:
            vehicle_name = variable["vehicle_name"]
            if vehicle_name not in vehicle_names:
                vehicle_names.append(vehicle_name)
            group = group_data.setdefault(variable["group_id"], {
                "vehicle_name": vehicle_name,
                "group_name": variable["group_name"],
                "required_count": 0,
            })
            if variable["required"]:
                group["required_count"] += 1

        for vehicle_name in vehicle_names:
            item = self.vehicle_items.add()
            item.vehicle_id = variableoutput_importer.make_vehicle_id(vehicle_name)
            item.vehicle_name = vehicle_name
            item.display_name = vehicle_name or "(No vehicle name)"
            item.enabled = item.vehicle_id not in previously_disabled_vehicles

        for group_id, group in group_data.items():
            item = self.group_items.add()
            item.group_id = group_id
            item.vehicle_name = group["vehicle_name"]
            item.group_name = group["group_name"]
            group_label = group["group_name"] or "(No group name)"
            vehicle_label = group["vehicle_name"] or "(No vehicle name)"
            item.display_name = f"{vehicle_label}: {group_label}"
            item.required_count = str(group["required_count"]) if group["required_count"] else ""
            item.enabled = item.group_id not in previously_disabled_groups

        for variable in variables:
            item = self.variable_items.add()
            item.variable_id = variable["id"]
            item.vehicle_name = variable["vehicle_name"]
            item.group_id = variable["group_id"]
            item.group_name = variable["group_name"]
            item.source_name = variable["source_name"]
            item.translated_name = variable["translated_name"]
            item.unit = variable["unit"]
            item.required = variable["required"]
            display_name = variable["translated_name"] or variable["source_name"]
            if variable["vehicle_name"]:
                display_name = f"{variable['vehicle_name']}: {display_name}"
            item.display_name = display_name
            item.enabled = item.required or item.variable_id not in previously_disabled

        return len(self.variable_items)

    def is_vehicle_enabled(self, vehicle_name):
        from . import variableoutput_importer

        vehicle_id = variableoutput_importer.make_vehicle_id(vehicle_name)
        for item in self.vehicle_items:
            if item.vehicle_id == vehicle_id:
                return item.enabled
        return True

    def is_group_enabled(self, group_id):
        for item in self.group_items:
            if item.group_id == group_id:
                return item.enabled
        return True

    def update_disabled_variables(self):
        from . import variableoutput_importer

        disabled_vehicles = [item.vehicle_id for item in self.vehicle_items if not item.enabled]
        disabled_groups = [item.group_id for item in self.group_items if not item.enabled]
        disabled_variables = []
        disabled_vehicle_set = set(disabled_vehicles)
        disabled_group_set = set(disabled_groups)

        for item in self.variable_items:
            vehicle_disabled = variableoutput_importer.make_vehicle_id(item.vehicle_name) in disabled_vehicle_set
            group_disabled = item.group_id in disabled_group_set
            if item.required and not vehicle_disabled:
                item.enabled = True
            elif not item.enabled and not vehicle_disabled and not group_disabled:
                disabled_variables.append(item.variable_id)

        self.disabled_vehicles = "\n".join(disabled_vehicles)
        self.disabled_groups = "\n".join(disabled_groups)
        self.disabled_variables = "\n".join(disabled_variables)

    def execute(self, context):
        from . import variableoutput_importer

        from mathutils import Matrix
       
        self.update_disabled_variables()
        keywords = self.as_keywords(ignore=("check_existing",
                                            "filter_glob",
                                            "variable_items",
                                            "group_items",
                                            "vehicle_items",
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
    VariableOutputGroupItem,
    VariableOutputVehicleItem,
    IMPORT_VARIABLES_OT_refresh_variable_list,
    IMPORT_VARIABLES_OT_enable_all_variables,
    IMPORT_VARIABLES_OT_disable_optional_variables,
    ImportVariables,
    CSV_PT_variableoutput_importer_include,
)
