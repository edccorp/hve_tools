import ast
import pathlib
import re

# Parse functions from fbx_importer.py without importing the module
module_path = pathlib.Path(__file__).resolve().parents[1] / "fbx_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {'re': re}
for node in module_ast.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "ROTATION_AXIS_KEYWORDS":
                code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
                exec(code, ns)
    elif isinstance(node, ast.FunctionDef) and node.name in {
        "_iter_layered_fcurve_collections",
        "normalize_root_name",
        "get_root_vehicle_names",
        "belongs_to_vehicle",
        "join_mesh_objects_per_vehicle",
        "normalize_name",
        "copy_animated_rotation",
        "get_action_fcurve_collection",
        "iter_action_fcurve_collections",
        "iter_action_fcurves",
        "offset_selected_animation",
        "ensure_preroll_keys",
        "adjust_animation",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

normalize_root_name = ns["normalize_root_name"]
get_root_vehicle_names = ns["get_root_vehicle_names"]
belongs_to_vehicle = ns["belongs_to_vehicle"]
join_mesh_objects_per_vehicle = ns["join_mesh_objects_per_vehicle"]
normalize_name = ns["normalize_name"]
copy_animated_rotation = ns["copy_animated_rotation"]
adjust_animation = ns["adjust_animation"]
offset_selected_animation = ns["offset_selected_animation"]
ROTATION_AXIS_KEYWORDS = ns["ROTATION_AXIS_KEYWORDS"]


class Obj:
    def __init__(self, name, type='EMPTY', parent=None):
        self.name = name
        self.type = type
        self.parent = parent


def test_get_root_vehicle_names_dedup():
    root1 = Obj('Heil')
    root2 = Obj('Heil.001')
    root3 = Obj('Heil_Rear')
    child = Obj('Mesh: Heil.001: Body', type='MESH', parent=root2)
    objects = [root1, root2, root3, child]
    assert get_root_vehicle_names(objects) == ['Heil', 'Heil_Rear']


def test_belongs_to_vehicle_match():
    assert belongs_to_vehicle('Mesh: Heil: Body', 'Heil')
    assert belongs_to_vehicle('Heil', 'Heil')
    assert belongs_to_vehicle('Mesh: Heil_Rear: Body', 'Heil_Rear')
    assert belongs_to_vehicle('Wheel: Heil Rear: Body', 'Heil_Rear')
    assert not belongs_to_vehicle('Mesh: Other: Body', 'Heil')


def test_belongs_to_vehicle_distinct_prefixes():
    assert not belongs_to_vehicle('Mesh: Heil_Rear: Body', 'Heil')
    assert not belongs_to_vehicle('Mesh: Heil: Body', 'Heil_Rear')
    assert not belongs_to_vehicle('Wheel: Heil Rear: Body', 'Heil')

def test_belongs_to_vehicle_numeric_suffix():
    assert belongs_to_vehicle('Mesh: Heil.001: Body', 'Heil')
    assert belongs_to_vehicle('Mesh: Heil_Rear.001: Body', 'Heil_Rear')
    assert not belongs_to_vehicle('Mesh: Heil_Rear.001: Body', 'Heil')
    assert not belongs_to_vehicle('Mesh: Other.001: Body', 'Heil')


def test_belongs_to_vehicle_wheel_descriptors():
    for token in ['Wheel', 'Tire', 'Geometry', 'Steering']:
        name = f'Wheel_FL: Heil Rear {token}'
        assert belongs_to_vehicle(name, 'Heil_Rear')


def test_join_mesh_objects_per_vehicle_with_colon_segments():
    class Obj:
        def __init__(self, name, type='MESH'):
            self.name = name
            self.type = type
            self.selected = False

        def select_set(self, val):
            self.selected = val

    objs = [
        Obj('Mesh: Honda:0'),
        Obj('Mesh: Honda:1'),
        Obj('Mesh: Toyota:0'),
    ]

    joined = []

    class OpsObject:
        @staticmethod
        def select_all(action):
            if action == 'DESELECT':
                for o in objs:
                    o.selected = False

        @staticmethod
        def join():
            joined.append([o for o in objs if o.selected])

    bpy_stub = type(
        'bpy',
        (),
        {
            'data': type('data', (), {'collections': []})(),
            'context': type(
                'context',
                (),
                {
                    'scene': type('scene', (), {'objects': objs})(),
                    'view_layer': type(
                        'view_layer',
                        (),
                        {'objects': type('objects', (), {'active': None})()},
                    )(),
                },
            )(),
            'ops': type('ops', (), {'object': OpsObject})(),
        },
    )()

    ns.update(
        {
            'bpy': bpy_stub,
            'bake_shape_keys_threaded': lambda _objs: None,
            'belongs_to_vehicle': belongs_to_vehicle,
        }
    )

    join_mesh_objects_per_vehicle(['Honda'])

    assert len(joined) == 1
    assert {o.name for o in joined[0]} == {'Mesh: Honda:0', 'Mesh: Honda:1'}


def test_copy_animated_rotation_discovers_helpers_with_normalized_names():
    class Anim:
        def __init__(self):
            self.action = type('action', (), {'fcurves': []})()

    parent = Obj('Wheel_FL')
    parent.animation_data = Anim()

    helper = Obj('Wheel: Wheel_FL: Camber Objects')
    helper.animation_data = Anim()

    removed = []

    class Objects:
        def remove(self, obj, do_unlink=True):
            removed.append(obj)

    bpy_stub = type(
        'bpy',
        (),
        {
            'context': type('context', (), {'selected_objects': [parent, helper]})(),
            'data': type('data', (), {'objects': Objects()})(),
        },
    )()

    ns.update({'bpy': bpy_stub})
    copy_animated_rotation(parent)

    assert removed == [helper]


def test_copy_animated_rotation_filters_by_vehicle_id():
    class Anim:
        def __init__(self):
            self.action = type('action', (), {'fcurves': []})()

    parent = Obj('Wheel: Heil_Rear')
    parent.animation_data = Anim()

    rotation = Obj('Wheel: Heil_Rear: Rotation Objects')
    rotation.animation_data = Anim()
    camber = Obj('Wheel: Heil_Rear: Camber Objects')
    camber.animation_data = Anim()
    steering = Obj('Wheel: Heil_Rear: Steering Objects')
    steering.animation_data = Anim()
    other = Obj('Wheel: Other: Rotation Objects')
    other.animation_data = Anim()

    removed = []

    class Objects:
        def remove(self, obj, do_unlink=True):
            removed.append(obj)

    bpy_stub = type(
        'bpy',
        (),
        {
            'context': type('context', (), {'selected_objects': [parent, rotation, camber, steering, other]})(),
            'data': type('data', (), {'objects': Objects()})(),
        },
    )()

    ns.update({'bpy': bpy_stub})
    copy_animated_rotation(parent)

    assert set(removed) == {rotation, camber, steering}


def test_adjust_animation_does_not_insert_synthetic_preroll_keys():
    class KeyPoint:
        def __init__(self, frame, value):
            self.co = type("co", (), {"x": frame, "y": value})()
            self.handle_left = type("co", (), {"x": frame - 0.1, "y": value})()
            self.handle_right = type("co", (), {"x": frame + 0.1, "y": value})()

    class FCurve:
        def __init__(self):
            self.data_path = "rotation_euler"
            self.array_index = 0
            self.keyframe_points = [KeyPoint(-1, 0.0)]

    class FCurveCollection(list):
        def remove(self, _fcurve):
            raise AssertionError("No scale fcurves should be removed in this test")

    class Action:
        def __init__(self):
            self.fcurves = FCurveCollection([FCurve()])

    class ObjWithAnimation:
        def __init__(self):
            self.animation_data = type("anim", (), {"action": Action()})()
            self.scale = type("scale", (), {"y": 1.0, "z": 1.0})()
            self.inserted = []

        def keyframe_insert(self, data_path, frame):
            self.inserted.append((data_path, frame))

    obj = ObjWithAnimation()
    ns["math"] = __import__("math")

    adjust_animation(obj)

    assert obj.inserted == []


def test_ensure_preroll_keys_duplicates_first_pose_at_minus_one():
    class KeyPoint:
        def __init__(self, frame, value):
            self.co = type("co", (), {"x": frame, "y": value})()
            self.handle_left = type("co", (), {"x": frame - 0.1, "y": value})()
            self.handle_right = type("co", (), {"x": frame + 0.1, "y": value})()
            self.interpolation = "BEZIER"

    class KeyframeCollection(list):
        def insert(self, frame, value, options=None):
            key = KeyPoint(frame, value)
            self.append(key)
            return key

    curve = type(
        "FCurve",
        (),
        {
            "data_path": "rotation_euler",
            "array_index": 0,
            "keyframe_points": KeyframeCollection([KeyPoint(0.0, 1.25)]),
        },
    )()

    action = type("Action", (), {"fcurves": [curve]})()

    ns["ensure_preroll_keys"](action, target_frame=-1)

    xs = sorted(k.co.x for k in curve.keyframe_points)
    assert xs == [-1.0, 0.0]
    values = {k.co.x: k.co.y for k in curve.keyframe_points}
    assert values[-1.0] == values[0.0] == 1.25


def test_get_action_fcurve_collection_supports_layered_actions():
    layered_curve = object()
    action = type(
        "Action",
        (),
        {
            "layers": [
                type(
                    "Layer",
                    (),
                    {
                        "strips": [
                            type(
                                "Strip",
                                (),
                                {
                                    "channelbags": [
                                        type("Bag", (), {"fcurves": [layered_curve]})()
                                    ]
                                },
                            )()
                        ]
                    },
                )()
            ]
        },
    )()

    fcurves = ns["get_action_fcurve_collection"](action)
    assert list(fcurves) == [layered_curve]


def test_offset_selected_animation_auto_aligns_first_key_to_frame_zero():
    class KeyPoint:
        def __init__(self, frame):
            self.co = type("co", (), {"x": frame, "y": 0.0})()
            self.handle_left = type("h", (), {"x": frame - 0.2, "y": 0.0})()
            self.handle_right = type("h", (), {"x": frame + 0.2, "y": 0.0})()

    curve = type(
        "FCurve",
        (),
        {
            "keyframe_points": [KeyPoint(1.0), KeyPoint(10.0)],
            "data_path": "location",
            "array_index": 0,
        },
    )()

    action = type(
        "Action",
        (),
        {
            "layers": [
                type(
                    "Layer",
                    (),
                    {
                        "strips": [
                            type(
                                "Strip",
                                (),
                                {"channelbags": [type("Bag", (), {"fcurves": [curve]})()]},
                            )()
                        ]
                    },
                )()
            ]
        },
    )()

    obj = type("Obj", (), {"animation_data": type("Anim", (), {"action": action})()})()

    offset_selected_animation(obj, frame_offset=None, target_start_frame=0)

    assert curve.keyframe_points[0].co.x == 0.0
    assert curve.keyframe_points[1].co.x == 9.0


if __name__ == "__main__":
    test_get_root_vehicle_names_dedup()
    test_belongs_to_vehicle_match()
    test_belongs_to_vehicle_numeric_suffix()
    print("ok")
