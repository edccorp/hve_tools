import bpy
import logging
from bpy.types import Operator
from bpy.props import StringProperty, FloatProperty
from bpy_extras.io_utils import ImportHelper

from .loaders import import_point_cloud

logger = logging.getLogger(__name__)

__all__ = ["IMPORT_OT_ply_pointcloud_geonodes", "register", "unregister"]

class IMPORT_OT_ply_pointcloud_geonodes(Operator, ImportHelper):
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

        self.report({'INFO'}, f"Imported point cloud and set up GeoNodes + material (attr='{self.color_attribute}').")
        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_ply_pointcloud_geonodes.bl_idname, text="Point Cloud (PLY / PTX / E57 / LAS)")


classes = (IMPORT_OT_ply_pointcloud_geonodes,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
