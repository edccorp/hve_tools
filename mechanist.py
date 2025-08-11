
import os
import time
import datetime
import numpy as np

import bpy
import bgl
from gpu.types import GPUShader
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix

from .debug import log, debug_mode

class HVEMechanist():
    cache = {}
    handle = None
    initialized = False
    
    @classmethod
    def init(cls):
        if(cls.initialized):
            return
        
        log("init", prefix='>>>', )
        
        cls.handle = bpy.types.SpaceView3D.draw_handler_add(cls.draw_handler, (), 'WINDOW', 'POST_VIEW', )
        # deinitialize when new file is about to be loaded
        bpy.app.handlers.load_pre.append(watcher)
        # clean cache if container is missing, e.g. on undo/redo, rename, delete etc.. so i don't need to deal with references
        bpy.app.handlers.depsgraph_update_post.append(cls.gc)
        cls.initialized = True
    
    @classmethod
    def deinit(cls):
        if(not cls.initialized):
            return
        
        log("deinit", prefix='>>>', )
        
        bpy.types.SpaceView3D.draw_handler_remove(cls.handle, 'WINDOW', )
        cls.handle = None
        cls.cache = {}
        if(watcher in bpy.app.handlers.load_pre):

            bpy.app.handlers.load_pre.remove(watcher)
        if(cls.gc in bpy.app.handlers.depsgraph_update_post):
            bpy.app.handlers.depsgraph_update_post.remove(cls.gc)
        cls.initialized = False
     



