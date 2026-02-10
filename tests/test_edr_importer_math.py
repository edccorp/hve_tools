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

    @staticmethod
    def maximum(a, b):
        return max(a, b)

    @staticmethod
    def asarray(value, dtype=float):
        return float(value)

    @staticmethod
    def arctan(value):
        return math.atan(value)

    @staticmethod
    def clip(value, low, high):
        return min(max(value, low), high)


module_path = pathlib.Path(__file__).resolve().parents[1] / "edr_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {'np': MathNP}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {
        "estimate_yaw_rate_from_steering",
        "estimate_slip_angle_from_yaw_rate",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

estimate_yaw_rate_from_steering = ns["estimate_yaw_rate_from_steering"]
estimate_slip_angle_from_yaw_rate = ns["estimate_slip_angle_from_yaw_rate"]


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


def test_estimate_slip_angle_from_yaw_rate_scalar():
    beta = estimate_slip_angle_from_yaw_rate(10.0, 0.2, 2.5, 1.0, 12.0)
    expected = math.atan((2.5 * 0.2) / 10.0)
    assert math.isclose(beta, expected)


def test_estimate_slip_angle_from_yaw_rate_clipped():
    beta = estimate_slip_angle_from_yaw_rate(0.1, 10.0, 2.5, 1.0, 12.0)
    assert math.isclose(beta, math.radians(12.0))
