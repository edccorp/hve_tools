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
        "normalize_root_name",
        "get_root_vehicle_names",
        "belongs_to_vehicle",
        "join_mesh_objects_per_vehicle",
        "normalize_name",
        "copy_animated_rotation",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

normalize_root_name = ns["normalize_root_name"]
get_root_vehicle_names = ns["get_root_vehicle_names"]
belongs_to_vehicle = ns["belongs_to_vehicle"]
join_mesh_objects_per_vehicle = ns["join_mesh_objects_per_vehicle"]
normalize_name = ns["normalize_name"]
copy_animated_rotation = ns["copy_animated_rotation"]
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


if __name__ == "__main__":
    test_get_root_vehicle_names_dedup()
    test_belongs_to_vehicle_match()
    test_belongs_to_vehicle_numeric_suffix()
    print("ok")
