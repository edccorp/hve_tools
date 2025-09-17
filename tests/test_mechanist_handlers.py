import importlib
import sys
import types

import pytest


@pytest.fixture
def blender_stubs(monkeypatch):
    """Provide minimal Blender API shims required for the mechanist module."""

    handlers_module = types.ModuleType("bpy.app.handlers")
    handlers_module.load_pre = []
    handlers_module.load_post = []
    handlers_module.depsgraph_update_post = []

    def persistent(func):
        func.__persistent__ = True
        return func

    handlers_module.persistent = persistent

    app_module = types.ModuleType("bpy.app")
    app_module.handlers = handlers_module
    app_module.debug_value = 1

    class FakeSpaceView3D:
        handles = []
        removed = []

        @staticmethod
        def draw_handler_add(callback, args, region, space):
            handle = object()
            FakeSpaceView3D.handles.append(handle)
            return handle

        @staticmethod
        def draw_handler_remove(handle, region):
            FakeSpaceView3D.removed.append(handle)
            if handle in FakeSpaceView3D.handles:
                FakeSpaceView3D.handles.remove(handle)

    bpy_types_module = types.ModuleType("bpy.types")

    class Operator:
        bl_idname = ""
        bl_label = ""
        bl_description = ""

        @classmethod
        def poll(cls, context):  # pragma: no cover - default always true
            return True

        def execute(self, context):  # pragma: no cover - default noop
            return {'FINISHED'}

    bpy_types_module.Operator = Operator
    bpy_types_module.SpaceView3D = FakeSpaceView3D

    bpy_module = types.ModuleType("bpy")
    bpy_module.app = app_module
    bpy_module.types = bpy_types_module

    bpy_props_module = types.ModuleType("bpy.props")

    def _property_stub(*args, **kwargs):  # pragma: no cover - simple placeholder
        return types.SimpleNamespace(args=args, kwargs=kwargs)

    for name in [
        "StringProperty",
        "IntProperty",
        "EnumProperty",
        "PointerProperty",
        "FloatProperty",
    ]:
        setattr(bpy_props_module, name, _property_stub)

    bpy_module.props = bpy_props_module

    monkeypatch.setitem(sys.modules, "bpy", bpy_module)
    monkeypatch.setitem(sys.modules, "bpy.app", app_module)
    monkeypatch.setitem(sys.modules, "bpy.app.handlers", handlers_module)
    monkeypatch.setitem(sys.modules, "bpy.props", bpy_props_module)
    monkeypatch.setitem(sys.modules, "bpy.types", bpy_types_module)

    monkeypatch.setitem(sys.modules, "bgl", types.ModuleType("bgl"))
    monkeypatch.setitem(sys.modules, "bmesh", types.ModuleType("bmesh"))

    gpu_module = types.ModuleType("gpu")
    gpu_types_module = types.ModuleType("gpu.types")

    class DummyShader:
        pass

    gpu_types_module.GPUShader = DummyShader
    gpu_module.types = gpu_types_module
    monkeypatch.setitem(sys.modules, "gpu", gpu_module)
    monkeypatch.setitem(sys.modules, "gpu.types", gpu_types_module)

    gpu_extras_module = types.ModuleType("gpu_extras")
    gpu_extras_batch_module = types.ModuleType("gpu_extras.batch")

    def batch_for_shader(*args, **kwargs):  # pragma: no cover - trivial shim
        return object()

    gpu_extras_batch_module.batch_for_shader = batch_for_shader
    gpu_extras_module.batch = gpu_extras_batch_module
    monkeypatch.setitem(sys.modules, "gpu_extras", gpu_extras_module)
    monkeypatch.setitem(sys.modules, "gpu_extras.batch", gpu_extras_batch_module)

    mathutils_module = types.ModuleType("mathutils")

    class Vector(tuple):  # pragma: no cover - container placeholder
        pass

    class Matrix(tuple):  # pragma: no cover - container placeholder
        pass

    class Quaternion(tuple):  # pragma: no cover - container placeholder
        pass

    class Color(tuple):  # pragma: no cover - container placeholder
        pass

    mathutils_module.Vector = Vector
    mathutils_module.Matrix = Matrix
    mathutils_module.Quaternion = Quaternion
    mathutils_module.Color = Color
    mathutils_geometry_module = types.ModuleType("mathutils.geometry")
    mathutils_geometry_module.intersect_point_line = lambda *args, **kwargs: None
    mathutils_module.geometry = mathutils_geometry_module
    monkeypatch.setitem(sys.modules, "mathutils", mathutils_module)
    monkeypatch.setitem(sys.modules, "mathutils.geometry", mathutils_geometry_module)

    bpy_extras_module = types.ModuleType("bpy_extras")
    bpy_extras_io_utils = types.ModuleType("bpy_extras.io_utils")
    bpy_extras_io_utils.axis_conversion = lambda *args, **kwargs: None

    class ExportHelper:  # pragma: no cover - placeholder mixin
        pass

    bpy_extras_io_utils.ExportHelper = ExportHelper
    bpy_extras_module.io_utils = bpy_extras_io_utils
    monkeypatch.setitem(sys.modules, "bpy_extras", bpy_extras_module)
    monkeypatch.setitem(sys.modules, "bpy_extras.io_utils", bpy_extras_io_utils)

    numpy_module = types.ModuleType("numpy")
    numpy_module.array = lambda *args, **kwargs: args[0]
    numpy_module.float32 = float
    numpy_module.float64 = float
    monkeypatch.setitem(sys.modules, "numpy", numpy_module)

    return {
        "handlers": handlers_module,
        "space_view3d": FakeSpaceView3D,
    }


@pytest.fixture
def mechanist_modules(blender_stubs):
    for module_name in ["hve_tools.debug", "hve_tools.mechanist", "hve_tools.ops"]:
        sys.modules.pop(module_name, None)

    mechanist = importlib.import_module("hve_tools.mechanist")
    ops = importlib.import_module("hve_tools.ops")

    # Provide minimal implementations expected by the operator wrappers.
    mechanist.HVEMechanist.draw_handler = staticmethod(lambda: None)
    mechanist.HVEMechanist.tag_redraw = staticmethod(lambda: None)
    mechanist.HVEMechanist.gc = staticmethod(lambda *args, **kwargs: None)

    return mechanist, ops, blender_stubs


def test_mechanist_handlers_register_and_unregister(mechanist_modules):
    mechanist, ops, stubs = mechanist_modules
    handlers = stubs["handlers"]

    init_op = ops.HVE_OT_mechanist_init()
    assert init_op.execute(None) == {'FINISHED'}

    assert mechanist.HVEMechanist.initialized is True
    assert handlers.load_pre == [mechanist.watcher]
    assert handlers.load_post == [mechanist.on_file_load]
    assert handlers.depsgraph_update_post == [mechanist.HVEMechanist.gc]
    assert mechanist.HVEMechanist.handle in stubs["space_view3d"].handles

    deinit_op = ops.HVE_OT_mechanist_deinit()
    assert deinit_op.execute(None) == {'FINISHED'}

    assert mechanist.HVEMechanist.initialized is False
    assert mechanist.HVEMechanist.handle is None
    assert handlers.load_pre == []
    assert handlers.load_post == []
    assert handlers.depsgraph_update_post == []


def test_watcher_cleans_up_without_removing_itself(mechanist_modules):
    mechanist, ops, stubs = mechanist_modules
    handlers = stubs["handlers"]
    space = stubs["space_view3d"]

    ops.HVE_OT_mechanist_init().execute(None)
    mechanist.HVEMechanist.cache["example"] = 1

    # Simulate Blender invoking the load-pre handler with arbitrary arguments.
    mechanist.watcher(object())

    assert mechanist.HVEMechanist.initialized is False
    assert mechanist.HVEMechanist.cache == {}
    assert mechanist.HVEMechanist.handle is None
    assert handlers.load_pre == [mechanist.watcher]
    assert handlers.load_post == []
    assert handlers.depsgraph_update_post == []
    assert space.removed  # The draw handler was removed during cleanup.

    # The watcher should quietly ignore subsequent calls when already clean.
    mechanist.watcher()

