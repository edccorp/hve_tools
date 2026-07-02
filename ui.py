import os
import numpy as np
import json
import bpy
import re
import csv
from bpy.props import FloatProperty, CollectionProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ImportHelper

PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hve_presets")

def get_preset_list(self, context):
    """Gets the list of saved presets, displaying names without .json but keeping full filename for loading."""
    presets = [
        (f, os.path.splitext(f)[0], "")  # ✅ Show filename without .json, but store full filename
        for f in os.listdir(PRESET_DIR) if f.endswith(".json")
    ]
    return presets if presets else [("NONE", "No Presets Available", "")]

def sanitize_filename(name):
    """Sanitize poName to be a valid filename."""
    name = name.strip().replace(" ", "_")  # Replace spaces with underscores
    name = re.sub(r"[^\w\-_]", "", name)  # Remove invalid characters
    return name or "Unnamed_Preset"  # Ensure a fallback name

def save_hve_environment():

    """Save HVE environment properties to a json file."""
    obj = bpy.context.object
    if not obj or not hasattr(obj, "hve_env_props"):
        return

    # Get sanitized filename from poName
    preset_name = sanitize_filename(obj.hve_env_props.set_env_props.poName)
    filename = f"{preset_name}.json"
    
    # Ensure a valid filename
    if not preset_name:
        preset_name = "Unnamed_Preset"  # Fallback if poName is empty
    
    # Replace spaces with underscores and remove invalid characters
    preset_name = preset_name.replace(" ", "_")
    # Replace spaces with underscores and remove invalid characters
    preset_name = preset_name.replace(",", "_")    
    # Ensure .json extension
    filename = f"{preset_name}.json"
    
    filepath = os.path.join(PRESET_DIR, filename)
    
    try:
        # Ensure the directory exists
        os.makedirs(PRESET_DIR, exist_ok=True)
   
        data = {prop: getattr(obj.hve_env_props.set_env_props, prop) for prop in obj.hve_env_props.set_env_props.__annotations__}

        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"❌ Error saving HVE environment: {e}")
    
def load_hve_environment(filepath):
    """Load HVE environment properties from a json file."""
    obj = bpy.context.object
    if not obj or not hasattr(obj, "hve_env_props"):
        return

    with open(filepath, "r") as f:
        data = json.load(f)

    for prop, value in data.items():
        setattr(obj.hve_env_props.set_env_props, prop, value)

def apply_preset(self, context):
    """Apply a selected preset from the dropdown."""
    if self.hve_preset == "NONE":
        return
    load_hve_environment(os.path.join(PRESET_DIR, self.hve_preset))

def preferences():
    a = os.path.split(os.path.split(os.path.realpath(__file__))[0])[1]
    p = bpy.context.preferences.addons[a].preferences
    return p


def sync_fps_with_scene(self, context):
    """Syncs UI FPS field when scene FPS is changed externally"""
    if context.scene.render.fps != context.scene.anim_settings.anim_fps:
        context.scene.anim_settings.anim_fps = context.scene.render.fps
        
def update_panel_bl_category(self, context):
    main_panels = (HVE_PT_pre, HVE_PT_post, HVE_PT_other_tools, HVE_PT_documentation)
    sub_panels = (
        HVE_PT_mechanist_setup,
        HVE_PT_mechanist_export,
        HVE_PT_fbx_importer,
        HVE_PT_variableoutput_importer,
        HVE_PT_edr_importer,
        HVE_PT_xyzrpy_importer,

        HVE_PT_point_importer,
        HVE_PT_motion_paths,
        HVE_PT_timed_location_markers,
        HVE_PT_scale_objects,
        HVE_PT_speed_acceleration,
        HVE_PT_point_cloud_tools,
        HVE_PT_pc_import,
        HVE_PT_pc_filter,
        HVE_PT_pc_ground,
        HVE_PT_surface_reconstruct,
        HVE_PT_race_render_exporter,
    )

    try:
        for p in main_panels:
            bpy.utils.unregister_class(p)
        for sp in sub_panels:
            bpy.utils.unregister_class(sp)
        prefs = preferences()
        c = prefs.category_custom
        n = ''
        if c:
            n = prefs.category_custom_name
        else:
            v = prefs.category
            ei = prefs.bl_rna.properties['category'].enum_items
            for e in ei:
                if e.identifier == v:
                    n = e.name
        if n == '':
            raise Exception('Name is empty string')
        for p in main_panels:
            p.bl_category = n
            bpy.utils.register_class(p)
        for sp in sub_panels:
            bpy.utils.register_class(sp)
    except Exception as e:
        print('HVE setting tab name failed ({})'.format(str(e)))


HVE_OBJECT_TYPES = {
    "ENVIRONMENT": "Environment",
    "VEHICLE": "Vehicle",
    "GATB_SURFACE": "GATB Surface",
}


def get_object_hve_type(obj):
    if not obj or not hasattr(obj, "hve_type") or not hasattr(obj.hve_type, "set_type"):
        return None
    return obj.hve_type.set_type.type


def get_selected_hve_type_counts(context):
    counts = {}
    for obj in context.selected_objects:
        obj_type = get_object_hve_type(obj)
        if obj_type:
            counts[obj_type] = counts.get(obj_type, 0) + 1
    return counts


def format_hve_type_counts(counts):
    return ", ".join(
        f"{count} {HVE_OBJECT_TYPES.get(obj_type, obj_type)}"
        for obj_type, count in counts.items()
    )


class HVETOOLS_OT_set_selected_hve_type(bpy.types.Operator):
    bl_idname = "hvetools.set_selected_hve_type"
    bl_label = "Classify Selected Objects"
    bl_description = "Set the HVE object type on all selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    object_type: bpy.props.EnumProperty(
        name="Object Type",
        items=(
            ('ENVIRONMENT', "Environment", "Classify selected objects as HVE environment objects"),
            ('VEHICLE', "Vehicle", "Classify selected objects as HVE vehicle objects"),
            ('GATB_SURFACE', "GATB Surface", "Classify selected objects as GATB contact surfaces"),
        ),
        default='ENVIRONMENT',
    )

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        changed = 0
        for obj in context.selected_objects:
            if not hasattr(obj, "hve_type") or not hasattr(obj.hve_type, "set_type"):
                continue
            obj.hve_type.set_type.type = self.object_type
            changed += 1

        label = HVE_OBJECT_TYPES.get(self.object_type, self.object_type)
        self.report({'INFO'}, f"Classified {changed} selected object(s) as {label}")
        return {'FINISHED'}


class HVETOOLS_OT_copy_surface_to_selected(bpy.types.Operator):
    bl_idname = "hvetools.copy_surface_to_selected"
    bl_label = "Copy Type + Overlay to Selected"
    bl_description = "Copy poSurfaceType and polabel from the active object to the other selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        src = context.active_object
        if not src or not hasattr(src, "hve_env_props"):
            self.report({'ERROR'}, "Active object missing hve_env_props")
            return {'CANCELLED'}

        src_env = src.hve_env_props.set_env_props

        copied = 0
        for obj in context.selected_objects:
            if obj == src:
                continue
            if not hasattr(obj, "hve_env_props"):
                continue

            dst_env = obj.hve_env_props.set_env_props

            # 👇 copy the two properties you asked for
            dst_env.poSurfaceType = src_env.poSurfaceType
            dst_env.polabel = src_env.polabel

            copied += 1

        self.report({'INFO'}, f"Copied to {copied} object(s)")
        return {'FINISHED'}

class HVE_OT_open_user_guide(bpy.types.Operator):
    """Open the HVE Tools user guide in your web browser"""
    bl_idname = "hve.open_user_guide"
    bl_label = "Open User Guide"

    _GITHUB_URL = "https://github.com/edccorp/hve_tools/blob/main/USER_GUIDE.md"

    def execute(self, context):
        import webbrowser
        import pathlib

        base = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(base, "docs", "USER_GUIDE.html")

        if os.path.exists(html_path):
            webbrowser.open(pathlib.Path(html_path).as_uri())
            self.report({'INFO'}, "Opened the HVE Tools user guide.")
        else:
            webbrowser.open(self._GITHUB_URL)
            self.report({'INFO'}, "Bundled guide not found; opened the online guide.")
        return {'FINISHED'}


class HVE_PT_mechanist_base(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "HVEMechanist Base"

    def prop_name(self, cls, prop, colon=False):
        for p in cls.bl_rna.properties:
            if p.identifier == prop:
                if colon:
                    return "{}:".format(p.name)
                return p.name
        return ''

    def third_label_two_thirds_prop(self, cls, prop, uil):
        f = 0.33
        r = uil.row()
        s = r.split(factor=f)
        s.label(text=self.prop_name(cls, prop, True))
        s = s.split(factor=1.0)
        r = s.row()
        r.prop(cls, prop, text='')

    def table_one_third_label_two_thirds_value(self, uil, label, value, colon=True, icon=None):
        f = 0.33
        r = uil.row()
        s = r.split(factor=f)
        if colon:
            s.label(text='{}:'.format(label))
        else:
            s.label(text='{}'.format(label))
        s = s.split(factor=1.0)
        r = s.row()
        r.label(text='{}'.format(value))

    @classmethod
    def poll(cls, context):
        o = context.active_object
        if o is None:
            return False
        return True

    def draw(self, context):
        o = context.active_object
        if o is None:
            self.layout.label(text='Select an object..', icon='ERROR')
            return

        l = self.layout
        c = l.column()
        c.separator()

# === PRE GROUP ===
class HVE_PT_pre(HVE_PT_mechanist_base):
    bl_label = "Pre-Simulation Setup"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        l = self.layout
        col = l.column(align=True)
        col.label(text="Configure scene objects before export.", icon='INFO')
        col.label(text="Use H3D Setup, then run Export to HVE.")

class HVE_PT_mechanist_export(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Export to HVE"
    bl_parent_id = "HVE_PT_pre"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        l = self.layout
        selected = list(context.selected_objects)
        if not selected:
            l.label(text='Select object(s) to export.', icon='ERROR')
            return

        counts = get_selected_hve_type_counts(context)
        if not counts:
            l.label(text="Selected object(s) do not have an HVE type", icon='ERROR')
            l.label(text="Classify selected objects before exporting.", icon='INFO')
            self.draw_classify_selected_buttons(l)
            return

        if len(counts) > 1 or sum(counts.values()) != len(selected):
            l.label(text="Mixed HVE object types selected", icon='ERROR')
            l.label(text=format_hve_type_counts(counts), icon='INFO')
            l.label(text="Classify all selected objects as one type?", icon='QUESTION')
            self.draw_classify_selected_buttons(l)
            return

        obj_type = next(iter(counts))
        selected_count = counts[obj_type]
        l.label(text=f"Selected: {selected_count} {HVE_OBJECT_TYPES.get(obj_type, obj_type)} object(s)", icon='INFO')

        if obj_type == "VEHICLE":
            l.operator("export_vehicle.h3d", text="Export Vehicle", icon='EXPORT')
        elif obj_type == "ENVIRONMENT":
            l.operator("export_environment.h3d", text="Export Environment", icon='EXPORT')
        elif obj_type == "GATB_SURFACE":
            l.operator("export_contacts.csv", text="Export GATB Surfaces", icon='EXPORT')
        else:
            l.label(text="Invalid HVE Type", icon='ERROR')
            l.label(text="Set HVE Type in Object Setup.", icon='INFO')

    def draw_classify_selected_buttons(self, layout):
        row = layout.row(align=True)
        for object_type, label in HVE_OBJECT_TYPES.items():
            op = row.operator("hvetools.set_selected_hve_type", text=label)
            op.object_type = object_type



class HVE_PT_mechanist_setup(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "H3D Setup"
    bl_parent_id = "HVE_PT_pre"
    bl_options = {'DEFAULT_CLOSED'}

    bpy.types.Scene.hve_preset = bpy.props.EnumProperty(
        name="Presets",
        description="Select a saved preset",
        items=get_preset_list,
        update=apply_preset
    )
    
    @classmethod
    def poll(cls, context):
        return True

    def draw_collapsible_panel(self, parent, scene, toggle_prop, label, icon=None):
        is_open = getattr(scene, toggle_prop)

        box = parent.box()
        row = box.row(align=True)
        row.prop(
            scene,
            toggle_prop,
            text=label,
            icon='TRIA_DOWN' if is_open else 'TRIA_RIGHT',
            emboss=False,
        )
        if icon:
            row.label(text="", icon=icon)

        return box if is_open else None

    def draw_collapsible_section(self, parent, data, toggle_prop, label, props):
        scene = bpy.context.scene
        box = self.draw_collapsible_panel(parent, scene, toggle_prop, label)

        if box:
            for prop_name in props:
                box.prop(data, prop_name)

    def draw(self, context):
        o = context.active_object
        if o is None:
            self.layout.label(text='Select an object..', icon='ERROR')
            return

        scene = context.scene
        lights = o.hve_vehicle_light
        types = o.hve_type
        env_props = o.hve_env_props

        l = self.layout
        c = l.column()

        c.separator()
        materials_box = self.draw_collapsible_panel(
            c, scene, "hve_setup_show_materials", "Add Materials", icon='MATERIAL'
        )
        if materials_box:
            materials_box.operator("hve_material.add_all_materials", text="Add Materials", icon='MATERIAL')

        c.separator()
        object_type_box = self.draw_collapsible_panel(
            c, scene, "hve_setup_show_object_type", "Object Type", icon='OUTLINER_OB_EMPTY'
        )
        selected_counts = get_selected_hve_type_counts(context)
        has_mixed_selection = (
            len(selected_counts) > 1
            or sum(selected_counts.values()) != len(context.selected_objects)
        )
        if object_type_box:
            object_type_box.prop(types.set_type, 'type')
            if has_mixed_selection:
                object_type_box.label(text="Mixed HVE object types selected", icon='ERROR')
                object_type_box.label(text="Classify all selected objects as one type?", icon='QUESTION')
                row = object_type_box.row(align=True)
                for object_type, label in HVE_OBJECT_TYPES.items():
                    op = row.operator("hvetools.set_selected_hve_type", text=label)
                    op.object_type = object_type

        enum_value = getattr(getattr(types, "set_type", None), "type", None)
        if enum_value == "VEHICLE" and not has_mixed_selection:
            c.separator()
            vehicle_lighting_box = self.draw_collapsible_panel(
                c, scene, "hve_setup_show_vehicle_lighting", "Vehicle Lighting", icon='LIGHT'
            )
            if vehicle_lighting_box:
                vehicle_lighting_box.prop(lights.make_light, 'type')
        elif enum_value == "ENVIRONMENT" and not has_mixed_selection:
            c.separator()
            terrain_box = self.draw_collapsible_panel(
                c, scene, "hve_setup_show_terrain", "Terrain Properties", icon='WORLD'
            )
            if terrain_box:
                surface_box = self.draw_collapsible_panel(
                    terrain_box, scene, "hve_setup_show_surface", "Surface"
                )

                if surface_box:
                    surface_box.prop(env_props.set_env_props, "poSurfaceType")
                    surface_box.prop(env_props.set_env_props, "polabel")

                    # 👇 your copy button goes HERE (between polabel and poName/material)
                    surface_box.operator("hvetools.copy_surface_to_selected", icon='DUPLICATE')

                    surface_box.prop(env_props.set_env_props, "poName")
                    surface_box.prop(env_props.set_env_props, "poFriction")

                self.draw_collapsible_section(
                    terrain_box,
                    env_props.set_env_props,
                    "hve_setup_show_water",
                    "Water",
                    ["poWaterDepth", "poStaticWater"],
                )

                self.draw_collapsible_section(
                    terrain_box,
                    env_props.set_env_props,
                    "hve_setup_show_soil",
                    "Soil",
                    ["poBekkerConst", "poKphi", "poKc", "poPcntMoisture", "poPcntClay"],
                )

                self.draw_collapsible_section(
                    terrain_box,
                    env_props.set_env_props,
                    "hve_setup_show_forces",
                    "Forces",
                    ["poForceConst", "poForceLinear", "poForceQuad", "poForceCubic", "poForceUnload", "poRateDamping"],
                )
       
            c.separator()

            # Save / Load Buttons
            row = c.row()
            row.operator("hve.save_preset", text="Save Preset", icon="EXPORT")
            row.operator("hve.load_preset", text="Load Preset", icon="IMPORT")

            c.separator()

            # Preset Dropdown
            c.prop(context.scene, "hve_preset", text="Apply Preset")

class HVE_OT_save_preset(bpy.types.Operator):
    """Save the current HVE environment settings as a preset."""
    bl_idname = "hve.save_preset"
    bl_label = "Save HVE Preset"
    
    def execute(self, context):
        save_hve_environment()
        self.report({'INFO'}, "Preset saved")
        return {'FINISHED'}


class HVE_OT_load_preset(bpy.types.Operator):
    """Load an HVE environment preset from a file."""
    bl_idname = "hve.load_preset"
    bl_label = "Load HVE Preset"
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        load_hve_environment(self.filepath)
        self.report({'INFO'}, f"Preset loaded: {self.filepath}")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# === POST GROUP ===
class HVE_PT_post(HVE_PT_mechanist_base):
    bl_label = "Post-Simulation Processing"
    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        l = self.layout
        col = l.column(align=True)
        col.label(text="Import or export simulation results.", icon='INFO')
        col.label(text="Choose a tool below based on file type.")
        


class HVE_PT_variableoutput_importer(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Variable Output Importer"
    bl_parent_id = "HVE_PT_post"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        target_obj = scene.anim_settings.anim_object
        l = self.layout
        c = l.column()
        

        # Contacts Exporter controls
        c.label(text="CSV Format: Time + Variable Output Columns")
        c.operator("import_variables.csv", text="Import Variable Output CSV", icon='IMPORT')
        
class HVE_PT_fbx_importer(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "HVE FBX Importer"
    bl_parent_id = "HVE_PT_post"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        l = self.layout

        l.operator("import_hve.fbx", text="Import FBX", icon='IMPORT')

        l.separator()
        l.prop(scene, "fbx_shape_key_max_samples", text="Max Shape Key Samples")
        l.label(text="Process: Reduce Keys → Merge Meshes → Smooth", icon='INFO')
        l.operator("import_hve.process_all", text="Process Imported FBX", icon='PLAY')
        l.prop(scene, "fbx_process_collection", text="Process Collection")
        if scene.fbx_process_collection:
            l.label(text=f"Only meshes under '{scene.fbx_process_collection.name}'", icon='FILTER')
        else:
            l.label(text="Empty = process all imported vehicles", icon='INFO')

class HVE_PT_other_tools(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Other Tools"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        l = self.layout
        col = l.column(align=True)
        col.label(text="Utilities for data prep and analysis.", icon='TOOL_SETTINGS')
        col.label(text="Select a utility panel below.")

class HVE_PT_edr_importer(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "EDR Data Importer / Entry"
    bl_parent_id = "HVE_PT_other_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene        
        anim_settings = scene.anim_settings  # Access property group
        anim_settings.sync_edr_settings_from_target()
        target_obj = anim_settings.edr_anim_object
        edr_mode = anim_settings.edr_input_mode

        l = self.layout
        c = l.column()

        # Mode-specific CSV format hint
        if edr_mode == 'STEERING_WHEEL_ANGLE':
            c.label(text="CSV Format: Time,Speed,SteeringWheelAngle")
        elif edr_mode == 'PATH_FOLLOW':
            c.label(text="CSV Format: Time,Speed (path sets heading)")
        else:
            c.label(text="CSV Format: Time,Speed,YawRate")

        c.label(text="Select EDR Object:")
        c.prop(anim_settings, "edr_anim_object")
        c.prop(anim_settings, "edr_input_mode")

        # --- Inputs that depend on the selected mode ---
        if edr_mode == 'PATH_FOLLOW':
            path_box = l.box()
            path_box.label(text="Path Follow", icon='CURVE_PATH')
            path_box.label(text="Speed-Time data sets position along the path")
            path_box.prop(anim_settings, "edr_path_object")
            path_box.prop(anim_settings, "edr_path_align_orientation")
            if anim_settings.edr_path_align_orientation:
                path_box.prop(anim_settings, "edr_path_yaw_offset")
        else:
            needs_wheelbase = (edr_mode == 'STEERING_WHEEL_ANGLE') or anim_settings.edr_use_slip_estimate
            if needs_wheelbase:
                c.prop(anim_settings, "edr_wheelbase")

            if edr_mode == 'STEERING_WHEEL_ANGLE':
                c.prop(anim_settings, "edr_steering_gear_ratio")
                c.label(text="yaw_rate = speed / wheelbase * tan(steering_wheel_angle / steering_gear_ratio)")
                c.label(text="Tip: lower steering ratio increases computed yaw rate.", icon='INFO')

            c.prop(anim_settings, "edr_use_slip_estimate")
            if anim_settings.edr_use_slip_estimate:
                c.prop(anim_settings, "edr_slip_gain")
                c.prop(anim_settings, "edr_slip_max_deg")
                c.label(text="beta ≈ gain * atan(wheelbase * yaw_rate / speed)")
                c.label(text="Tip: start with small gain and increase gradually.", icon='INFO')
                if edr_mode == 'STEERING_WHEEL_ANGLE':
                    c.label(text="(yaw_rate is first estimated from steering)")

        c.label(text="Frame Rate:")
        c.prop(anim_settings, "anim_fps")  # Editable FPS field

        c.label(text=f"Unit System: {scene.unit_settings.system}")  # Show unit system
        c.separator()

        # --- Flexible CSV import: load a file, map columns, then import ---
        import_box = l.box()
        import_box.label(text="Import CSV (map columns)", icon='IMPORT')
        import_box.operator("object.load_edr_csv_headers", text="Load CSV File")
        if anim_settings.edr_csv_filepath:
            import_box.label(text=f"File: {os.path.basename(anim_settings.edr_csv_filepath)}")
            if not anim_settings.edr_csv_has_header:
                import_box.label(text="No header row detected - map columns below", icon='INFO')
            # Always expose every column so the mapping is ready if you switch
            # input methods later; unused columns are simply ignored per mode.
            import_box.prop(anim_settings, "edr_col_time")
            import_box.prop(anim_settings, "edr_col_speed")
            import_box.prop(anim_settings, "edr_col_yaw_rate")
            import_box.prop(anim_settings, "edr_col_steering")
            import_box.operator("object.import_edr_mapped_csv", text="Import Mapped Data")

        c.separator()

        # --- Animate using the chosen mode ---
        if edr_mode == 'PATH_FOLLOW':
            c.operator("object.animate_path_from_speed", text="Animate Along Path")
        else:
            c.operator("object.animate_vehicle", text="Animate Object")

        if target_obj:
            c.label(text=f"Entries for: {target_obj.name}")
            entries = target_obj.vehicle_path_entries
        else:
            c.label(text="No target object selected")
            entries = []

        for i, entry in enumerate(entries):
            row = c.row()
            row.prop(entry, "time", text="Time (s)")
            row.prop(entry, "speed", text="Speed")
            if edr_mode == 'STEERING_WHEEL_ANGLE':
                row.prop(entry, "steering_wheel_angle", text="Steering Wheel Angle (°)")
            elif edr_mode == 'YAW_RATE':
                row.prop(entry, "yaw_rate", text="Yaw Rate (°/s)")

        c.operator("object.add_path_entry", text="Add Entry")
        c.operator("object.remove_path_entry", text="Remove Last Entry")
        c.operator("object.remove_all_entries", text="Remove All Entries")


 
class HVE_PT_xyzrpy_importer(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Motion Data Importer"
    bl_parent_id = "HVE_PT_other_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        anim_settings = scene.anim_settings
        target_obj = anim_settings.motion_anim_object
        l = self.layout
        c = l.column()
        c.label(text="CSV Format: Time,X,Y,Z,Roll,Pitch,Yaw")
        c.label(text="Select Motion Object:")
        c.prop(anim_settings, "motion_anim_object")

        c.label(text="Frame Rate:")
        c.prop(anim_settings, "anim_fps")  # Editable FPS field
        c.label(text="Extrapolation Mode:")
        c.prop(anim_settings, "extrapolation_mode")  # 🔹 User selects extrapolation type

        c.label(text=f"Unit System: {scene.unit_settings.system}")  # Show unit system
        if target_obj:
            c.label(text=f"Stored rows for {target_obj.name}: {len(target_obj.motion_data_entries)}")
        else:
            c.label(text="No target object selected")

        # --- Load a CSV, map its columns, then import + animate ---
        c.separator()
        map_box = l.box()
        map_box.label(text="Import CSV (map columns)", icon='IMPORT')
        map_box.operator("import_anim.load_motion_csv_headers", text="Load CSV File")
        if anim_settings.motion_csv_filepath:
            map_box.label(text=f"File: {os.path.basename(anim_settings.motion_csv_filepath)}")
            if not anim_settings.motion_csv_has_header:
                map_box.label(text="No header row detected - map columns below", icon='INFO')
            map_box.prop(anim_settings, "motion_col_time")
            map_box.prop(anim_settings, "motion_col_x")
            map_box.prop(anim_settings, "motion_col_y")
            map_box.prop(anim_settings, "motion_col_z")
            map_box.prop(anim_settings, "motion_col_roll")
            map_box.prop(anim_settings, "motion_col_pitch")
            map_box.prop(anim_settings, "motion_col_yaw")
            map_box.operator("import_anim.import_mapped_motion_csv", text="Import and Animate", icon='IMPORT')
        
class HVE_PT_motion_paths(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Motion Path Tools"
    bl_parent_id = "HVE_PT_other_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()

        c.label(text="Motion Path Tools", icon="ANIM_DATA")  # Section title with an icon

        c.operator("object.generate_motion_path", text="Generate Motion Paths")
        c.operator("object.remove_motion_path", text="Remove Motion Paths")
        c.operator("object.convert_motion_path_selected", text="Convert Motion Paths To Curve")
        c.operator("object.toggle_motion_path_visibility", text="Show/Hide Motion Paths")


class HVE_PT_timed_location_markers(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Timed Location Markers"
    bl_parent_id = "HVE_PT_other_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()

        c.label(text="Timed Location Markers", icon="EMPTY_SINGLE_ARROW")
        c.prop(scene, "motion_marker_interval_seconds")
        c.prop(scene, "motion_marker_zero_frame")
        c.prop(scene, "motion_marker_size")
        c.prop(scene, "motion_marker_forward_axis")
        c.prop(scene, "motion_marker_yaw_offset")
        c.prop(scene, "motion_marker_create_time_labels")
        if scene.motion_marker_create_time_labels:
            c.prop(scene, "motion_marker_label_size")
        c.prop(scene, "motion_marker_replace_existing")
        c.operator("object.create_timed_location_markers", text="Create Location Markers")


class HVE_PT_scale_objects(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Scale Objects"
    bl_parent_id = "HVE_PT_other_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()
        
        unit_system = context.scene.unit_settings.system
        display_unit = "m" if unit_system == 'METRIC' else "ft" if unit_system == 'IMPERIAL' else "BU"
        
        c.label(text=f"Scene Units: {unit_system}")
        c.prop(context.scene, "scale_target_distance", text=f"Target Distance ({display_unit})")
        c.operator("object.scale_by_two_points", text="Scale Object")


class HVE_PT_speed_acceleration(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Speed + Acceleration"
    bl_parent_id = "HVE_PT_other_tools"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()

        c.label(text="Bake animated speed and acceleration", icon="FORCE_FORCE")

        if context.selected_objects:
            active = context.active_object
            source = (
                active
                if active in context.selected_objects
                else context.selected_objects[0]
            )
            c.label(text=f"Source: {source.name} (selected)", icon="OBJECT_DATA")
        else:
            c.label(text="No object selected; choose a source below", icon="INFO")
            c.prop(scene, "speed_accel_target_object")

        c.prop(scene, "speed_accel_forward_axis")
        c.prop(scene, "speed_accel_forward_yaw_offset")
        c.prop(scene, "speed_accel_window_frames")
        c.prop(scene, "speed_accel_unit_mode")
        c.prop(scene, "speed_accel_use_xy_only")
        c.prop(scene, "speed_accel_include_acceleration")
        c.prop(scene, "speed_accel_remove_old_curves")
        c.prop(scene, "speed_accel_parent_helper")
        c.operator("object.calculate_speed_acceleration", text="Calculate Speed + Acceleration")


class HVE_PT_point_importer(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Point Importer"
    bl_parent_id = "HVE_PT_other_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        anim_settings = scene.anim_settings
        l = self.layout
        c = l.column()

        c.label(text="Point Importer", icon="TOOL_SETTINGS")  # Section title with an icon
        c.label(text="CSV Format: PointNumber,X,Y,Z,Description")

        # --- Load a CSV, map its columns, then import ---
        map_box = l.box()
        map_box.label(text="Import CSV (map columns)", icon='IMPORT')
        map_box.operator("import_xyz.load_point_csv_headers", text="Load CSV File")
        if anim_settings.point_csv_filepath:
            map_box.label(text=f"File: {os.path.basename(anim_settings.point_csv_filepath)}")
            if not anim_settings.point_csv_has_header:
                map_box.label(text="No header row detected - map columns below", icon='INFO')
            map_box.prop(anim_settings, "point_col_number")
            map_box.prop(anim_settings, "point_col_x")
            map_box.prop(anim_settings, "point_col_y")
            map_box.prop(anim_settings, "point_col_z")
            map_box.prop(anim_settings, "point_col_description")
            map_box.prop(anim_settings, "point_scale_factor")
            map_box.operator("import_xyz.import_mapped_points", text="Import Points")


# Names the point-cloud display input may carry ("Subsample Percent" is the
# legacy name used by clouds imported before the rename to "Points Visible %").
_POINTS_VISIBLE_NAMES = {"Points Visible %", "Subsample Percent"}


def _geonodes_subsample_input(obj):
    """Return ``(modifier, socket_identifier)`` for a point cloud's GeoNodes
    points-visible display input, or None if the object doesn't have one."""
    if obj is None:
        return None
    for mod in obj.modifiers:
        if mod.type != 'NODES' or not mod.node_group:
            continue
        ng = mod.node_group
        iface = getattr(ng, "interface", None)
        if iface is not None and hasattr(iface, "items_tree"):
            for item in iface.items_tree:
                if (getattr(item, "in_out", "") == 'INPUT'
                        and getattr(item, "name", "") in _POINTS_VISIBLE_NAMES):
                    return mod, item.identifier
        else:  # Blender 3.x
            for inp in getattr(ng, "inputs", []):
                if inp.name in _POINTS_VISIBLE_NAMES:
                    return mod, inp.identifier
    return None


def _draw_cloud_source(layout, scene, context):
    """Draw the shared Point Cloud source selector (used by Filter / Ground / 3D).

    Returns the resolved source object (the pointer, or the active mesh) or None.
    """
    pc_obj = scene.roadway_source_object or (
        context.object if context.object and context.object.type == 'MESH' else None
    )
    if not scene.roadway_source_object:
        if pc_obj is not None:
            layout.label(text=f"Source: {pc_obj.name} (active)", icon="OBJECT_DATA")
        else:
            layout.label(text="Select a point cloud to begin", icon='ERROR')
    layout.prop(scene, "roadway_source_object")
    sub = _geonodes_subsample_input(pc_obj)
    if sub is not None:
        mod, ident = sub
        try:
            layout.prop(mod, '["%s"]' % ident, text="Points Visible %")
        except Exception:
            pass
    return pc_obj


def _draw_clip_options(layout, scene):
    """Draw the shared Clip To Object controls (used by Ground / 3D)."""
    layout.prop(scene, "roadway_clip_object")
    if getattr(scene, "roadway_clip_object", None) is not None:
        layout.prop(scene, "roadway_clip_mode")
        if scene.roadway_clip_mode == 'MESH':
            layout.label(text="Clips to the exact (closed) mesh volume", icon='INFO')
        else:
            layout.label(text="Box/cube clips in 3D; a plane clips its footprint", icon='INFO')


class HVE_PT_point_cloud_tools(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Point Cloud Tools"
    bl_parent_id = "HVE_PT_other_tools"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        self.layout.label(text="Import, filter, then create a ground or 3D surface", icon='INFO')


class HVE_PT_pc_import(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Import Point Cloud"
    bl_parent_id = "HVE_PT_point_cloud_tools"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        c = self.layout.column()
        c.label(text="PLY / PTX / E57 / LAS", icon='IMPORT')
        c.operator("import_scene.ply_pointcloud_geonodes", text="Import Point Cloud", icon='IMPORT')
        # Offer a one-click install for the optional E57 / LAZ packages, but only
        # when they're actually missing (keeps the panel clean once installed).
        try:
            from .ply_pointcloud import missing_optional_deps
            missing = missing_optional_deps()
        except Exception:
            missing = []
        if missing:
            fmts = ", ".join(fmt for _n, _s, fmt in missing)
            c.label(text=f"{fmts} auto-install on first open", icon='INFO')
            c.operator("import_scene.install_pointcloud_deps", text="Install E57 / LAZ Support Now", icon='PACKAGE')
        c.label(text="Imported cloud is selected automatically", icon='INFO')


class HVE_PT_pc_filter(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Filter Point Cloud"
    bl_parent_id = "HVE_PT_point_cloud_tools"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        c = self.layout.column()
        c.label(text="Clean a cloud (also runs before surfacing)", icon='FILTER')
        pc_obj = _draw_cloud_source(c, scene, context)

        c.prop(scene, "roadway_subsample")
        if scene.roadway_subsample:
            c.prop(scene, "roadway_voxel_size")
        c.prop(scene, "roadway_sor")
        if scene.roadway_sor:
            c.prop(scene, "roadway_sor_neighbors")
            c.prop(scene, "roadway_sor_ratio")

        run = c.column()
        run.enabled = pc_obj is not None and (scene.roadway_subsample or scene.roadway_sor)
        run.operator("object.filter_point_cloud", text="Filter → Create New Point Cloud", icon='DUPLICATE')
        c.label(text="Adds a new cloud; the original is never modified", icon='INFO')
        c.label(text="These filters also run when creating a surface", icon='INFO')


class HVE_PT_pc_ground(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Create Ground Surface"
    bl_parent_id = "HVE_PT_point_cloud_tools"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        c = self.layout.column()
        c.label(text="Drapes a ground grid onto the point cloud", icon='MESH_GRID')
        pc_obj = _draw_cloud_source(c, scene, context)
        _draw_clip_options(c, scene)

        c.prop(scene, "roadway_cell_size")
        c.prop(scene, "roadway_ground_percentile")
        c.prop(scene, "roadway_below_grade_tol")
        c.prop(scene, "roadway_fill_holes")
        if scene.roadway_fill_holes:
            c.prop(scene, "roadway_fill_distance")
        c.prop(scene, "roadway_color_height_tol")
        c.prop(scene, "roadway_texture_size")
        c.prop(scene, "roadway_texture_source_object")
        if not bpy.data.filepath:
            c.label(text="Save the .blend to write the texture JPG", icon='ERROR')

        c.label(text="Subsample / SOR from Filter also run here", icon='INFO')
        if pc_obj is None:
            c.label(text="Select a point cloud first", icon='ERROR')
        build = c.column()
        build.enabled = pc_obj is not None
        build.operator("object.create_roadway_surface", text="Create Ground Surface", icon='SURFACE_NSURFACE')

        # Rebake the texture of an existing surface at a new Texture Resolution
        # without regenerating the mesh. Enabled when a surface is selected.
        active = context.active_object
        if active is not None and active.get("roadway_surface"):
            c.separator()
            c.operator("object.rebake_roadway_texture", text="Rebake Texture (Selected Surface)", icon='TEXTURE')
            c.label(text="Uses Texture Resolution above; no mesh rebuild", icon='INFO')


class HVE_PT_surface_reconstruct(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Create 3D Surface"
    bl_parent_id = "HVE_PT_point_cloud_tools"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        c = self.layout.column()

        c.label(text="Full 3D mesh (Open3D) for vertical / overhanging geometry", icon='MESH_ICOSPHERE')
        pc_obj = _draw_cloud_source(c, scene, context)
        _draw_clip_options(c, scene)

        c.prop(scene, "roadway_recon_method")
        if scene.roadway_recon_method == 'POISSON':
            c.prop(scene, "roadway_recon_depth")
            c.prop(scene, "roadway_recon_density_trim")
        elif scene.roadway_recon_method == 'BPA':
            c.prop(scene, "roadway_recon_bpa_radius_mult")
            c.label(text="Raise to close holes in sparse areas", icon='INFO')
        elif scene.roadway_recon_method == 'ALPHA':
            c.prop(scene, "roadway_recon_alpha")
        c.prop(scene, "roadway_recon_normals_k")
        c.label(text="Subsample / SOR from Filter also run here", icon='INFO')

        if pc_obj is None:
            c.label(text="Select a point cloud first", icon='ERROR')
        recon = c.column()
        recon.enabled = pc_obj is not None
        recon.operator("object.reconstruct_surface_3d", text="Reconstruct 3D Surface", icon='MOD_REMESH')
        # Only mention the Open3D install while it's actually missing.
        try:
            import importlib.util
            open3d_missing = importlib.util.find_spec("open3d") is None
        except Exception:
            open3d_missing = False
        if open3d_missing:
            c.label(text="Open3D installs on first run (large; may need Blender restart)", icon='PACKAGE')
        c.label(text="For drivable ground, use Create Ground Surface instead", icon='INFO')

        # Bake the reconstructed surface's colour to a texture (unwraps + bakes),
        # so the colour exports to HVE. Shown when a coloured 3D surface is active.
        active = context.active_object
        if active is not None and active.get("surface_3d"):
            c.separator()
            c.label(text="Texture bake", icon='TEXTURE')
            c.prop(scene, "roadway_texture_size")
            c.operator("object.bake_surface_texture", text="Bake Texture (Selected 3D Surface)", icon='TEXTURE')
            c.label(text="Unwraps + bakes cloud colour to a JPG", icon='INFO')


class HVE_PT_race_render_exporter(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "RaceRender Converter"
    bl_parent_id = "HVE_PT_post"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()

        c.label(text="Convert HVE Variable Output to RaceRender CSV", icon="TOOL_SETTINGS")  # Section title with an icon
        c.operator("export_racerender.csv", text="Convert to RaceRender CSV", icon='EXPORT')


class HVE_PT_documentation(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Documentation"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        l = self.layout
        l.operator("hve.open_user_guide", text="Open User Guide", icon='HELP')
        l.label(text="Opens the offline guide in your browser.", icon='INFO')


classes = (
    HVE_PT_pre,
    HVE_PT_mechanist_setup,
    HVE_PT_mechanist_export,
    HVE_PT_post,
    HVE_PT_fbx_importer,
    HVE_PT_variableoutput_importer,
    HVE_PT_other_tools,
    HVE_PT_edr_importer,
    HVE_PT_xyzrpy_importer,
    HVE_PT_motion_paths,
    HVE_PT_timed_location_markers,
    HVE_PT_scale_objects,
    HVE_PT_speed_acceleration,
    HVE_PT_point_importer,
    HVE_PT_point_cloud_tools,
    HVE_PT_pc_import,
    HVE_PT_pc_filter,
    HVE_PT_pc_ground,
    HVE_PT_surface_reconstruct,
    HVE_PT_race_render_exporter,
    HVE_PT_documentation,
    HVE_OT_save_preset,
    HVE_OT_load_preset,
    HVETOOLS_OT_set_selected_hve_type,
    HVETOOLS_OT_copy_surface_to_selected,
    HVE_OT_open_user_guide,

    )


def register():
    # Sync UI FPS with scene FPS when scene FPS changes
    bpy.app.handlers.depsgraph_update_post.append(sync_fps_with_scene)
    
def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(sync_fps_with_scene)
