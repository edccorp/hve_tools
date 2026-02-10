import ast
import math
import pathlib


class MathNP:
    @staticmethod
    def cos(value):
        return math.cos(value)

    @staticmethod
    def sin(value):
        return math.sin(value)


module_path = pathlib.Path(__file__).resolve().parents[1] / "edr_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {"np": MathNP}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == "integrate_step":
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

integrate_step = ns["integrate_step"]


def test_integrate_step_straight_line_no_yaw():
    x, y, psi, v, r = integrate_step(0.0, 0.0, 0.0, 10.0, 0.0, 0.5, 0.0, 0.0)

    assert math.isclose(x, 5.0)
    assert math.isclose(y, 0.0)
    assert math.isclose(psi, 0.0)
    assert math.isclose(v, 10.0)
    assert math.isclose(r, 0.0)


def test_integrate_step_constant_turn_uses_midpoint_heading():
    # 1 m movement while heading changes from 0 to pi/2 should land near 45°
    x, y, psi, v, r = integrate_step(0.0, 0.0, 0.0, 1.0, math.pi / 2, 1.0, 0.0, 0.0)

    expected = math.sqrt(2) / 2
    assert math.isclose(x, expected, rel_tol=1e-9)
    assert math.isclose(y, expected, rel_tol=1e-9)
    assert math.isclose(psi, math.pi / 2)
