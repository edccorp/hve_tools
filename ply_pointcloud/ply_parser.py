import bpy
import struct

import numpy as np

__all__ = ["load_ply_vertices", "build_point_cloud_object", "import_ply"]



def _ply_parse_header(f):
    header_lines = []
    while True:
        line = f.readline()
        if not line:
            raise RuntimeError("Unexpected EOF while reading PLY header")
        line = line.decode('ascii', errors='ignore').strip()
        header_lines.append(line)
        if line == 'end_header':
            break
    fmt = None
    vertex_count = 0
    vertex_props = []
    in_vertex = False
    for line in header_lines:
        if line.startswith('format'):
            fmt = line.split()[1]
        elif line.startswith('element'):
            parts = line.split()
            in_vertex = (len(parts) >= 3 and parts[1] == 'vertex')
            if in_vertex:
                vertex_count = int(parts[2])
        elif line.startswith('property') and in_vertex:
            parts = line.split()
            if len(parts) >= 3:
                vertex_props.append((parts[1], parts[2]))
    if fmt not in ('ascii', 'binary_little_endian', 'binary_big_endian'):
        raise RuntimeError(
            f"Unsupported PLY format: {fmt}. "
            "Only ascii, binary_little_endian, binary_big_endian are supported"
        )
    return fmt, vertex_count, vertex_props


def _struct_fmt(ply_type):
    return {

        'char':'b','int8':'b','uchar':'B','uint8':'B',
        'short':'h','int16':'h','ushort':'H','uint16':'H',
        'int':'i','int32':'i','uint':'I','uint32':'I',
        'float':'f','float32':'f','double':'d','float64':'d'


    }[ply_type]


def _numpy_fmt(ply_type):
    return {
        'char': 'i1', 'int8': 'i1', 'uchar': 'u1', 'uint8': 'u1',
        'short': 'i2', 'int16': 'i2', 'ushort': 'u2', 'uint16': 'u2',
        'int': 'i4', 'int32': 'i4', 'uint': 'u4', 'uint32': 'u4',
        'float': 'f4', 'float32': 'f4', 'double': 'f8', 'float64': 'f8',
    }[ply_type]


def _color_indices(prop_names):
    """Return ``(rgb_indices_or_None, alpha_index_or_None)`` from property names."""
    cidx = None
    for r, g, b in [('red', 'green', 'blue'), ('r', 'g', 'b')]:
        if r in prop_names and g in prop_names and b in prop_names:
            cidx = (prop_names.index(r), prop_names.index(g), prop_names.index(b))
            break
    aidx = None
    for aname in ('alpha', 'a'):
        if aname in prop_names:
            aidx = prop_names.index(aname)
            break
    return cidx, aidx


def load_ply_vertices(filepath):
    """Load a PLY point cloud's vertices and colours.

    Returns ``(verts, cols)`` where ``verts`` is an (N, 3) float64 numpy array
    and ``cols`` is an (N, 4) float64 RGBA array (0-1) or None when the file has
    no colour. Binary bodies are parsed in one vectorized numpy read.
    """
    with open(filepath, 'rb') as f:
        if f.readline().decode('ascii', errors='ignore').strip() != 'ply':
            raise RuntimeError('Not a PLY file')
        fmt, vcount, vprops = _ply_parse_header(f)
        prop_names = [p[1] for p in vprops]
        ix, iy, iz = prop_names.index('x'), prop_names.index('y'), prop_names.index('z')
        cidx, aidx = _color_indices(prop_names)

        if fmt == 'ascii':
            verts = np.empty((vcount, 3), dtype=np.float64)
            cols = np.empty((vcount, 4), dtype=np.float64) if cidx else None
            for row_i in range(vcount):
                parts = f.readline().decode('ascii', errors='ignore').split()
                verts[row_i] = (float(parts[ix]), float(parts[iy]), float(parts[iz]))
                if cidx:
                    r, g, b = float(parts[cidx[0]]), float(parts[cidx[1]]), float(parts[cidx[2]])
                    if r > 1 or g > 1 or b > 1:
                        r, g, b = r / 255, g / 255, b / 255
                    if aidx is not None:
                        a = float(parts[aidx])
                        if a > 1:
                            a = a / 255
                    else:
                        a = 1.0
                    cols[row_i] = (r, g, b, a)
            return verts, cols

        if fmt in ('binary_little_endian', 'binary_big_endian'):
            endian = '<' if fmt == 'binary_little_endian' else '>'
            dt = np.dtype([(f"f{i}", endian + _numpy_fmt(t)) for i, (t, _n) in enumerate(vprops)])
            buf = f.read(dt.itemsize * vcount)
            arr = np.frombuffer(buf, dtype=dt, count=vcount)

            verts = np.column_stack([
                arr[f"f{ix}"].astype(np.float64),
                arr[f"f{iy}"].astype(np.float64),
                arr[f"f{iz}"].astype(np.float64),
            ])

            cols = None
            if cidx:
                def channel(idx):
                    vals = arr[f"f{idx}"].astype(np.float64)
                    # Integer colour channels (e.g. uchar 0-255) are normalized.
                    if np.issubdtype(dt[idx], np.integer):
                        vals = vals / 255.0
                    return vals

                r = channel(cidx[0])
                g = channel(cidx[1])
                b = channel(cidx[2])
                a = channel(aidx) if aidx is not None else np.ones(vcount, dtype=np.float64)
                cols = np.column_stack([r, g, b, a])
            return verts, cols

        raise RuntimeError(
            f"Unsupported PLY format: {fmt}. "
            "Only ascii, binary_little_endian, binary_big_endian are supported"
        )


def import_ply(filepath, setup_geonodes=False, point_radius=0.01, color_attribute="Col",
               display_subsample=100.0):
    """Import a PLY point cloud and optionally set up Geometry Nodes.

    Args:
        filepath: Path to the ``.ply`` file.
        setup_geonodes: When ``True``, create a basic point material,
            generate a Geometry Nodes group and assign it to the imported
            object before returning it. Defaults to ``False``.
        point_radius: Radius for point instances if ``setup_geonodes`` is
            enabled. Defaults to ``0.01``.
        color_attribute: Name of the vertex color attribute used by the
            material when ``setup_geonodes`` is enabled. Defaults to ``"Col"``.
        display_subsample: Percentage of points shown by the viewport display
            (display only; every point stays in the mesh data). Default 100.

    Returns:
        The newly created ``bpy.types.Object``.
    """
    verts, cols = load_ply_vertices(filepath)
    name = f"PLY_{bpy.path.display_name_from_filepath(filepath)}"
    return build_point_cloud_object(
        verts, cols, name, setup_geonodes=setup_geonodes, point_radius=point_radius,
        color_attribute=color_attribute, display_subsample=display_subsample,
    )


def build_point_cloud_object(verts, cols, name, setup_geonodes=False, point_radius=0.01,
                             color_attribute="Col", display_subsample=100.0):
    """Build a point-cloud mesh object from loaded vertices/colours.

    Shared by every importer (PLY / PTX / E57) so they all produce the same
    kind of object with the same Geometry Nodes + material setup.

    Args:
        verts: (N, 3) array of point positions.
        cols: (N, 4) RGBA array in 0-1, or ``None`` for no colour.
        name: Mesh/object name.
        setup_geonodes, point_radius, color_attribute, display_subsample: see
            :func:`import_ply`.

    Returns:
        The newly created ``bpy.types.Object``.
    """
    mesh = bpy.data.meshes.new(name=name)

    # Bulk-create the vertices (fast even for millions of points).
    n = len(verts)
    mesh.vertices.add(n)
    mesh.vertices.foreach_set("co", np.ascontiguousarray(verts, dtype=np.float32).ravel())
    mesh.update()
    mesh.validate(clean_customdata=False)

    if cols is not None and len(cols):
        try:
            ca = mesh.color_attributes.new(name=color_attribute, type='BYTE_COLOR', domain='POINT')
        except Exception:
            ca = mesh.color_attributes.new(name=color_attribute, type='FLOAT_COLOR', domain='POINT')
        ca.data.foreach_set("color", np.ascontiguousarray(cols, dtype=np.float32).ravel())

    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    if setup_geonodes:
        try:
            from .materials import make_point_material
            from .geonodes import make_geonodes_group, assign_geonodes_modifier
        except Exception:
            from materials import make_point_material
            from geonodes import make_geonodes_group, assign_geonodes_modifier

        mat_name = f"PointCloud_Color_{color_attribute}"
        mat = bpy.data.materials.get(mat_name) or make_point_material(mat_name, color_attribute)
        ng = make_geonodes_group("PCD_View_Geo", point_radius, mat, display_subsample)
        assign_geonodes_modifier(obj, ng, point_radius)
        if mat.name not in [m.name for m in obj.data.materials]:
            obj.data.materials.append(mat)
        obj.active_material = mat

    return obj
