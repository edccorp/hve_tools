bl_info = {
    "name": "HVE Menu",
    "author": "EDC",
    "version": (2, 0),
    "blender": (4, 0, 0),
    "description": "Tools for HVE",
    'warning': '',
    "category": "HVE",
}

try:
    import bpy
    from . import (
        materials, props, ui, prefs, debug, ops, mechanist,
        export_vehicle, export_vehicle_ui,
        export_environment, export_environment_ui,
        variableoutput_importer, variableoutput_importer_ui,
        contacts_exporter, contacts_exporter_ui,
        racerender_exporter, racerender_exporter_ui,
        fbx_importer, fbx_importer_ui,
        motionpaths, xyz_importer, xyz_importer_ui,

        edr_importer, scale_objects, import_xyzrpy, ortho_projector,

    )

    from bpy.props import *
    from bpy_extras.io_utils import ImportHelper
    from bpy.types import Panel, PropertyGroup, Scene, WindowManager
    from bpy.props import (
        IntProperty,
        EnumProperty,
        StringProperty,
        PointerProperty,
        FloatProperty,
    )

    props.register()

    modules = [
        ui, materials, prefs, ops, export_vehicle_ui, export_environment_ui,
        contacts_exporter_ui, variableoutput_importer_ui, racerender_exporter_ui,
        fbx_importer_ui, motionpaths, xyz_importer_ui, edr_importer, scale_objects,
        import_xyzrpy, ortho_projector,
    ]

    # Aggregate all classes from modules
    classes = [cls for module in modules for cls in module.classes]

    def register():
        from .edr_importer import VehiclePathEntry  # Ensure correct module
        bpy.utils.register_class(VehiclePathEntry)  # Register VehiclePathEntry FIRST

        for cls in classes:
            bpy.utils.register_class(cls)

        # Ensure anim_settings is registered before UI accesses it
        if not hasattr(bpy.types.Scene, "anim_settings"):
            bpy.types.Scene.anim_settings = PointerProperty(type=props.AnimationSettings)

        bpy.types.Scene.scale_target_distance = bpy.props.FloatProperty(
            name="Target Distance",
            description="Distance to scale the object to, based on scene units",
            default=1.0,
            min=0.001,
        )

        bpy.types.Object.vehicle_path_entries = CollectionProperty(type=edr_importer.VehiclePathEntry)
        bpy.types.Object.motion_data_entries = CollectionProperty(type=import_xyzrpy.MotionDataEntry)

        ui.update_panel_bl_category(None, bpy.context)

    def unregister():
        del bpy.types.Scene.scale_target_distance
        del bpy.types.Object.motion_data_entries
        del bpy.types.Object.vehicle_path_entries
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)

except ModuleNotFoundError:
    bpy = None
    modules = []
    classes = []

    # When running tests or outside Blender, provide no-op register/unregister
    def register():
        """Placeholder register function when bpy is unavailable."""
        pass

    def unregister():
        """Placeholder unregister function when bpy is unavailable."""
        pass

if __name__ == "__main__":
    register()

print("HVE Tools successfully (re)loaded")
