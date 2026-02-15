import ast
import pathlib


module_path = pathlib.Path(__file__).resolve().parents[1] / "export_environment.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {}

for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == "get_environment_props":
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

get_environment_props = ns["get_environment_props"]


class Obj:
    pass


class EnvProps:
    def __init__(self):
        self.poName = "Gravel"
        self.poRateDamping = 0.33
        self.poFriction = 0.7
        self.poStaticWater = False


class EnvPropContainer:
    def __init__(self):
        self.set_env_props = EnvProps()


def test_get_environment_props_uses_defaults_when_props_missing():
    obj = Obj()

    props = get_environment_props(obj)

    assert props["poName"] == "Asphalt, Normal"
    assert props["poRateDamping"] == 0.5
    assert props["poFriction"] == 1


def test_get_environment_props_reads_pointer_properties_when_present():
    obj = Obj()
    obj.hve_env_props = EnvPropContainer()

    props = get_environment_props(obj)

    assert props["poName"] == "Gravel"
    assert props["poRateDamping"] == 0.33
    assert props["poFriction"] == 0.7
    assert props["poStaticWater"] is False
