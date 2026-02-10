import ast
import math
import pathlib


class MathNP:
    pi = math.pi

    @staticmethod
    def deg2rad(value):
        return value * math.pi / 180.0

    @staticmethod
    def tan(value):
        return math.tan(value)


module_path = pathlib.Path(__file__).resolve().parents[1] / "edr_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {'np': MathNP}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == "estimate_yaw_rate_from_steering":
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

estimate_yaw_rate_from_steering = ns["estimate_yaw_rate_from_steering"]


def test_estimate_yaw_rate_from_steering_scalar():
    yaw_rate = estimate_yaw_rate_from_steering(20.0, 160.0, 2.5, 16.0)
    expected = (20.0 / 2.5) * math.tan(math.radians(10.0))
    assert math.isclose(yaw_rate, expected)


def test_estimate_yaw_rate_from_steering_invalid_params():
    try:
        estimate_yaw_rate_from_steering(10.0, 30.0, 0.0, 16.0)
        raised = False
    except ValueError:
        raised = True
    assert raised
