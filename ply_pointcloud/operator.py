import bpy
import logging
import subprocess
import sys
from bpy.types import Operator
from bpy.props import StringProperty, FloatProperty
from bpy_extras.io_utils import ImportHelper

from .loaders import (
    import_point_cloud,
    missing_optional_deps,
    deps_for_extension,
    OPTIONAL_DEPS,
)

logger = logging.getLogger(__name__)

__all__ = [
    "IMPORT_OT_ply_pointcloud_geonodes",
    "IMPORT_OT_install_pointcloud_deps",
    "install_optional_packages",
    "register",
    "unregister",
]


def install_optional_packages(specs):
    """pip-install the given package specs into Blender's Python.

    Raises on failure. Invalidates import caches so freshly installed packages
    can be imported without restarting Blender when possible.
    """
    import importlib

    py = sys.executable
    try:
        subprocess.run([py, "-m", "ensurepip"], check=False)
    except Exception as exc:  # noqa: BLE001 - ensurepip is best-effort
        logger.warning("ensurepip failed (continuing): %s", exc)
    subprocess.check_call([py, "-m", "pip", "install", "--upgrade"] + list(specs))
    importlib.invalidate_caches()

class IMPORT_OT_ply_pointcloud_geonodes(Operator, ImportHelper):
    """Import a point cloud (PLY, PTX, E57, or LAS/LAZ) as a coloured mesh with a Geometry Nodes point display"""
    bl_idname = "import_scene.ply_pointcloud_geonodes"
    bl_label = "Point Cloud (PLY / PTX / E57 / LAS)"
    bl_options = {'UNDO'}

    filename_ext = ".ply"
    filter_glob: StringProperty(default="*.ply;*.ptx;*.e57;*.las;*.laz", options={'HIDDEN'})
    point_radius: FloatProperty(name="Point Radius", default=0.1, min=0.000001, soft_max=0.1)
    color_attribute: StringProperty(name="Color Attribute", default="Col")
    display_subsample: FloatProperty(
        name="Points Visible %",
        description="Percentage of points shown in the viewport; display only, all points are kept in the data",
        default=100.0, min=0.0, max=100.0, subtype='PERCENTAGE',
    )

    def execute(self, context):
        import os

        # Auto-install the package this format needs (E57 -> pye57, LAZ ->
        # laspy) the first time such a file is opened, so it just works without
        # a manual step. Native formats (PLY/PTX/LAS) need nothing.
        ext = os.path.splitext(self.filepath)[1].lower()
        needed = deps_for_extension(ext)
        if needed:
            specs = [spec for _n, spec, _f in needed]
            window = context.window
            if window is not None:
                window.cursor_set('WAIT')
            print(f"[HVE Tools] Installing {', '.join(specs)} for {ext} import...")
            try:
                install_optional_packages(specs)
            except Exception as exc:  # noqa: BLE001 - surface pip failure to the user
                self.report(
                    {'ERROR'},
                    f"Couldn't auto-install {', '.join(specs)} for {ext} import: "
                    f"{exc}. Use 'Install E57 / LAZ Support' in the panel, or run "
                    f"`pip install {' '.join(specs)}` in Blender's Python.",
                )
                return {'CANCELLED'}
            finally:
                if window is not None:
                    window.cursor_set('DEFAULT')

        try:
            obj = import_point_cloud(
                self.filepath,
                setup_geonodes=True,
                point_radius=self.point_radius,
                color_attribute=self.color_attribute,
                display_subsample=self.display_subsample,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        try:
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    with context.temp_override(area=area, region=area.regions[-1], active_object=obj):
                        bpy.ops.view3d.view_selected(use_all_regions=False)
                    break

        except (AttributeError, RuntimeError) as exc:
            logger.warning("Unable to focus view on imported point cloud: %s", exc)

        # Auto-select the imported cloud as the Point Cloud Tools source so the
        # ground / 3D surface tools are ready to use it immediately.
        try:
            if hasattr(context.scene, "roadway_source_object"):
                context.scene.roadway_source_object = obj
        except (AttributeError, TypeError) as exc:
            logger.warning("Unable to set imported cloud as the surface source: %s", exc)

        self.report({'INFO'}, f"Imported point cloud and set up GeoNodes + material (attr='{self.color_attribute}').")
        return {'FINISHED'}


class IMPORT_OT_install_pointcloud_deps(Operator):
    bl_idname = "import_scene.install_pointcloud_deps"
    bl_label = "Install E57 / LAZ Support"
    bl_description = (
        "Install the optional pye57 and laspy[lazrs] Python packages into "
        "Blender's Python so E57 and compressed LAZ point clouds can be imported. "
        "Requires an internet connection; Blender may need to be run as "
        "administrator on Windows"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        specs = [spec for _name, spec, _fmt in OPTIONAL_DEPS]
        window = context.window
        if window is not None:
            window.cursor_set('WAIT')
        try:
            install_optional_packages(specs)
        except Exception as exc:  # noqa: BLE001 - surface any pip failure to the user
            self.report(
                {'ERROR'},
                f"Install failed: {exc}. Check your internet connection, or run "
                f"Blender as administrator and try again, or install manually: "
                f"pip install {' '.join(specs)}",
            )
            return {'CANCELLED'}
        finally:
            if window is not None:
                window.cursor_set('DEFAULT')

        still_missing = missing_optional_deps()
        if still_missing:
            names = ", ".join(spec for _n, spec, _f in still_missing)
            self.report(
                {'WARNING'},
                f"Installed, but still can't import: {names}. Restart Blender and "
                "try the import again.",
            )
        else:
            self.report(
                {'INFO'},
                "Installed E57 / LAZ support. Restart Blender if the import still "
                "reports a missing package.",
            )
        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_ply_pointcloud_geonodes.bl_idname, text="Point Cloud (PLY / PTX / E57 / LAS)")


classes = (IMPORT_OT_ply_pointcloud_geonodes, IMPORT_OT_install_pointcloud_deps)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
