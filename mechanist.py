
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
        # perform actions after a file has been loaded
        if on_file_load not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(on_file_load)
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
        if on_file_load in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(on_file_load)
        if(cls.gc in bpy.app.handlers.depsgraph_update_post):
            bpy.app.handlers.depsgraph_update_post.remove(cls.gc)
        cls.initialized = False


def on_file_load(dummy):
    """Handler executed after a new file is loaded."""
    if debug_mode():
        log("file loaded", prefix='>>>')
     



