

import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty, StringProperty, FloatVectorProperty, EnumProperty

from . import ui


class HVE_preferences(AddonPreferences):
    # bl_idname = __name__
    bl_idname = __package__
    
    category: EnumProperty(name="Tab Name", items=[('HUMAN_VEHICLE_ENVIRONMENT', "Human Vehicle Environment", ""),
                                                   ('HVE', "HVE", ""), ], default='HVE', description="To have HVE in its own separate tab, choose one", update=ui.update_panel_bl_category, )
    category_custom: BoolProperty(name="Custom Tab Name", default=False, description="Check if you want to have HVE in custom named tab or in existing tab", update=ui.update_panel_bl_category, )
    category_custom_name: StringProperty(name="Name", default="View", description="Custom HVE tab name, if you choose one from already existing tabs it will append to that tab", update=ui.update_panel_bl_category, )
    
    def draw(self, context):
        l = self.layout
        c = l.column()
        f = 0.5
        r = c.row()
        s = r.split(factor=f)
        cc = s.column()
        cc.prop(self, "category")
        if(self.category_custom):
            cc.enabled = False
        s = s.split(factor=1.0)
        r = s.row()
        r.prop(self, "category_custom")
        cc = r.column()
        cc.prop(self, "category_custom_name")
        if(not self.category_custom):
            cc.enabled = False


classes = (
    HVE_preferences,
)
