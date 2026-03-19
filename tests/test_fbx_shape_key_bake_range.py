import ast
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / 'fbx_importer.py'
module_ast = ast.parse(module_path.read_text())


def test_bake_shape_keys_bakes_every_frame_before_reduction():
    bake_func = next(
        node for node in module_ast.body
        if isinstance(node, ast.FunctionDef) and node.name == 'bake_shape_keys_to_keyframes'
    )

    range_calls = [
        node for node in ast.walk(bake_func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'range'
    ]

    matching_call = next(
        call for call in range_calls
        if len(call.args) >= 2
        and isinstance(call.args[0], ast.Subscript)
        and isinstance(call.args[1], ast.BinOp)
    )

    assert len(matching_call.args) == 2, 'shape-key baking should evaluate every frame'
