import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty

from . import ui


class POINTCLOUD_preferences(AddonPreferences):
    bl_idname = __package__

    category: StringProperty(
        name="Sidebar Tab",
        default="Point Cloud",
        description="Name of the 3D View sidebar tab the Point Cloud Tools panels appear in; use an existing tab name (e.g. HVE) to append to that tab",
        update=ui.update_panel_bl_category,
    )

    def draw(self, context):
        self.layout.prop(self, "category")


classes = (
    POINTCLOUD_preferences,
)
