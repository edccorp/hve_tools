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
    main_panels = (HVE_PT_pre, HVE_PT_post, HVE_PT_other_tools)
    sub_panels = (
        HVE_PT_mechanist_setup,
        HVE_PT_mechanist_export,
        HVE_PT_contacts_exporter,
        HVE_PT_fbx_importer,
        HVE_PT_variableoutput_importer,
        HVE_PT_edr_importer,
        HVE_PT_xyzrpy_importer,

        HVE_PT_point_importer,
        HVE_PT_motion_paths,
        HVE_PT_scale_objects,
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
        col.label(text="Use h3d Setup, then run h3d Export.")

class HVE_PT_mechanist_export(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "H3D Export"
    bl_parent_id = "HVE_PT_pre"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        o = context.active_object
        if o is None:
            self.layout.label(text='Select an object..', icon='ERROR')
            return

        l = self.layout
        # Check if the object has hve_type property and toggle buttons accordingly
        if hasattr(o, "hve_type") and hasattr(o.hve_type, "set_type"):
            obj_type = o.hve_type.set_type.type

            if obj_type == "VEHICLE":
                l.operator("export_vehicle.h3d", text="Export Vehicle", icon='EXPORT')
            elif obj_type == "ENVIRONMENT":
                l.operator("export_environment.h3d", text="Export Environment", icon='EXPORT')
            else:
                l.label(text="Invalid HVE Type", icon='ERROR')
                l.label(text="Set HVE Type in H3D Setup.", icon='INFO')
        else:
            l.label(text="HVE Type not set", icon='ERROR')
            l.label(text="Open H3D Setup and choose Vehicle or Environment.", icon='INFO')



class HVE_PT_mechanist_setup(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "H3D Setup"
    bl_parent_id = "HVE_PT_pre"
    
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
            c, scene, "hve_setup_show_materials", "Materials", icon='MATERIAL'
        )
        if materials_box:
            materials_box.operator("hve_material.add_hve_material", text="Add HVE Material")
            materials_box.separator()
            materials_box.operator("hve_material.add_standard_materials", text="Add Standard Materials")
            materials_box.separator()
            materials_box.operator("hve_material.add_hve_light_materials", text="Add HVE Light Materials")

        c.separator()
        object_type_box = self.draw_collapsible_panel(
            c, scene, "hve_setup_show_object_type", "Object Type", icon='OUTLINER_OB_EMPTY'
        )
        if object_type_box:
            object_type_box.prop(types.set_type, 'type')

        enum_value = getattr(getattr(types, "set_type", None), "type", None)
        if enum_value == "VEHICLE":
            c.separator()
            vehicle_lighting_box = self.draw_collapsible_panel(
                c, scene, "hve_setup_show_vehicle_lighting", "Vehicle Lighting", icon='LIGHT'
            )
            if vehicle_lighting_box:
                vehicle_lighting_box.prop(lights.make_light, 'type')
        elif enum_value == "ENVIRONMENT":
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

class HVE_PT_contacts_exporter(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "GATB Surface Points Exporter"
    bl_parent_id = "HVE_PT_pre"
    @classmethod
    def poll(cls, context):
        return True
        
    def draw(self, context):
        o = context.active_object
        if o is None:
            self.layout.label(text='Select an object..', icon='ERROR')
            return
        scene = context.scene
        l = self.layout
        c = l.column()
        

        # Contacts Exporter controls
        l.operator("export_contacts.csv", text="Export Contact Surfaces", icon='EXPORT')

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
    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        target_obj = scene.anim_settings.anim_object
        l = self.layout
        c = l.column()


        # Contacts Exporter controls
        l.operator("import_hve.fbx", text="Import FBX", icon='IMPORT')

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
        if edr_mode == 'STEERING_WHEEL_ANGLE':
            c.label(text="CSV Format: Time,Speed,SteeringWheelAngle")
        else:
            c.label(text="CSV Format: Time,Speed,YawRate")
        c.label(text="Select EDR Object:")
        c.prop(scene.anim_settings, "edr_anim_object")
        c.prop(scene.anim_settings, "edr_input_mode")

        needs_wheelbase = (edr_mode == 'STEERING_WHEEL_ANGLE') or scene.anim_settings.edr_use_slip_estimate
        if needs_wheelbase:
            c.prop(scene.anim_settings, "edr_wheelbase")

        if edr_mode == 'STEERING_WHEEL_ANGLE':
            c.prop(scene.anim_settings, "edr_steering_gear_ratio")
            c.label(text="yaw_rate = speed / wheelbase * tan(steering_wheel_angle / steering_gear_ratio)")
            c.label(text="Tip: lower steering ratio increases computed yaw rate.", icon='INFO')

        c.prop(scene.anim_settings, "edr_use_slip_estimate")
        if scene.anim_settings.edr_use_slip_estimate:
            c.prop(scene.anim_settings, "edr_slip_gain")
            c.prop(scene.anim_settings, "edr_slip_max_deg")
            c.label(text="beta ≈ gain * atan(wheelbase * yaw_rate / speed)")
            c.label(text="Tip: start with small gain and increase gradually.", icon='INFO')
            if edr_mode == 'STEERING_WHEEL_ANGLE':
                c.label(text="(yaw_rate is first estimated from steering)")

        c.label(text="Frame Rate:")
        c.prop(scene.anim_settings, "anim_fps")  # Editable FPS field

        c.label(text=f"Unit System: {scene.unit_settings.system}")  # Show unit system
        c.separator()
        c.operator("object.import_csv", text="Import CSV")
        c.separator()
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
            else:
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
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        target_obj = scene.anim_settings.motion_anim_object
        l = self.layout
        c = l.column()
        c.label(text="CSV Format: Time,X,Y,Z,Roll,Pitch,Yaw")
        c.label(text="Select Motion Object:")
        c.prop(scene.anim_settings, "motion_anim_object")

        c.label(text="Frame Rate:")
        c.prop(scene.anim_settings, "anim_fps")  # Editable FPS field
        c.label(text="Extrapolation Mode:")
        c.prop(scene.anim_settings, "extrapolation_mode")  # 🔹 User selects extrapolation type

        c.label(text=f"Unit System: {scene.unit_settings.system}")  # Show unit system
        if target_obj:
            c.label(text=f"Stored rows for {target_obj.name}: {len(target_obj.motion_data_entries)}")
        else:
            c.label(text="No target object selected")
        c.operator("import_anim.csv", text="Import and Animate Object", icon='IMPORT')
        
class HVE_PT_motion_paths(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Motion Path Tools"
    bl_parent_id = "HVE_PT_other_tools"
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
 
 
class HVE_PT_scale_objects(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Scale Objects"
    bl_parent_id = "HVE_PT_other_tools"
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


class HVE_PT_point_importer(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Point Importer"
    bl_parent_id = "HVE_PT_other_tools"
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()

        c.label(text="Point Importer", icon="TOOL_SETTINGS")  # Section title with an icon
        c.label(text="CSV Format: PointNumber,X, Y, Z, Description")        
        c.operator("import_xyz.csv", text="Import Points")


class HVE_PT_race_render_exporter(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "Export HVE Variable Output to RaceRender"
    bl_parent_id = "HVE_PT_post"    
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()

        c.label(text="Export CSV for RaceRender", icon="TOOL_SETTINGS")  # Section title with an icon
        c.operator("export_racerender.csv", text="Export RaceRender CSV", icon='EXPORT')


classes = (
    HVE_PT_pre,
    HVE_PT_mechanist_setup,
    HVE_PT_mechanist_export,
    HVE_PT_contacts_exporter,
    HVE_PT_post,
    HVE_PT_fbx_importer,
    HVE_PT_variableoutput_importer,
    HVE_PT_other_tools,
    HVE_PT_edr_importer,
    HVE_PT_xyzrpy_importer,
    HVE_PT_motion_paths,
    HVE_PT_scale_objects,
    HVE_PT_point_importer,
    HVE_PT_race_render_exporter,
    HVE_OT_save_preset,
    HVE_OT_load_preset, 
    HVETOOLS_OT_copy_surface_to_selected,
    
    )


def register():
    # Sync UI FPS with scene FPS when scene FPS changes
    bpy.app.handlers.depsgraph_update_post.append(sync_fps_with_scene)
    
def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(sync_fps_with_scene)
