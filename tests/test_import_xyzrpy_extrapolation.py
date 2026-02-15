import ast
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / "import_xyzrpy.py"
source = module_path.read_text()
module_ast = ast.parse(source)

ns = {}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == "iter_action_fcurves":
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

for node in module_ast.body:
    if isinstance(node, ast.ClassDef) and node.name == "ImportCSVAnimationOperator":
        for class_node in node.body:
            if isinstance(class_node, ast.FunctionDef) and class_node.name == "set_extrapolation":
                class_node = ast.FunctionDef(
                    name="set_extrapolation",
                    args=class_node.args,
                    body=class_node.body,
                    decorator_list=[],
                    returns=class_node.returns,
                    type_comment=class_node.type_comment,
                )
                module = ast.Module([class_node], [])
                module = ast.fix_missing_locations(module)
                code = compile(module, filename="<ast>", mode="exec")
                exec(code, ns)


iter_action_fcurves = ns["iter_action_fcurves"]
set_extrapolation = ns["set_extrapolation"]


class Curve:
    def __init__(self):
        self.extrapolation = "BEZIER"


def _build_obj_with_action(action):
    return type("Obj", (), {"animation_data": type("Anim", (), {"action": action})()})()


def test_iter_action_fcurves_supports_layered_actions():
    layered_curve = Curve()
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
                                {"channelbags": [type("Bag", (), {"fcurves": [layered_curve]})()]},
                            )()
                        ]
                    },
                )()
            ]
        },
    )()

    curves = list(iter_action_fcurves(action))
    assert curves == [layered_curve]


def test_set_extrapolation_updates_layered_action_curves():
    layered_curve = Curve()
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
                                {"channelbags": [type("Bag", (), {"fcurves": [layered_curve]})()]},
                            )()
                        ]
                    },
                )()
            ]
        },
    )()
    obj = _build_obj_with_action(action)

    set_extrapolation(None, obj, "LINEAR")

    assert layered_curve.extrapolation == "LINEAR"
