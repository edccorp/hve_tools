import ast
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / "speed_accel.py"
source = module_path.read_text()
module_ast = ast.parse(source)

ns = {}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == "get_speed_accel_source_object":
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)
        break

get_speed_accel_source_object = ns["get_speed_accel_source_object"]


class Scene:
    def __init__(self, target=None):
        self.speed_accel_target_object = target


class Context:
    def __init__(self, selected_objects=None, active_object=None, target=None):
        self.selected_objects = selected_objects or []
        self.active_object = active_object
        self.scene = Scene(target)


def test_selected_active_object_overrides_source_picker():
    selected = object()
    picker_target = object()
    context = Context(
        selected_objects=[selected],
        active_object=selected,
        target=picker_target,
    )

    assert get_speed_accel_source_object(context) is selected


def test_first_selected_object_is_used_when_active_is_not_selected():
    selected = object()
    active = object()
    picker_target = object()
    context = Context(
        selected_objects=[selected],
        active_object=active,
        target=picker_target,
    )

    assert get_speed_accel_source_object(context) is selected


def test_source_picker_is_used_only_when_nothing_is_selected():
    picker_target = object()
    context = Context(target=picker_target)

    assert get_speed_accel_source_object(context) is picker_target
