
import os
import time
import datetime
import numpy as np

import bpy
from bpy.app.handlers import persistent
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
        if watcher not in bpy.app.handlers.load_pre:
            bpy.app.handlers.load_pre.append(watcher)
        # perform actions after a file has been loaded
        if on_file_load not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(on_file_load)
        # clean cache if container is missing, e.g. on undo/redo, rename, delete etc.. so i don't need to deal with references
        gc_handler = getattr(cls, "gc", None)
        if gc_handler and gc_handler not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(gc_handler)
        cls.initialized = True

    @classmethod
    def deinit(cls):
        if(not cls.initialized):
            return

        log("deinit", prefix='>>>', )

        cls._shutdown(remove_load_pre=True)

    @classmethod
    def _shutdown(cls, remove_load_pre=True):
        """Release draw handlers and cached data.

        The ``remove_load_pre`` flag allows the load-pre handler itself to
        trigger the cleanup without attempting to remove the currently
        executing callback from ``bpy.app.handlers.load_pre``.
        """

        if cls.handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(cls.handle, 'WINDOW', )
            cls.handle = None
        cls.cache = {}
        if remove_load_pre and watcher in bpy.app.handlers.load_pre:
            bpy.app.handlers.load_pre.remove(watcher)
        if on_file_load in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(on_file_load)
        gc_handler = getattr(cls, "gc", None)
        if gc_handler and gc_handler in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(gc_handler)
        cls.initialized = False


@persistent
def watcher(*args):
    """Reset the Mechanist system before Blender loads a new file."""

    if not HVEMechanist.initialized:
        return

    if debug_mode():
        log("file load detected - cleaning up", prefix='>>>')

    HVEMechanist._shutdown(remove_load_pre=False)


def on_file_load(scene, context):
    """Handler executed after a new file is loaded.

    Blender's ``load_post`` handler passes the current ``scene`` and
    ``context`` when invoking callbacks.  Accepting these parameters keeps the
    handler compatible with Blender's expectations while allowing the function
    to ignore them when not needed.
    """

    if debug_mode():
        log("file loaded", prefix='>>>')
     



