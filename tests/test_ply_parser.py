import ast
import pathlib
import struct
import tempfile
import os

import pytest

np = pytest.importorskip("numpy")  # parser now returns numpy arrays


# Extract the bpy-free PLY parsing helpers from ply_pointcloud/ply_parser.py.
module_path = pathlib.Path(__file__).resolve().parents[1] / "point_cloud_tools" / "ply_pointcloud" / "ply_parser.py"
module_ast = ast.parse(module_path.read_text())

WANTED = {"_ply_parse_header", "_struct_fmt", "_numpy_fmt", "_color_indices", "load_ply_vertices"}
ns = {"struct": struct, "np": np}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANTED:
        exec(compile(ast.Module([node], []), filename="<ast>", mode="exec"), ns)

load_ply_vertices = ns["load_ply_vertices"]


def _write(tmpdir, name, data, binary=False):
    path = os.path.join(tmpdir, name)
    with open(path, "wb" if binary else "w") as fh:
        fh.write(data)
    return path


def test_ascii_ply_with_byte_colors_normalized():
    ply = (
        "ply\n"
        "format ascii 1.0\n"
        "element vertex 2\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
        "0 0 0 255 0 0\n"
        "1 2 3 0 255 0\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_ply_vertices(_write(tmp, "a.ply", ply))
    assert verts.tolist() == [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]
    # 0-255 byte colours are normalized to 0-1, alpha defaults to 1.
    assert cols.tolist() == [[1.0, 0.0, 0.0, 1.0], [0.0, 1.0, 0.0, 1.0]]


def test_ascii_ply_without_color():
    ply = (
        "ply\nformat ascii 1.0\nelement vertex 1\n"
        "property float x\nproperty float y\nproperty float z\nend_header\n"
        "5 6 7\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_ply_vertices(_write(tmp, "b.ply", ply))
    assert verts.tolist() == [[5.0, 6.0, 7.0]]
    assert cols is None


def test_binary_little_endian_ply():
    header = (
        "ply\nformat binary_little_endian 1.0\nelement vertex 1\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
    ).encode("ascii")
    body = struct.pack("<fffBBB", 1.0, 2.0, 3.0, 255, 128, 0)
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_ply_vertices(_write(tmp, "c.ply", header + body, binary=True))
    assert verts.tolist() == [[1.0, 2.0, 3.0]]
    assert cols[0][0] == 1.0
    assert abs(cols[0][1] - 128 / 255) < 1e-6
    assert cols[0][3] == 1.0


def test_binary_big_endian_matches_little_endian():
    def make(endian_word, pack):
        header = (
            f"ply\nformat {endian_word} 1.0\nelement vertex 1\n"
            "property float x\nproperty float y\nproperty float z\nend_header\n"
        ).encode("ascii")
        return header + pack
    with tempfile.TemporaryDirectory() as tmp:
        le = load_ply_vertices(_write(tmp, "le.ply", make("binary_little_endian", struct.pack("<fff", 1, 2, 3)), binary=True))[0]
        be = load_ply_vertices(_write(tmp, "be.ply", make("binary_big_endian", struct.pack(">fff", 1, 2, 3)), binary=True))[0]
    assert le.tolist() == be.tolist() == [[1.0, 2.0, 3.0]]


def test_rejects_non_ply():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, "d.txt", "not a ply\n")
        try:
            load_ply_vertices(path)
        except RuntimeError:
            return
    raise AssertionError("Expected RuntimeError for a non-PLY file")
