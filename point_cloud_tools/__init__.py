bl_info = {
    "name": "Point Cloud Tools",
    "author": "Engnineering Dynamics Company : Anthony Cornetto",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "description": "Import, filter, and surface PLY point clouds: GeoNodes point display, voxel/SOR pre-filters, and draped roadway surfaces with baked color textures",
    'warning': '',
    "category": "Import-Export",
}

try:
    import bpy
    from . import ui, prefs, roadway_surface, ply_pointcloud

    from bpy.props import (
        IntProperty,
        PointerProperty,
        FloatProperty,
    )

    modules = [
        ui, prefs, roadway_surface,
    ]

    # Aggregate all classes from modules
    classes = [cls for module in modules for cls in module.classes]

    def register():
        for cls in classes:
            bpy.utils.register_class(cls)

        def _roadway_source_poll(self, obj):
            return obj is not None and obj.type == 'MESH'

        bpy.types.Scene.roadway_source_object = PointerProperty(
            name="Point Cloud",
            description="Mesh object whose vertices are the roadway point cloud (e.g. an imported PLY); leave empty to use the active object",
            type=bpy.types.Object,
            poll=_roadway_source_poll,
        )
        bpy.types.Scene.roadway_subsample = bpy.props.BoolProperty(
            name="Subsample (Voxel)",
            description="Thin the point cloud to one averaged point per voxel before surfacing (faster, more uniform)",
            default=False,
        )
        bpy.types.Scene.roadway_voxel_size = FloatProperty(
            name="Voxel Size",
            description="Edge length of the subsampling voxel, in the scene's units",
            default=0.1,
            min=0.0,
            soft_max=5.0,
            unit='LENGTH',
        )
        bpy.types.Scene.roadway_sor = bpy.props.BoolProperty(
            name="Remove Outliers (SOR)",
            description="Statistical Outlier Removal: drop points whose neighbours are unusually far away (floating noise, stray returns). Runs after subsampling",
            default=False,
        )
        bpy.types.Scene.roadway_sor_neighbors = IntProperty(
            name="SOR Neighbors (k)",
            description="Number of nearest neighbours averaged per point for outlier removal",
            default=16,
            min=1,
            soft_max=64,
        )
        bpy.types.Scene.roadway_sor_ratio = FloatProperty(
            name="SOR Std Ratio",
            description="Keep points whose mean neighbour distance is within mean + ratio x std; lower removes more",
            default=2.0,
            min=0.0,
            soft_max=10.0,
        )
        bpy.types.Scene.roadway_filter_in_place = bpy.props.BoolProperty(
            name="Filter In Place",
            description="Apply Filters Only replaces the selected cloud's points instead of creating a new filtered copy",
            default=False,
        )
        bpy.types.Scene.roadway_texture_source_object = PointerProperty(
            name="Texture Color Source",
            description="Optional: sample the baked texture's colour from this object (e.g. the original full-resolution cloud) instead of the surface's point cloud. Use it when the geometry cloud is a filtered copy",
            type=bpy.types.Object,
            poll=_roadway_source_poll,
        )
        bpy.types.Scene.roadway_color_height_tol = FloatProperty(
            name="Color Height Tolerance",
            description="Only points within this distance of the sampled ground height contribute colour to the surface and texture, so vehicles and foliage above the road cannot tint it; 0 = use all points",
            default=0.25,
            min=0.0,
            soft_max=5.0,
            unit='LENGTH',
        )
        bpy.types.Scene.roadway_cell_size = FloatProperty(
            name="Resolution (Cell Size)",
            description="Spacing of the generated surface grid, in the scene's units; smaller is finer and slower",
            default=0.3048,  # 1 foot (LENGTH props store metres; shows as 1 ft in Imperial scenes)
            min=0.001,
            soft_max=10.0,
            unit='LENGTH',
        )
        bpy.types.Scene.roadway_fill_distance = FloatProperty(
            name="Max Fill Distance",
            description="How far, in the scene's units, to interpolate across empty grid cells; 0 = unlimited",
            default=2.0,
            min=0.0,
            soft_max=50.0,
            unit='LENGTH',
        )
        bpy.types.Scene.roadway_ground_percentile = FloatProperty(
            name="Ground Percentile",
            description="Percentile of each cell's point heights taken as ground (low = from below); rejects overhead noise and stray low outliers",
            default=10.0,
            min=0.0,
            max=100.0,
        )
        bpy.types.Scene.roadway_fill_holes = bpy.props.BoolProperty(
            name="Fill Holes",
            description="Interpolate empty grid cells from their neighbours so sparse spots do not leave gaps",
            default=True,
        )
        bpy.types.Scene.roadway_transfer_color = bpy.props.BoolProperty(
            name="Transfer Point Color",
            description="Average the point cloud's per-point colour into each cell and store it on the surface as a color attribute",
            default=True,
        )
        bpy.types.Scene.roadway_create_material = bpy.props.BoolProperty(
            name="Create Material",
            description="Create a material whose Base Color is driven by the transferred Col color attribute, and assign it to the surface",
            default=True,
        )
        bpy.types.Scene.roadway_bake_texture = bpy.props.BoolProperty(
            name="Bake Color to Texture",
            description="Bake the per-cell colours to a JPG image (saved next to the .blend), add grid UVs, and build an image-texture material. Textures export to HVE more reliably than vertex colours",
            default=True,
        )
        bpy.types.Scene.roadway_texture_size = IntProperty(
            name="Texture Resolution",
            description="Longest side (pixels) of the baked texture, sampled directly from the point cloud so it can be sharper than the surface grid; 0 matches the grid resolution",
            default=4096,
            min=0,
            soft_max=16384,
        )

        ply_pointcloud.register()

        ui.update_panel_bl_category(None, bpy.context)

    def unregister():
        ply_pointcloud.unregister()

        del bpy.types.Scene.roadway_source_object
        del bpy.types.Scene.roadway_subsample
        del bpy.types.Scene.roadway_voxel_size
        del bpy.types.Scene.roadway_sor
        del bpy.types.Scene.roadway_sor_neighbors
        del bpy.types.Scene.roadway_sor_ratio
        del bpy.types.Scene.roadway_filter_in_place
        del bpy.types.Scene.roadway_texture_source_object
        del bpy.types.Scene.roadway_color_height_tol
        del bpy.types.Scene.roadway_cell_size
        del bpy.types.Scene.roadway_fill_distance
        del bpy.types.Scene.roadway_ground_percentile
        del bpy.types.Scene.roadway_fill_holes
        del bpy.types.Scene.roadway_transfer_color
        del bpy.types.Scene.roadway_create_material
        del bpy.types.Scene.roadway_bake_texture
        del bpy.types.Scene.roadway_texture_size

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

print("Point Cloud Tools successfully (re)loaded")
