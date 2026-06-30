import ast
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / "import_xyzrpy.py"
source = module_path.read_text()
module_ast = ast.parse(source)

ns = {}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {"iter_action_fcurves", "set_extrapolation"}:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
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

    set_extrapolation(obj, "LINEAR")

    assert layered_curve.extrapolation == "LINEAR"
