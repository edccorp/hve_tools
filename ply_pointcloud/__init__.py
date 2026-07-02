"""Point-cloud importer (GeoNodes + vertex colour) integrated into HVE Tools.

Originally a standalone PLY add-on by Engineering Dynamics Company (Anthony
Cornetto). Bundled here as a subpackage so point clouds can be imported
directly from the HVE tab and fed into the Roadway Surface tool. Supports
PLY, PTX, E57 and LAS/LAZ (E57 and LAZ require optional Python packages).
"""

from .ply_parser import load_ply_vertices, build_point_cloud_object, import_ply
from .loaders import (
    load_ptx_vertices,
    load_e57_vertices,
    load_las_vertices,
    load_pcd_vertices,
    load_point_cloud_vertices,
    import_point_cloud,
    missing_optional_deps,
    OPTIONAL_DEPS,
    SUPPORTED_EXTENSIONS,
)

try:  # Optional imports when bpy is unavailable (e.g. in tests)
    from .materials import make_point_material
    from .geonodes import make_geonodes_group, assign_geonodes_modifier
    from .operator import (
        IMPORT_OT_ply_pointcloud_geonodes,
        IMPORT_OT_install_pointcloud_deps,
        register,
        unregister,
    )
except Exception:  # pragma: no cover - used when Blender's bpy is missing
    make_point_material = None
    make_geonodes_group = None
    assign_geonodes_modifier = None
    IMPORT_OT_ply_pointcloud_geonodes = None
    IMPORT_OT_install_pointcloud_deps = None

    def register():  # type: ignore[no-redef]
        raise ImportError("Blender 'bpy' module is required")

    def unregister():  # type: ignore[no-redef]
        pass

__all__ = [
    "load_ply_vertices",
    "build_point_cloud_object",
    "import_ply",
    "load_ptx_vertices",
    "load_e57_vertices",
    "load_las_vertices",
    "load_pcd_vertices",
    "load_point_cloud_vertices",
    "import_point_cloud",
    "missing_optional_deps",
    "OPTIONAL_DEPS",
    "SUPPORTED_EXTENSIONS",
    "make_point_material",
    "make_geonodes_group",
    "assign_geonodes_modifier",
    "IMPORT_OT_ply_pointcloud_geonodes",
    "IMPORT_OT_install_pointcloud_deps",
    "register",
    "unregister",
]
