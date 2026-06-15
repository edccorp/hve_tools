bl_info = {
    "name": "HVE Menu",
    "author": "Engnineering Dynamics Company : Anthony Cornetto",
    "version": (2, 5),
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
        edr_importer, scale_objects, speed_accel, import_xyzrpy,

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
        import_xyzrpy, speed_accel,
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
        bpy.types.Scene.speed_accel_target_object = PointerProperty(
            name="Source Object",
            description="Animated object used to calculate speed and acceleration",
            type=bpy.types.Object,
        )
        bpy.types.Scene.speed_accel_forward_axis = EnumProperty(
            name="Forward Direction",
            description="Local object axis treated as the object's forward direction",
            items=[
                ('LOCAL_X', "+X", "Use the object's local +X axis as forward"),
                ('LOCAL_NEG_X', "-X", "Use the object's local -X axis as forward"),
                ('LOCAL_Y', "+Y", "Use the object's local +Y axis as forward"),
                ('LOCAL_NEG_Y', "-Y", "Use the object's local -Y axis as forward"),
                ('LOCAL_Z', "+Z", "Use the object's local +Z axis as forward"),
                ('LOCAL_NEG_Z', "-Z", "Use the object's local -Z axis as forward"),
            ],
            default='LOCAL_X',
        )
        bpy.types.Scene.speed_accel_forward_yaw_offset = FloatProperty(
            name="Forward Yaw Offset (deg)",
            description="Additional yaw offset applied to the selected forward direction in degrees",
            default=0.0,
            soft_min=-180.0,
            soft_max=180.0,
        )
        bpy.types.Scene.speed_accel_window_frames = IntProperty(
            name="Average Window (Frames)",
            description="Number of sampled frames used for the centered average velocity window; 3 compares the previous and next frames",
            default=3,
            min=2,
        )
        bpy.types.Scene.speed_accel_unit_mode = EnumProperty(
            name="Distance Units",
            description="Units represented by object location values before conversion to mph and g",
            items=[
                ('AUTO', "Auto", "Use the scene unit scale to convert Blender Units to mph and g"),
                ('METERS', "Meters", "Treat object location values as meters"),
                ('FEET', "Feet", "Treat object location values as feet"),
            ],
            default='AUTO',
        )
        bpy.types.Scene.speed_accel_use_xy_only = bpy.props.BoolProperty(
            name="Use XY Only",
            description="Ignore vertical displacement when calculating speed",
            default=True,
        )
        bpy.types.Scene.speed_accel_remove_old_curves = bpy.props.BoolProperty(
            name="Replace Existing Curves",
            description="Remove previously baked speed and acceleration curves from the helper before baking",
            default=True,
        )
        bpy.types.Scene.speed_accel_parent_helper = bpy.props.BoolProperty(
            name="Parent Helper to Source",
            description="Parent the SpeedData helper empty to the source object after baking",
            default=False,
        )

        bpy.types.Scene.motion_marker_interval_seconds = FloatProperty(
            name="Marker Interval (sec)",
            description="Time spacing between generated object location markers",
            default=1.0,
            min=0.001,
        )
        bpy.types.Scene.motion_marker_size = FloatProperty(
            name="Marker Size",
            description="Triangle marker size in scene units",
            default=1.0,
            min=0.001,
        )
        bpy.types.Scene.motion_marker_zero_frame = FloatProperty(
            name="Zero Frame",
            description="Frame used as time zero; markers are generated forward and backward from this frame",
            default=1.0,
        )
        bpy.types.Scene.motion_marker_forward_axis = EnumProperty(
            name="Marker Forward Direction",
            description="Local object axis that the triangle tip should point along",
            items=[
                ('LOCAL_X', "+X", "Use the object's local +X axis as forward"),
                ('LOCAL_NEG_X', "-X", "Use the object's local -X axis as forward"),
                ('LOCAL_Y', "+Y", "Use the object's local +Y axis as forward"),
                ('LOCAL_NEG_Y', "-Y", "Use the object's local -Y axis as forward"),
                ('LOCAL_Z', "+Z", "Use the object's local +Z axis as forward"),
                ('LOCAL_NEG_Z', "-Z", "Use the object's local -Z axis as forward"),
            ],
            default='LOCAL_X',
        )
        bpy.types.Scene.motion_marker_yaw_offset = FloatProperty(
            name="Marker Yaw Offset (deg)",
            description="Additional yaw offset applied to marker direction in degrees",
            default=0.0,
            soft_min=-180.0,
            soft_max=180.0,
        )
        bpy.types.Scene.motion_marker_create_time_labels = bpy.props.BoolProperty(
            name="Create Time Labels",
            description="Add text labels showing each marker time relative to the zero frame",
            default=True,
        )
        bpy.types.Scene.motion_marker_label_size = FloatProperty(
            name="Time Label Size",
            description="Text size for marker time labels in scene units",
            default=0.5,
            min=0.001,
        )
        bpy.types.Scene.motion_marker_replace_existing = bpy.props.BoolProperty(
            name="Replace Existing Markers",
            description="Remove the existing marker mesh for the object before creating a new one",
            default=True,
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
            default=False,
        )
        bpy.types.Scene.hve_setup_show_soil = bpy.props.BoolProperty(
            name="Show Soil",
            default=False,
        )
        bpy.types.Scene.hve_setup_show_water = bpy.props.BoolProperty(
            name="Show Water",
            default=False,
        )

        bpy.types.Scene.fbx_shape_key_max_samples = bpy.props.IntProperty(
            name="Max Shape Key Samples",
            description="Maximum shape keys kept per mesh after adaptive reduction. 0 = no cap, tolerance controls quality",
            default=24, min=0, soft_max=200,
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
        del bpy.types.Scene.scale_target_distance
        del bpy.types.Scene.speed_accel_target_object
        del bpy.types.Scene.speed_accel_forward_axis
        del bpy.types.Scene.speed_accel_forward_yaw_offset
        del bpy.types.Scene.speed_accel_window_frames
        del bpy.types.Scene.speed_accel_unit_mode
        del bpy.types.Scene.speed_accel_use_xy_only
        del bpy.types.Scene.speed_accel_remove_old_curves
        del bpy.types.Scene.speed_accel_parent_helper
        del bpy.types.Scene.motion_marker_interval_seconds
        del bpy.types.Scene.motion_marker_size
        del bpy.types.Scene.motion_marker_zero_frame
        del bpy.types.Scene.motion_marker_forward_axis
        del bpy.types.Scene.motion_marker_yaw_offset
        del bpy.types.Scene.motion_marker_create_time_labels
        del bpy.types.Scene.motion_marker_label_size
        del bpy.types.Scene.motion_marker_replace_existing
        del bpy.types.Scene.hve_setup_show_surface
        del bpy.types.Scene.hve_setup_show_materials
        del bpy.types.Scene.hve_setup_show_object_type
        del bpy.types.Scene.hve_setup_show_terrain
        del bpy.types.Scene.hve_setup_show_vehicle_lighting
        del bpy.types.Scene.hve_setup_show_forces
        del bpy.types.Scene.hve_setup_show_soil
        del bpy.types.Scene.hve_setup_show_water
        del bpy.types.Scene.fbx_shape_key_max_samples
        del bpy.types.Object.edr_input_mode_preference
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
