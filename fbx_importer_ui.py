
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
import sys
import time
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper


def open_system_console():
    """Open the Blender system console on Windows if not already visible."""
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            visible = ctypes.windll.user32.IsWindowVisible(hwnd)
            if not visible:
                bpy.ops.wm.console_toggle()
        except Exception:
            pass


def get_hve_vehicle_names():
    """Return vehicle names from all HVE FBX collections currently in the scene."""
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


def is_body_mesh_collection(self, collection):
    """PointerProperty filter: only offer HVE body mesh collections in the picker."""
    return collection.name.startswith("Body Mesh: ")


def get_target_vehicle_names(context):
    """Vehicle names the post-process operators should act on.

    If the user picked a specific Body Mesh collection in the panel, restrict to
    that collection's vehicle; otherwise fall back to every imported vehicle.
    """
    chosen = getattr(context.scene, "fbx_process_collection", None)
    if chosen is not None and chosen.name.startswith("Body Mesh: "):
        parts = chosen.name.split(": ")
        if len(parts) >= 2:
            return [parts[1]]
    return get_hve_vehicle_names()


def iter_body_mesh_objects(vehicle_names):
    """Yield every MESH object in the ``Body Mesh:`` collections of the given vehicles."""
    for col in bpy.data.collections:
        if not col.name.startswith("Body Mesh: "):
            continue
        parts = col.name.split(": ")
        if len(parts) >= 2 and parts[1] in vehicle_names:
            for obj in col.objects:
                if obj.type == 'MESH':
                    yield obj


def reduce_shape_keys_for_vehicles(vehicle_names, max_samples):
    """Adaptively reduce shape keys; ``max_samples`` of 0 means no hard cap."""
    from . import fbx_importer
    fbx_importer.reduce_shape_key_meshes_with_adaptive_samples(
        vehicle_names,
        max_samples=max_samples if max_samples > 0 else None,
    )


def merge_body_meshes_for_vehicles(vehicle_names):
    """Join each vehicle's body mesh parts into a single object."""
    from . import fbx_importer
    all_objects = list(bpy.context.scene.objects)
    pointer_set = {obj.as_pointer() for obj in all_objects}
    fbx_importer.join_mesh_objects_per_vehicle(vehicle_names, all_objects, pointer_set)


def apply_mesh_cleanup_to_vehicles(vehicle_names):
    """Add merge-by-distance and smooth-by-angle modifiers to body meshes; return the count."""
    from . import fbx_importer
    count = 0
    for obj in iter_body_mesh_objects(vehicle_names):
        fbx_importer.add_merge_by_distance_modifier(obj)
        fbx_importer.add_smooth_by_angle_modifier(obj)
        count += 1
    return count


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
        open_system_console()
        return fbx_importer.load(context, self.filepath, operator=self)

    def draw(self, context):
        pass


class FBX_OT_merge_body_mesh(bpy.types.Operator):
    """Join each vehicle's body mesh parts into a single object"""
    bl_idname = "import_hve.merge_body_mesh"
    bl_label = "Merge Body Meshes"
    bl_description = "Join each vehicle's body mesh parts into a single object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        vehicle_names = get_target_vehicle_names(context)
        if not vehicle_names:
            self.report({'WARNING'}, "No HVE body mesh collections found")
            return {'CANCELLED'}
        open_system_console()
        print(f"🔧 Merging body meshes for: {', '.join(vehicle_names)}")
        t = time.perf_counter()
        merge_body_meshes_for_vehicles(vehicle_names)
        print(f"✅ Merge body meshes done ({time.perf_counter() - t:.2f}s)")
        return {'FINISHED'}


class FBX_OT_reduce_shape_keys(bpy.types.Operator):
    """Adaptively reduce per-frame shape keys to the minimum needed to represent the deformation"""
    bl_idname = "import_hve.reduce_shape_keys"
    bl_label = "Reduce Shape Keys"
    bl_description = "Adaptively reduce per-frame shape keys to the minimum needed to represent the deformation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        vehicle_names = get_target_vehicle_names(context)
        if not vehicle_names:
            self.report({'WARNING'}, "No HVE body mesh collections found")
            return {'CANCELLED'}
        open_system_console()
        max_samples = context.scene.fbx_shape_key_max_samples
        print(f"🔧 Reducing shape keys for: {', '.join(vehicle_names)} (max samples: {max_samples if max_samples > 0 else 'unlimited'})")
        t = time.perf_counter()
        reduce_shape_keys_for_vehicles(vehicle_names, max_samples)
        print(f"✅ Reduce shape keys done ({time.perf_counter() - t:.2f}s)")
        return {'FINISHED'}




class FBX_OT_apply_mesh_cleanup(bpy.types.Operator):
    """Add Merge by Distance and Smooth by Angle geometry node modifiers to body mesh objects"""
    bl_idname = "import_hve.apply_mesh_cleanup"
    bl_label = "Apply Mesh Cleanup"
    bl_description = "Add Merge by Distance and Smooth by Angle geometry node modifiers to body mesh objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        vehicle_names = get_target_vehicle_names(context)
        if not vehicle_names:
            self.report({'WARNING'}, "No HVE body mesh collections found")
            return {'CANCELLED'}
        open_system_console()
        print(f"🔧 Applying mesh cleanup (merge verts + smooth by angle) for: {', '.join(vehicle_names)}")
        t = time.perf_counter()
        count = apply_mesh_cleanup_to_vehicles(vehicle_names)
        print(f"✅ Mesh cleanup applied to {count} object(s) ({time.perf_counter() - t:.2f}s)")
        return {'FINISHED'}


class FBX_OT_process_all(bpy.types.Operator):
    """Run all post-process steps: Reduce Shape Keys, Merge Body Meshes, then Merge Verts + Smooth by Angle"""
    bl_idname = "import_hve.process_all"
    bl_label = "Process All"
    bl_description = "Run all post-process steps in order: Reduce Shape Keys → Merge Body Meshes → Merge Verts + Smooth by Angle"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        vehicle_names = get_target_vehicle_names(context)
        if not vehicle_names:
            self.report({'WARNING'}, "No HVE body mesh collections found")
            return {'CANCELLED'}
        open_system_console()
        t_total = time.perf_counter()

        # Step 1: Reduce shape keys
        max_samples = context.scene.fbx_shape_key_max_samples
        print(f"🔧 [1/3] Reducing shape keys for: {', '.join(vehicle_names)} (max samples: {max_samples if max_samples > 0 else 'unlimited'})")
        t = time.perf_counter()
        reduce_shape_keys_for_vehicles(vehicle_names, max_samples)
        print(f"✅ [1/3] Reduce shape keys done ({time.perf_counter() - t:.2f}s)")

        # Step 2: Merge body meshes
        print(f"🔧 [2/3] Merging body meshes for: {', '.join(vehicle_names)}")
        t = time.perf_counter()
        merge_body_meshes_for_vehicles(vehicle_names)
        print(f"✅ [2/3] Merge body meshes done ({time.perf_counter() - t:.2f}s)")

        # Step 3: Mesh cleanup
        print(f"🔧 [3/3] Applying mesh cleanup for: {', '.join(vehicle_names)}")
        t = time.perf_counter()
        count = apply_mesh_cleanup_to_vehicles(vehicle_names)
        print(f"✅ [3/3] Mesh cleanup applied to {count} object(s) ({time.perf_counter() - t:.2f}s)")

        print(f"🎉 All post-process steps complete ({time.perf_counter() - t_total:.2f}s total)")
        return {'FINISHED'}


def menu_func_export(self, context):
    self.layout.operator(ImportFBX.bl_idname, text="FBX (.fbx)")


classes = (
    ImportFBX,
    FBX_OT_process_all,
    FBX_PT_fbx_importer_include,
    FBX_OT_merge_body_mesh,
    FBX_OT_reduce_shape_keys,
    FBX_OT_apply_mesh_cleanup,
)
