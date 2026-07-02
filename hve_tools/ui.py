import os
import json
import bpy
import re
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


def update_panel_bl_category(self, context):
    main_panels = (HVE_PT_pre, HVE_PT_post, HVE_PT_documentation)
    sub_panels = (
        HVE_PT_mechanist_setup,
        HVE_PT_mechanist_export,
        HVE_PT_fbx_importer,
        HVE_PT_variableoutput_importer,
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
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
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

class HVE_PT_race_render_exporter(HVE_PT_mechanist_base):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HVE"
    bl_label = "RaceRender Converter"
    bl_parent_id = "HVE_PT_post"    
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
    HVE_PT_race_render_exporter,
    HVE_PT_documentation,
    HVE_OT_save_preset,
    HVE_OT_load_preset,
    HVETOOLS_OT_set_selected_hve_type,
    HVETOOLS_OT_copy_surface_to_selected,
    HVE_OT_open_user_guide,
)


def register():
    pass

def unregister():
    pass
