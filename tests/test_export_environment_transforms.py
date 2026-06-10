import ast
import math
import pathlib

import pytest


module_path = pathlib.Path(__file__).resolve().parents[1] / "export_environment.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {}

wanted = {
    "HVE_GLOBAL_SCALE",
    "HVE_X_AXIS_FLIP_VALUES",
    "hve_global_scale_matrix",
    "compose_environment_mesh_matrix",
    "apply_environment_mesh_transform",
}

for node in module_ast.body:
    if isinstance(node, ast.Assign) and any(getattr(target, "id", None) in wanted for target in node.targets):
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)
    elif isinstance(node, ast.FunctionDef) and node.name in wanted:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

HVE_GLOBAL_SCALE = ns["HVE_GLOBAL_SCALE"]
HVE_X_AXIS_FLIP_VALUES = ns["HVE_X_AXIS_FLIP_VALUES"]
hve_global_scale_matrix = ns["hve_global_scale_matrix"]
compose_environment_mesh_matrix = ns["compose_environment_mesh_matrix"]
apply_environment_mesh_transform = ns["apply_environment_mesh_transform"]


class MatrixToken:
    def __init__(self, label):
        self.label = label

    def __matmul__(self, other):
        return MatrixToken(f"({self.label} @ {other.label})")


class DummyMatrixModule:
    class Matrix:
        @staticmethod
        def Scale(scale, size):
            return ("scale", scale, size)


class PlanarMatrix:
    def __init__(self, values):
        self.values = values

    def __matmul__(self, other):
        if isinstance(other, PlanarMatrix):
            return PlanarMatrix(tuple(
                tuple(
                    sum(self.values[row][idx] * other.values[idx][col] for idx in range(2))
                    for col in range(2)
                )
                for row in range(2)
            ))
        x, y = other
        return (
            self.values[0][0] * x + self.values[0][1] * y,
            self.values[1][0] * x + self.values[1][1] * y,
        )


def planar_z_rotation(degrees):
    radians = math.radians(degrees)
    return PlanarMatrix(((math.cos(radians), -math.sin(radians)),
                         (math.sin(radians), math.cos(radians))))


def planar_x_axis_flip():
    return PlanarMatrix(((1.0, 0.0), (0.0, -1.0)))


class DummyMesh:
    def __init__(self):
        self.calls = []

    def transform(self, matrix):
        self.calls.append(("transform", matrix))

    def update(self):
        self.calls.append(("update", None))


def test_hve_global_scale_defaults_to_inches_conversion():
    assert HVE_GLOBAL_SCALE == 39.37


def test_hve_global_scale_matrix_uses_default_inches_conversion(monkeypatch):
    monkeypatch.setitem(hve_global_scale_matrix.__globals__, "mathutils", DummyMatrixModule)

    assert hve_global_scale_matrix() == ("scale", 39.37, 4)


def test_hve_x_axis_flip_is_exact_180_degree_x_rotation_values():
    assert HVE_X_AXIS_FLIP_VALUES == (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, -1.0, 0.0, 0.0),
        (0.0, 0.0, -1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def test_compose_environment_mesh_matrix_applies_coordinate_transform_after_object():
    matrix = compose_environment_mesh_matrix(
        MatrixToken("global"),
        MatrixToken("object"),
        coordinate_transform=MatrixToken("x_flip"),
    )

    assert matrix.label == "((global @ x_flip) @ object)"


def test_coordinate_transform_after_object_reverses_z_rotation_direction():
    matrix = compose_environment_mesh_matrix(
        PlanarMatrix(((1.0, 0.0), (0.0, 1.0))),
        planar_z_rotation(16.0),
        coordinate_transform=planar_x_axis_flip(),
    )

    x_axis = matrix @ (1.0, 0.0)
    exported_angle = math.degrees(math.atan2(x_axis[1], x_axis[0]))

    assert exported_angle == pytest.approx(-16.0)


def test_apply_environment_mesh_transform_bakes_matrix_then_updates_mesh():
    mesh = DummyMesh()
    matrix = MatrixToken("export")

    apply_environment_mesh_transform(mesh, matrix)

    assert mesh.calls == [("transform", matrix), ("update", None)]


def test_save_forces_modifiers_on_for_environment_exports():
    save_def = next(
        node for node in module_ast.body
        if isinstance(node, ast.FunctionDef) and node.name == "save"
    )

    assert any(
        isinstance(node, ast.Assign)
        and any(getattr(target, "id", None) == "use_mesh_modifiers" for target in node.targets)
        and isinstance(node.value, ast.Constant)
        and node.value.value is True
        for node in ast.walk(save_def)
    )


def test_save_defaults_to_applying_modifiers_before_transform_bake():
    save_def = next(
        node for node in module_ast.body
        if isinstance(node, ast.FunctionDef) and node.name == "save"
    )
    kw_defaults = dict(zip(
        [arg.arg for arg in save_def.args.kwonlyargs],
        save_def.args.kw_defaults,
    ))

    assert isinstance(kw_defaults["use_mesh_modifiers"], ast.Constant)
    assert kw_defaults["use_mesh_modifiers"].value is True
