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
    from . import ortho_projector

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
        ortho_projector.HVE_PT_ortho_projector,
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
        l.label(text="")

class HVE_PT_mechanist_export(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "h3d Export"
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
        else:
            l.label(text="HVE Type not set", icon='ERROR')



class HVE_PT_mechanist_setup(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "h3d Setup"
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
        c.operator("hve_material.add_hve_material")

        c.separator()
        c.operator("hve_material.add_standard_materials")

        c.separator()
        c.operator("hve_material.add_hve_light_materials")

        c.separator()

        c.label(text="HVE Type")
        c.prop(types.set_type, 'type')

        if "hve_type" in o:
            enum_value = o.hve_type.set_type.type
            if enum_value == "VEHICLE":
                c.separator()
                c.label(text="HVE Light")
                c.prop(lights.make_light, 'type')
            elif enum_value == "ENVIRONMENT":
                c.separator()
                c.label(text="HVE Terrain Properties")
                l.prop(env_props.set_env_props, "poSurfaceType")
                l.prop(env_props.set_env_props, "polabel")
                l.prop(env_props.set_env_props, "poName")
                l.prop(env_props.set_env_props, "poFriction")
                l.prop(env_props.set_env_props, "poRateDamping")
                l.prop(env_props.set_env_props, "poForceConst")
                l.prop(env_props.set_env_props, "poForceLinear")
                l.prop(env_props.set_env_props, "poForceQuad")
                l.prop(env_props.set_env_props, "poForceCubic")
                l.prop(env_props.set_env_props, "poForceUnload")
                l.prop(env_props.set_env_props, "poBekkerConst")
                l.prop(env_props.set_env_props, "poKphi")
                l.prop(env_props.set_env_props, "poKc")
                l.prop(env_props.set_env_props, "poPcntMoisture")
                l.prop(env_props.set_env_props, "poPcntClay")
                l.prop(env_props.set_env_props, "poWaterDepth")
                l.prop(env_props.set_env_props, "poStaticWater")
       
                l.separator()

                # Save / Load Buttons
                row = l.row()
                row.operator("hve.save_preset", text="Save Preset", icon="EXPORT")
                row.operator("hve.load_preset", text="Load Preset", icon="IMPORT")

                l.separator()

                # Preset Dropdown
                l.prop(context.scene, "hve_preset", text="Apply Preset")

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
        l.label(text="")
        


class HVE_PT_variableoutput_importer(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "HVE Motion and Variable Output Importer"
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
        l.operator("import_variables.csv", text="Import Variable Output", icon='IMPORT')
        
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
        l.label(text="")

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

        c.prop(scene.anim_settings, "edr_use_slip_estimate")
        if scene.anim_settings.edr_use_slip_estimate:
            c.prop(scene.anim_settings, "edr_slip_gain")
            c.prop(scene.anim_settings, "edr_slip_max_deg")
            if edr_mode == 'YAW_RATE':
                c.label(text="beta ≈ gain * atan(wheelbase * yaw_rate / speed)")
            else:
                c.label(text="beta ≈ gain * (steering_wheel_angle / steering_gear_ratio)")

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

        c.label(text="Export csv for RaceRender", icon="TOOL_SETTINGS")  # Section title with an icon
        c.operator("export_racerender.csv", text="Export RaceRender", icon='EXPORT')


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

    
    )


def register():
    # Sync UI FPS with scene FPS when scene FPS changes
    bpy.app.handlers.depsgraph_update_post.append(sync_fps_with_scene)
    
def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(sync_fps_with_scene)
