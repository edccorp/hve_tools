bl_info = {
    "name": "HVE Menu",
    "author": "Engnineering Dynamics Company : Anthony Cornetto",
    "version": (2, 1),
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

    modules = [
        ui, materials, prefs, ops, export_vehicle_ui, export_environment_ui,
        contacts_exporter_ui, variableoutput_importer_ui, racerender_exporter_ui,
        fbx_importer_ui, motionpaths, xyz_importer_ui, edr_importer, scale_objects,
        import_xyzrpy, ortho_projector,
    ]

    # Aggregate all classes from modules
    classes = [cls for module in modules for cls in module.classes]

    def _register_class_once(cls):
        if not bpy.utils.is_registered_class(cls):
            bpy.utils.register_class(cls)

    def _unregister_class_if_registered(cls):
        if bpy.utils.is_registered_class(cls):
            bpy.utils.unregister_class(cls)

    def register():
        props.register()

        from .edr_importer import VehiclePathEntry  # Ensure correct module
        _register_class_once(VehiclePathEntry)  # Register VehiclePathEntry FIRST

        for cls in classes:
            _register_class_once(cls)

        # Ensure anim_settings is registered before UI accesses it
        if not hasattr(bpy.types.Scene, "anim_settings"):
            bpy.types.Scene.anim_settings = PointerProperty(type=props.AnimationSettings)

        bpy.types.Scene.scale_target_distance = bpy.props.FloatProperty(
            name="Target Distance",
            description="Distance to scale the object to, based on scene units",
            default=1.0,
            min=0.001,
        )
        bpy.types.Scene.hve_setup_show_surface = bpy.props.BoolProperty(
            name="Show Surface",
            default=True,
        )
        bpy.types.Scene.hve_setup_show_materials = bpy.props.BoolProperty(
            name="Show Materials",
            default=True,
        )
        bpy.types.Scene.hve_setup_show_object_type = bpy.props.BoolProperty(
            name="Show Object Type",
            default=True,
        )
        bpy.types.Scene.hve_setup_show_terrain = bpy.props.BoolProperty(
            name="Show Terrain Properties",
            default=True,
        )
        bpy.types.Scene.hve_setup_show_vehicle_lighting = bpy.props.BoolProperty(
            name="Show Vehicle Lighting",
            default=True,
        )
        bpy.types.Scene.hve_setup_show_forces = bpy.props.BoolProperty(
            name="Show Forces",
            default=True,
        )
        bpy.types.Scene.hve_setup_show_soil = bpy.props.BoolProperty(
            name="Show Soil",
            default=True,
        )
        bpy.types.Scene.hve_setup_show_water = bpy.props.BoolProperty(
            name="Show Water",
            default=True,
        )

        bpy.types.Object.vehicle_path_entries = CollectionProperty(type=edr_importer.VehiclePathEntry)
        bpy.types.Object.motion_data_entries = CollectionProperty(type=import_xyzrpy.MotionDataEntry)
        bpy.types.Object.edr_input_mode_preference = EnumProperty(
            name="EDR Input Mode Preference",
            description="Stores which EDR input mode this object uses",
            items=props.AnimationSettings.EDR_INPUT_MODE_ITEMS,
            default='YAW_RATE',
        )

        ui.update_panel_bl_category(None, bpy.context)

    def unregister():
        from .edr_importer import VehiclePathEntry

        if hasattr(bpy.types.Scene, "scale_target_distance"):
            del bpy.types.Scene.scale_target_distance
        if hasattr(bpy.types.Scene, "hve_setup_show_surface"):
            del bpy.types.Scene.hve_setup_show_surface
        if hasattr(bpy.types.Scene, "hve_setup_show_materials"):
            del bpy.types.Scene.hve_setup_show_materials
        if hasattr(bpy.types.Scene, "hve_setup_show_object_type"):
            del bpy.types.Scene.hve_setup_show_object_type
        if hasattr(bpy.types.Scene, "hve_setup_show_terrain"):
            del bpy.types.Scene.hve_setup_show_terrain
        if hasattr(bpy.types.Scene, "hve_setup_show_vehicle_lighting"):
            del bpy.types.Scene.hve_setup_show_vehicle_lighting
        if hasattr(bpy.types.Scene, "hve_setup_show_forces"):
            del bpy.types.Scene.hve_setup_show_forces
        if hasattr(bpy.types.Scene, "hve_setup_show_soil"):
            del bpy.types.Scene.hve_setup_show_soil
        if hasattr(bpy.types.Scene, "hve_setup_show_water"):
            del bpy.types.Scene.hve_setup_show_water
        if hasattr(bpy.types.Object, "edr_input_mode_preference"):
            del bpy.types.Object.edr_input_mode_preference
        if hasattr(bpy.types.Object, "motion_data_entries"):
            del bpy.types.Object.motion_data_entries
        if hasattr(bpy.types.Object, "vehicle_path_entries"):
            del bpy.types.Object.vehicle_path_entries
        for cls in reversed(classes):
            _unregister_class_if_registered(cls)
        _unregister_class_if_registered(VehiclePathEntry)
        props.unregister()

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
