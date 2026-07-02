import os
import time
import datetime
import numpy as np
import re

import bpy
import bmesh
from bpy.props import StringProperty
from bpy.types import Operator
from mathutils import Matrix, Vector, Quaternion, Color
from bpy_extras.io_utils import axis_conversion, ExportHelper
import mathutils.geometry

from .debug import log, debug_mode
from .mechanist import HVEMechanist


class HVE_OT_mechanist_base(Operator):
    bl_idname = "human_vehicle_environment.mechanist_base"
    bl_label = "Base"
    bl_description = "HVEMechanist Base Operator"
    
    @classmethod
    def poll(cls, context):
        # if(not HVEMechanist.initialized):
        #     return False
        if(context.object is None):
            return False
        return True
    
    # def execute(self, context):
    #     return {'FINISHED'}


class HVE_OT_mechanist_init(HVE_OT_mechanist_base):
    bl_idname = "human_vehicle_environment.mechanist_init"
    bl_label = "Init"
    bl_description = "Initialize HVEMechanist"
    
    @classmethod
    def poll(cls, context):
        if(not debug_mode()):
            return False
        return not HVEMechanist.initialized
    
    def execute(self, context):
        HVEMechanist.init()
        HVEMechanist.tag_redraw()
        return {'FINISHED'}


class HVE_OT_mechanist_deinit(HVE_OT_mechanist_base):
    bl_idname = "human_vehicle_environment.mechanist_deinit"
    bl_label = "Deinit"
    bl_description = "Deinitialize HVEMechanist"
    
    @classmethod
    def poll(cls, context):
        if(not debug_mode()):
            return False
        return HVEMechanist.initialized
    
    def execute(self, context):
        HVEMechanist.deinit()
        HVEMechanist.tag_redraw()
        return {'FINISHED'}
        
        
class HVE_OT_mechanist_light_template(HVE_OT_mechanist_base):
    bl_idname = "hve_lights.add_light_template"
    bl_label = "Add HVE light switch template"
    bl_description = "Add an HVE light template switch text"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        if(context.object is None):
            return False
        o = context.object
        return True


    def execute(self, context):
        HVEMechanist.addHVELightText(context.object, context.scene)
        return{'FINISHED'}


classes = (
    HVE_OT_mechanist_init,
    HVE_OT_mechanist_deinit,
    HVE_OT_mechanist_light_template,
)
