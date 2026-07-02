import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty

from . import ui


class MOTION_preferences(AddonPreferences):
    bl_idname = __package__

    category: StringProperty(
        name="Sidebar Tab",
        default="Motion Data",
        description="Name of the 3D View sidebar tab the Motion Data Tools panels appear in; use an existing tab name (e.g. HVE) to append to that tab",
        update=ui.update_panel_bl_category,
    )

    def draw(self, context):
        self.layout.prop(self, "category")


classes = (
    MOTION_preferences,
)
