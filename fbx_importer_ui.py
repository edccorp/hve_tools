
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
import tempfile
import time
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper


def get_hve_vehicle_names():
    """Return vehicle names from all HVE FBX collections currently in the scene."""
    from . import fbx_importer
    names = []
    for col in bpy.data.collections:
        if col.name.startswith("Body Mesh: "):
            # "Body Mesh: Toyota: SideFlip: FBX" -> vehicle name is "Toyota"
            parts = col.name.split(": ")
            if len(parts) >= 2:
                name = parts[1]
                if name not in names:
                    names.append(name)
    return names


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
        layout.label(text="Import and rename HVE FBX")


class ImportFBX(bpy.types.Operator, ExportHelper):
    """Import motion FBX from HVE"""
    bl_idname = "import_hve.fbx"
    bl_label = 'Import FBX from HVE'
    bl_options = {'PRESET'}

    filename_ext = ".fbx"

    filter_glob: StringProperty(
            default="*.fbx",
            options={'HIDDEN'},
            maxlen=255,
            )

    def execute(self, context):
        from . import fbx_importer
        return fbx_importer.load(context, self.filepath)

    def draw(self, context):
        pass


class FBX_OT_merge_body_mesh(bpy.types.Operator):
    """Join each vehicle's body mesh parts into a single object"""
    bl_idname = "import_hve.merge_body_mesh"
    bl_label = "Merge Body Meshes"
    bl_description = "Join each vehicle's body mesh parts into a single object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import fbx_importer
        vehicle_names = get_hve_vehicle_names()
        if not vehicle_names:
            self.report({'WARNING'}, "No HVE body mesh collections found")
            return {'CANCELLED'}
        print(f"🔧 Merging body meshes for: {', '.join(vehicle_names)}")
        t = time.perf_counter()
        all_objects = list(bpy.context.scene.objects)
        pointer_set = {obj.as_pointer() for obj in bpy.context.scene.objects}
        fbx_importer.join_mesh_objects_per_vehicle(vehicle_names, all_objects, pointer_set)
        print(f"✅ Merge body meshes done ({time.perf_counter() - t:.2f}s)")
        return {'FINISHED'}


class FBX_OT_reduce_shape_keys(bpy.types.Operator):
    """Adaptively reduce per-frame shape keys to the minimum needed to represent the deformation"""
    bl_idname = "import_hve.reduce_shape_keys"
    bl_label = "Reduce Shape Keys"
    bl_description = "Adaptively reduce per-frame shape keys to the minimum needed to represent the deformation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import fbx_importer
        vehicle_names = get_hve_vehicle_names()
        if not vehicle_names:
            self.report({'WARNING'}, "No HVE body mesh collections found")
            return {'CANCELLED'}
        max_samples = context.scene.fbx_shape_key_max_samples
        print(f"🔧 Reducing shape keys for: {', '.join(vehicle_names)} (max samples: {max_samples if max_samples > 0 else 'unlimited'})")
        t = time.perf_counter()
        fbx_importer.reduce_shape_key_meshes_with_adaptive_samples(
            vehicle_names,
            max_samples=max_samples if max_samples > 0 else None,
        )
        print(f"✅ Reduce shape keys done ({time.perf_counter() - t:.2f}s)")
        return {'FINISHED'}


class FBX_OT_bake_to_mdd(bpy.types.Operator):
    """Export body mesh shape key animation to external .mdd point-cache files and replace with Mesh Cache modifiers"""
    bl_idname = "import_hve.bake_to_mdd"
    bl_label = "Bake Shape Keys to MDD"
    bl_description = "Export body mesh shape key animation to external .mdd point-cache files and replace with Mesh Cache modifiers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import fbx_importer
        vehicle_names = get_hve_vehicle_names()
        if not vehicle_names:
            self.report({'WARNING'}, "No HVE body mesh collections found")
            return {'CANCELLED'}
        print(f"🔧 Baking shape keys to MDD for: {', '.join(vehicle_names)}")
        t = time.perf_counter()
        all_objects = list(bpy.context.scene.objects)
        pointer_set = {obj.as_pointer() for obj in bpy.context.scene.objects}
        fbx_importer.export_body_shape_key_animations_to_mdd(
            vehicle_names,
            bpy.data.filepath or tempfile.gettempdir(),
            all_objects,
            pointer_set,
        )
        print(f"✅ Bake to MDD done ({time.perf_counter() - t:.2f}s)")
        return {'FINISHED'}



class FBX_OT_apply_mesh_cleanup(bpy.types.Operator):
    """Add Merge by Distance and Smooth by Angle geometry node modifiers to body mesh objects"""
    bl_idname = "import_hve.apply_mesh_cleanup"
    bl_label = "Apply Mesh Cleanup"
    bl_description = "Add Merge by Distance and Smooth by Angle geometry node modifiers to body mesh objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import fbx_importer
        vehicle_names = get_hve_vehicle_names()
        if not vehicle_names:
            self.report({'WARNING'}, "No HVE body mesh collections found")
            return {'CANCELLED'}
        print(f"🔧 Applying mesh cleanup (merge verts + smooth by angle) for: {', '.join(vehicle_names)}")
        t = time.perf_counter()
        count = 0
        for col in bpy.data.collections:
            if col.name.startswith("Body Mesh: "):
                parts = col.name.split(": ")
                if len(parts) >= 2 and parts[1] in vehicle_names:
                    for obj in col.objects:
                        if obj.type == 'MESH':
                            fbx_importer.add_merge_by_distance_modifier(obj)
                            fbx_importer.add_smooth_by_angle_modifier(obj)
                            count += 1
        print(f"✅ Mesh cleanup applied to {count} object(s) ({time.perf_counter() - t:.2f}s)")
        return {'FINISHED'}


def menu_func_export(self, context):
    self.layout.operator(ImportFBX.bl_idname, text="FBX (.fbx)")


classes = (
    ImportFBX,
    FBX_PT_fbx_importer_include,
    FBX_OT_merge_body_mesh,
    FBX_OT_reduce_shape_keys,
    FBX_OT_bake_to_mdd,
    FBX_OT_apply_mesh_cleanup,
)
