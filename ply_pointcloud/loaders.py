"""Point-cloud file loaders for the importer.

Each ``load_*_vertices`` function returns ``(verts, cols)`` with the same shape
contract as :func:`ply_parser.load_ply_vertices`:

* ``verts`` — (N, 3) float64 numpy array of world-space point positions.
* ``cols``  — (N, 4) float64 RGBA array in 0-1, or ``None`` when the file
  carries no per-point colour.

The parse functions are free of ``bpy`` so they can be unit-tested directly;
:func:`import_point_cloud` is the ``bpy`` entry point that dispatches on the
file extension and builds the mesh object.
"""

import os

import numpy as np

from .ply_parser import load_ply_vertices

__all__ = [
    "load_ptx_vertices",
    "load_e57_vertices",
    "load_las_vertices",
    "load_point_cloud_vertices",
    "import_point_cloud",
    "SUPPORTED_EXTENSIONS",
]

SUPPORTED_EXTENSIONS = (".ply", ".ptx", ".e57", ".las", ".laz")


def _read_floats(line):
    return [float(v) for v in line.split()]


def _parse_ptx_block(f):
    """Parse one PTX cloud block from an open text file.

    Returns ``(verts, cols)`` for the block, or ``None`` at end of file.
    Points recorded as the scanner origin ``0 0 0`` (no laser return) are
    dropped. The block's 4x4 transform is applied so points land in world space.
    """
    # Skip blank lines, then read the two grid-dimension lines.
    line = f.readline()
    while line and not line.strip():
        line = f.readline()
    if not line:
        return None
    ncols = int(line.split()[0])
    nrows = int(f.readline().split()[0])
    npoints = ncols * nrows

    # 4 header lines describe the scanner (position + 3 orientation axes); the
    # next 4 lines are the 4x4 world transform (row-vector convention).
    for _ in range(4):
        f.readline()
    matrix = np.array([_read_floats(f.readline()) for _ in range(4)], dtype=np.float64)

    data = np.loadtxt(f, max_rows=npoints, ndmin=2)
    if data.size == 0:
        return np.empty((0, 3)), None

    verts = data[:, 0:3]
    # Drop no-return points (stored as the scanner origin).
    valid = ~np.all(verts == 0.0, axis=1)
    verts = verts[valid]

    # Apply the block transform: world = [x y z 1] @ M.
    verts = verts @ matrix[:3, :3] + matrix[3, :3]

    cols = None
    if data.shape[1] >= 7:
        rgb = data[valid, 4:7]
        if rgb.max() > 1.0:
            rgb = rgb / 255.0
        alpha = np.ones((len(rgb), 1), dtype=np.float64)
        cols = np.hstack([rgb, alpha])
    return verts, cols


def load_ptx_vertices(filepath):
    """Load a PTX point cloud (one or more concatenated scan blocks)."""
    blocks = []
    with open(filepath, "r") as f:
        while True:
            block = _parse_ptx_block(f)
            if block is None:
                break
            if len(block[0]):
                blocks.append(block)
    if not blocks:
        return np.empty((0, 3), dtype=np.float64), None

    verts = np.vstack([b[0] for b in blocks])
    if all(b[1] is not None for b in blocks):
        cols = np.vstack([b[1] for b in blocks])
    else:
        cols = None
    return verts, cols


def load_e57_vertices(filepath):
    """Load an E57 point cloud (all scans concatenated).

    E57 is a binary/XML container; parsing it reliably needs the ``pye57``
    package. When it is not installed a clear ``RuntimeError`` is raised so the
    operator can tell the user how to enable E57 support.
    """
    try:
        import pye57
    except ImportError as exc:
        raise RuntimeError(
            "E57 import needs the 'pye57' Python package, which is not "
            "installed in Blender's Python. Install it (e.g. `pip install "
            "pye57`) or convert the file to PLY/PTX first."
        ) from exc

    verts_parts = []
    cols_parts = []
    any_color = False
    with pye57.E57(filepath) as e57:
        scan_count = e57.scan_count
        for scan_index in range(scan_count):
            data = e57.read_scan(scan_index, ignore_missing_fields=True, colors=True)
            xyz = np.column_stack([
                np.asarray(data["cartesianX"], dtype=np.float64),
                np.asarray(data["cartesianY"], dtype=np.float64),
                np.asarray(data["cartesianZ"], dtype=np.float64),
            ])
            verts_parts.append(xyz)

            if "colorRed" in data and "colorGreen" in data and "colorBlue" in data:
                rgb = np.column_stack([
                    np.asarray(data["colorRed"], dtype=np.float64),
                    np.asarray(data["colorGreen"], dtype=np.float64),
                    np.asarray(data["colorBlue"], dtype=np.float64),
                ])
                if rgb.size and rgb.max() > 1.0:
                    rgb = rgb / 255.0
                alpha = np.ones((len(rgb), 1), dtype=np.float64)
                cols_parts.append(np.hstack([rgb, alpha]))
                any_color = True
            else:
                cols_parts.append(None)

    if not verts_parts:
        return np.empty((0, 3), dtype=np.float64), None

    verts = np.vstack(verts_parts)
    if any_color and all(c is not None for c in cols_parts):
        cols = np.vstack(cols_parts)
    else:
        cols = None
    return verts, cols


# Byte offset of the RGB block within a LAS point record, per Point Data Record
# Format ID. Formats not listed carry no colour.
_LAS_COLOR_OFFSET = {2: 20, 3: 28, 5: 28, 7: 30, 8: 30, 10: 30}


def _load_las_with_laspy(filepath):
    """Load a LAS/LAZ file via laspy. Returns (verts, cols) or raises ImportError."""
    import laspy

    las = laspy.read(filepath)
    verts = np.column_stack([
        np.asarray(las.x, dtype=np.float64),
        np.asarray(las.y, dtype=np.float64),
        np.asarray(las.z, dtype=np.float64),
    ])
    cols = None
    dims = set(las.point_format.dimension_names)
    if {"red", "green", "blue"} <= dims:
        rgb = np.column_stack([
            np.asarray(las.red, dtype=np.float64),
            np.asarray(las.green, dtype=np.float64),
            np.asarray(las.blue, dtype=np.float64),
        ])
        rgb = _normalize_rgb(rgb)
        alpha = np.ones((len(rgb), 1), dtype=np.float64)
        cols = np.hstack([rgb, alpha])
    return verts, cols


def _normalize_rgb(rgb):
    """Scale an RGB array to 0-1, guessing 16-bit vs 8-bit vs already-normalized."""
    if rgb.size == 0:
        return rgb
    mx = rgb.max()
    if mx > 255:
        return rgb / 65535.0
    if mx > 1:
        return rgb / 255.0
    return rgb


def load_las_vertices(filepath):
    """Load a LAS/LAZ point cloud.

    Uncompressed ``.las`` is read natively with numpy for the common Point Data
    Record Formats. Compressed ``.laz`` (and anything the native reader can't
    handle) is delegated to the ``laspy`` package if it is installed; otherwise
    a clear ``RuntimeError`` explains how to enable support.
    """
    import struct

    with open(filepath, "rb") as f:
        header = f.read(375)  # covers the largest (LAS 1.4) public header block
        if header[:4] != b"LASF":
            raise RuntimeError("Not a LAS file (missing 'LASF' signature).")

        version_major, version_minor = header[24], header[25]
        offset_to_points = struct.unpack_from("<I", header, 96)[0]
        point_format_raw = header[104]
        point_length = struct.unpack_from("<H", header, 105)[0]
        legacy_count = struct.unpack_from("<I", header, 107)[0]
        scale = struct.unpack_from("<3d", header, 131)
        offset = struct.unpack_from("<3d", header, 155)

        # LAS 1.4+ stores the authoritative 64-bit point count at offset 247;
        # earlier versions have a shorter header where that offset is invalid.
        point_count = legacy_count
        if (version_major, version_minor) >= (1, 4) and len(header) >= 255:
            count14 = struct.unpack_from("<Q", header, 247)[0]
            if count14:
                point_count = count14

        # The high bit of the format byte flags LAZ compression.
        compressed = bool(point_format_raw & 0x80)
        point_format = point_format_raw & 0x3F

        if compressed:
            try:
                return _load_las_with_laspy(filepath)
            except ImportError as exc:
                raise RuntimeError(
                    "LAZ (compressed LAS) import needs the 'laspy' package with "
                    "LAZ support (e.g. `pip install laspy[lazrs]`), or decompress "
                    "the file to .las first."
                ) from exc

        f.seek(offset_to_points)
        buf = f.read(point_length * point_count)

    names = ["X", "Y", "Z"]
    formats = ["<i4", "<i4", "<i4"]
    offsets = [0, 4, 8]
    color_off = _LAS_COLOR_OFFSET.get(point_format)
    if color_off is not None and color_off + 6 <= point_length:
        names += ["R", "G", "B"]
        formats += ["<u2", "<u2", "<u2"]
        offsets += [color_off, color_off + 2, color_off + 4]

    dt = np.dtype({
        "names": names, "formats": formats, "offsets": offsets,
        "itemsize": point_length,
    })
    n = len(buf) // point_length
    arr = np.frombuffer(buf, dtype=dt, count=n)

    verts = np.column_stack([
        arr["X"].astype(np.float64) * scale[0] + offset[0],
        arr["Y"].astype(np.float64) * scale[1] + offset[1],
        arr["Z"].astype(np.float64) * scale[2] + offset[2],
    ])

    cols = None
    if "R" in names:
        rgb = np.column_stack([
            arr["R"].astype(np.float64),
            arr["G"].astype(np.float64),
            arr["B"].astype(np.float64),
        ])
        rgb = _normalize_rgb(rgb)
        alpha = np.ones((len(rgb), 1), dtype=np.float64)
        cols = np.hstack([rgb, alpha])
    return verts, cols


_LOADERS = {
    ".ply": load_ply_vertices,
    ".ptx": load_ptx_vertices,
    ".e57": load_e57_vertices,
    ".las": load_las_vertices,
    ".laz": load_las_vertices,
}


def load_point_cloud_vertices(filepath):
    """Dispatch to the loader for ``filepath``'s extension. Returns (verts, cols)."""
    ext = os.path.splitext(filepath)[1].lower()
    loader = _LOADERS.get(ext)
    if loader is None:
        raise RuntimeError(
            f"Unsupported point-cloud format '{ext}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}."
        )
    return loader(filepath)


def import_point_cloud(filepath, setup_geonodes=False, point_radius=0.01,
                       color_attribute="Col", display_subsample=100.0):
    """Import any supported point-cloud file and build the mesh object.

    Mirrors :func:`ply_parser.import_ply` but dispatches on the file extension
    so PLY, PTX and E57 all flow through the same object/GeoNodes setup.
    """
    import bpy

    from .ply_parser import build_point_cloud_object

    verts, cols = load_point_cloud_vertices(filepath)
    stem = bpy.path.display_name_from_filepath(filepath)
    ext = os.path.splitext(filepath)[1].lower().lstrip(".").upper() or "PCD"
    name = f"{ext}_{stem}"
    return build_point_cloud_object(
        verts, cols, name, setup_geonodes=setup_geonodes, point_radius=point_radius,
        color_attribute=color_attribute, display_subsample=display_subsample,
    )
