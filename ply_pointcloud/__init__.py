"""PLY point-cloud importer (GeoNodes + vertex colour) integrated into HVE Tools.

Originally a standalone add-on by Engineering Dynamics Company (Anthony
Cornetto). Bundled here as a subpackage so PLY point clouds can be imported
directly from the HVE tab and fed into the Roadway Surface tool.
"""

from .ply_parser import load_ply_vertices, import_ply

try:  # Optional imports when bpy is unavailable (e.g. in tests)
    from .materials import make_point_material
    from .geonodes import make_geonodes_group, assign_geonodes_modifier
    from .operator import IMPORT_OT_ply_pointcloud_geonodes, register, unregister
except Exception:  # pragma: no cover - used when Blender's bpy is missing
    make_point_material = None
    make_geonodes_group = None
    assign_geonodes_modifier = None
    IMPORT_OT_ply_pointcloud_geonodes = None

    def register():  # type: ignore[no-redef]
        raise ImportError("Blender 'bpy' module is required")

    def unregister():  # type: ignore[no-redef]
        pass

__all__ = [
    "load_ply_vertices",
    "import_ply",
    "make_point_material",
    "make_geonodes_group",
    "assign_geonodes_modifier",
    "IMPORT_OT_ply_pointcloud_geonodes",
    "register",
    "unregister",
]
