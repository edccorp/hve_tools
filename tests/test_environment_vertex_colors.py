import ast
import pathlib


# Extract the bpy-free Open Inventor colour formatter from export_environment.py.
module_path = pathlib.Path(__file__).resolve().parents[1] / "export_environment.py"
module_ast = ast.parse(module_path.read_text())

ns = {}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == "format_diffuse_color_array":
        exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), ns)

format_diffuse_color_array = ns["format_diffuse_color_array"]


def test_diffuse_color_array_structure():
    out = format_diffuse_color_array([(1.0, 0.0, 0.0), (0.0, 0.5, 1.0)], indent="")
    lines = out.splitlines()
    assert lines[0] == "diffuseColor [ 2,"
    assert lines[1] == "1.0000 0.0000 0.0000 ,"
    assert lines[2] == "0.0000 0.5000 1.0000 ,"
    assert lines[3] == "]"


def test_diffuse_color_array_honours_indent():
    out = format_diffuse_color_array([(0.2, 0.2, 0.2)], indent="  ")
    assert out.startswith("  diffuseColor [ 1,\n")
    assert "\n  0.2000 0.2000 0.2000 ,\n" in out
    assert out.endswith("  ]\n")
