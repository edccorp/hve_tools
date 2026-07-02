import ast
import os
import pathlib
import re
import struct
import tempfile


module_path = pathlib.Path(__file__).resolve().parents[1] / "hve_tools" / "fbx_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {"re": re, "struct": struct}

for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {
        "sanitize_cache_name",
        "write_mdd_file",
        "has_shape_key_animation",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)


sanitize_cache_name = ns["sanitize_cache_name"]
write_mdd_file = ns["write_mdd_file"]
has_shape_key_animation = ns["has_shape_key_animation"]


def test_sanitize_cache_name_replaces_unsafe_characters():
    assert sanitize_cache_name("Mesh: Truck/Main Body") == "Mesh_Truck_Main_Body"
    assert sanitize_cache_name("...") == "mesh_cache"


def test_write_mdd_file_writes_expected_header_and_payload():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "sample.mdd")
        frame_times = [0.0, 0.5]
        frame_vertex_positions = [
            [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
            [(1.5, 2.5, 3.5), (4.5, 5.5, 6.5)],
        ]

        write_mdd_file(filepath, frame_times, frame_vertex_positions)

        data = pathlib.Path(filepath).read_bytes()
        frame_count, point_count = struct.unpack(">2i", data[:8])
        assert (frame_count, point_count) == (2, 2)

        times = struct.unpack(">2f", data[8:16])
        assert times == (0.0, 0.5)

        payload = struct.unpack(">12f", data[16:])
        assert payload == (
            1.0,
            2.0,
            3.0,
            4.0,
            5.0,
            6.0,
            1.5,
            2.5,
            3.5,
            4.5,
            5.5,
            6.5,
        )


def test_write_mdd_file_rejects_inconsistent_vertex_counts():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "bad.mdd")
        try:
            write_mdd_file(
                filepath,
                [0.0, 1.0],
                [
                    [(0.0, 0.0, 0.0)],
                    [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)],
                ],
            )
        except ValueError as exc:
            assert "vertex count" in str(exc).lower()
        else:
            raise AssertionError("Expected write_mdd_file to reject mismatched samples.")


def test_has_shape_key_animation_detects_non_basis_keys():
    class KeyBlock:
        def __init__(self, name):
            self.name = name

    class ShapeKeys:
        def __init__(self, names):
            self.key_blocks = [KeyBlock(name) for name in names]

    class Mesh:
        def __init__(self, names):
            self.shape_keys = ShapeKeys(names) if names is not None else None

    class Obj:
        def __init__(self, names):
            self.data = Mesh(names)

    assert has_shape_key_animation(Obj(["Basis", "Smile"])) is True
    assert has_shape_key_animation(Obj(["Basis"])) is False
    assert has_shape_key_animation(Obj(None)) is False
