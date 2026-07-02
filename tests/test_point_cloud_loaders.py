import ast
import pathlib
import struct
import os
import tempfile

import pytest

np = pytest.importorskip("numpy")


# Extract the bpy-free loader helpers from ply_pointcloud/loaders.py without
# importing the package (which pulls in bpy via ply_parser).
module_path = pathlib.Path(__file__).resolve().parents[1] / "ply_pointcloud" / "loaders.py"
module_ast = ast.parse(module_path.read_text())

WANTED_FUNCS = {
    "_read_floats", "_parse_ptx_block", "load_ptx_vertices",
    "_normalize_rgb", "load_las_vertices", "missing_optional_deps",
    "deps_for_extension", "_pcd_unpack_rgb", "load_pcd_vertices",
}
WANTED_ASSIGN = {"_LAS_COLOR_OFFSET", "OPTIONAL_DEPS", "_EXTENSION_DEP", "_PCD_NUMPY"}

ns = {"os": os, "struct": struct, "np": np}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANTED_FUNCS:
        exec(compile(ast.Module([node], []), "<ast>", "exec"), ns)
    elif isinstance(node, ast.Assign):
        targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if targets & WANTED_ASSIGN:
            exec(compile(ast.Module([node], []), "<ast>", "exec"), ns)

load_ptx_vertices = ns["load_ptx_vertices"]
load_las_vertices = ns["load_las_vertices"]
load_pcd_vertices = ns["load_pcd_vertices"]
missing_optional_deps = ns["missing_optional_deps"]
deps_for_extension = ns["deps_for_extension"]
OPTIONAL_DEPS = ns["OPTIONAL_DEPS"]


def _write(tmp, name, data, binary=False):
    path = os.path.join(tmp, name)
    with open(path, "wb" if binary else "w") as fh:
        fh.write(data)
    return path


# --- PTX ---------------------------------------------------------------------

def _ptx_identity_header(ncols, nrows):
    return (
        f"{ncols}\n{nrows}\n"
        "0 0 0\n"          # scanner position
        "1 0 0\n0 1 0\n0 0 1\n"  # orientation axes
        "1 0 0 0\n0 1 0 0\n0 0 1 0\n0 0 0 1\n"  # 4x4 identity transform
    )


def test_ptx_with_color_drops_origin_points():
    body = (
        _ptx_identity_header(2, 2)
        + "0 0 0 0 0 0 0\n"        # scanner-origin no-return -> dropped
        + "1 2 3 0.5 255 0 0\n"    # red
        + "4 5 6 0.5 0 255 0\n"    # green
        + "0 0 0 0.5 0 0 255\n"    # origin again -> dropped
    )
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_ptx_vertices(_write(tmp, "s.ptx", body))
    assert verts.tolist() == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert cols.tolist() == [[1.0, 0.0, 0.0, 1.0], [0.0, 1.0, 0.0, 1.0]]


def test_ptx_applies_transform():
    # A transform that translates by (10, 20, 30).
    header = (
        "1\n1\n0 0 0\n1 0 0\n0 1 0\n0 0 1\n"
        "1 0 0 0\n0 1 0 0\n0 0 1 0\n10 20 30 1\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_ptx_vertices(_write(tmp, "t.ptx", header + "1 1 1 0.2\n"))
    assert verts.tolist() == [[11.0, 21.0, 31.0]]
    assert cols is None  # no RGB columns


def test_ptx_multiple_blocks_concatenate():
    body = (
        _ptx_identity_header(1, 1) + "1 0 0 0.1 255 255 255\n"
        + _ptx_identity_header(1, 1) + "0 2 0 0.1 0 0 0\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_ptx_vertices(_write(tmp, "m.ptx", body))
    assert verts.tolist() == [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0]]
    assert cols.shape == (2, 4)


# --- LAS ---------------------------------------------------------------------

def _make_las(points, colors=None, version=(1, 2)):
    """Build a minimal uncompressed LAS file.

    points: list of (x, y, z) in file units. colors: list of (r, g, b) 16-bit or
    None. Uses point format 2 (with RGB) when colors given, else format 0.
    """
    scale = (0.01, 0.01, 0.01)
    offset = (0.0, 0.0, 0.0)
    if colors is not None:
        point_format = 2
        point_length = 26  # format 0 core (20) + RGB (6)
    else:
        point_format = 0
        point_length = 20
    header_size = 227
    header = bytearray(header_size)
    header[0:4] = b"LASF"
    header[24] = version[0]
    header[25] = version[1]
    struct.pack_into("<H", header, 94, header_size)
    struct.pack_into("<I", header, 96, header_size)  # offset to point data
    header[104] = point_format
    struct.pack_into("<H", header, 105, point_length)
    struct.pack_into("<I", header, 107, len(points))
    struct.pack_into("<3d", header, 131, *scale)
    struct.pack_into("<3d", header, 155, *offset)

    body = bytearray()
    for i, (x, y, z) in enumerate(points):
        rec = bytearray(point_length)
        struct.pack_into("<3i", rec, 0,
                         int(round(x / scale[0])),
                         int(round(y / scale[1])),
                         int(round(z / scale[2])))
        if colors is not None:
            struct.pack_into("<3H", rec, 20, *colors[i])
        body += rec
    return bytes(header) + bytes(body)


def test_las_format0_no_color():
    data = _make_las([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)])
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_las_vertices(_write(tmp, "a.las", data, binary=True))
    assert np.allclose(verts, [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    assert cols is None


def test_las_format2_with_16bit_color():
    data = _make_las(
        [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)],
        colors=[(65535, 0, 0), (0, 65535, 0)],
    )
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_las_vertices(_write(tmp, "b.las", data, binary=True))
    assert np.allclose(verts, [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
    assert np.allclose(cols, [[1.0, 0.0, 0.0, 1.0], [0.0, 1.0, 0.0, 1.0]])


def test_las_rejects_non_las():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, "c.bin", b"NOPE" + bytes(400), binary=True)
        with pytest.raises(RuntimeError):
            load_las_vertices(path)


# --- Optional dependency detection -------------------------------------------

def test_optional_deps_shape():
    # Each entry is (import_name, pip_spec, format_label); PLY/PTX/LAS need none.
    names = {dep[0] for dep in OPTIONAL_DEPS}
    assert names == {"pye57", "laspy"}
    for import_name, pip_spec, fmt in OPTIONAL_DEPS:
        assert isinstance(import_name, str) and import_name
        assert isinstance(pip_spec, str) and pip_spec
        assert isinstance(fmt, str) and fmt


def test_missing_optional_deps_reports_absent_package():
    # A guaranteed-absent import name must be reported as missing; a present one
    # (the stdlib 'os') must not. Patch OPTIONAL_DEPS in the extracted namespace.
    ns["OPTIONAL_DEPS"] = (
        ("definitely_not_a_real_pkg_xyz", "definitely_not_a_real_pkg_xyz", "FOO"),
        ("os", "os", "BAR"),
    )
    try:
        missing = ns["missing_optional_deps"]()
    finally:
        ns["OPTIONAL_DEPS"] = OPTIONAL_DEPS
    reported = {dep[0] for dep in missing}
    assert "definitely_not_a_real_pkg_xyz" in reported
    assert "os" not in reported


def test_deps_for_extension_native_formats_need_nothing():
    for ext in (".ply", ".ptx", ".las", ".PLY", ".LAS"):
        assert deps_for_extension(ext) == []


def test_deps_for_extension_maps_e57_and_laz():
    # pye57/laspy aren't installed in the test env, so these report the need.
    e57 = deps_for_extension(".e57")
    laz = deps_for_extension(".LAZ")  # case-insensitive
    assert [d[0] for d in e57] == ["pye57"]
    assert [d[0] for d in laz] == ["laspy"]


# --- PCD ---------------------------------------------------------------------

def _pcd_header(n, data_kind, fields="x y z rgb", size="4 4 4 4", typ="F F F F", count="1 1 1 1"):
    return (
        "# .PCD v0.7\nVERSION 0.7\n"
        f"FIELDS {fields}\nSIZE {size}\nTYPE {typ}\nCOUNT {count}\n"
        f"WIDTH {n}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\n"
        f"POINTS {n}\nDATA {data_kind}\n"
    )


def _rgb_float(r, g, b):
    packed = (int(r) << 16) | (int(g) << 8) | int(b)
    return struct.unpack("<f", struct.pack("<I", packed))[0]


def test_pcd_ascii_with_packed_rgb():
    body = (
        _pcd_header(2, "ascii")
        + f"1 2 3 {_rgb_float(255, 0, 0)!r}\n"
        + f"4 5 6 {_rgb_float(0, 255, 0)!r}\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_pcd_vertices(_write(tmp, "a.pcd", body))
    assert verts.tolist() == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert np.allclose(cols, [[1.0, 0.0, 0.0, 1.0], [0.0, 1.0, 0.0, 1.0]])


def test_pcd_ascii_without_color():
    body = _pcd_header(1, "ascii", fields="x y z", size="4 4 4", typ="F F F", count="1 1 1") + "7 8 9\n"
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_pcd_vertices(_write(tmp, "b.pcd", body))
    assert verts.tolist() == [[7.0, 8.0, 9.0]]
    assert cols is None


def test_pcd_binary_with_packed_rgb():
    header = _pcd_header(2, "binary").encode("ascii")
    body = (
        struct.pack("<ffff", 1.0, 2.0, 3.0, _rgb_float(0, 0, 255))
        + struct.pack("<ffff", 4.0, 5.0, 6.0, _rgb_float(255, 255, 255))
    )
    with tempfile.TemporaryDirectory() as tmp:
        verts, cols = load_pcd_vertices(_write(tmp, "c.pcd", header + body, binary=True))
    assert np.allclose(verts, [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    assert np.allclose(cols, [[0.0, 0.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0]])
