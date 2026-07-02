bl_info = {
    "name": "HVE Tools",
    "author": "Engnineering Dynamics Company : Anthony Cornetto",
    "version": (3, 0),
    "blender": (4, 0, 0),
    "description": "Pre- and post-simulation tools for HVE: H3D setup and export, HVE FBX and variable output import, RaceRender conversion",
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
    )

    from bpy.props import PointerProperty

    modules = [
        ui, materials, prefs, ops, export_vehicle_ui, export_environment_ui,
        contacts_exporter_ui, variableoutput_importer_ui, racerender_exporter_ui,
        fbx_importer_ui,
    ]

    # Aggregate all classes from modules
    classes = [cls for module in modules for cls in module.classes]

    def register():
        props.register()

        for cls in classes:
            bpy.utils.register_class(cls)

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
        bpy.types.Scene.fbx_process_collection = PointerProperty(
            name="Process Collection",
            description="Limit FBX post-processing to the body meshes nested under this collection; leave empty to process all imported vehicles",
            type=bpy.types.Collection,
        )

        ui.update_panel_bl_category(None, bpy.context)

    def unregister():
        del bpy.types.Scene.hve_setup_show_surface
        del bpy.types.Scene.hve_setup_show_materials
        del bpy.types.Scene.hve_setup_show_object_type
        del bpy.types.Scene.hve_setup_show_terrain
        del bpy.types.Scene.hve_setup_show_vehicle_lighting
        del bpy.types.Scene.hve_setup_show_forces
        del bpy.types.Scene.hve_setup_show_soil
        del bpy.types.Scene.hve_setup_show_water
        del bpy.types.Scene.fbx_shape_key_max_samples
        del bpy.types.Scene.fbx_process_collection
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
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
