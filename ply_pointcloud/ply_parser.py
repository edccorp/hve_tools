import bpy
import struct

__all__ = ["load_ply_vertices", "import_ply"]



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


def load_ply_vertices(filepath):
    with open(filepath, 'rb') as f:
        if f.readline().decode('ascii', errors='ignore').strip() != 'ply':
            raise RuntimeError('Not a PLY file')
        fmt, vcount, vprops = _ply_parse_header(f)
        prop_names = [p[1] for p in vprops]
        ix, iy, iz = prop_names.index('x'), prop_names.index('y'), prop_names.index('z')
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
        verts = []
        cols = [] if cidx else None
        if fmt == 'ascii':
            for _ in range(vcount):
                parts = f.readline().decode('ascii', errors='ignore').split()
                verts.append((float(parts[ix]), float(parts[iy]), float(parts[iz])))
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
                    cols.append((r, g, b, a))
        elif fmt in ('binary_little_endian', 'binary_big_endian'):
            endian = '<' if fmt == 'binary_little_endian' else '>'
            row_struct = struct.Struct(endian + ''.join([_struct_fmt(t) for t, _ in vprops]))
            for _ in range(vcount):
                vals = row_struct.unpack(f.read(row_struct.size))
                verts.append((float(vals[ix]), float(vals[iy]), float(vals[iz])))
                if cidx:
                    r, g, b = float(vals[cidx[0]]), float(vals[cidx[1]]), float(vals[cidx[2]])
                    if r > 1 or g > 1 or b > 1:
                        r, g, b = r / 255, g / 255, b / 255
                    if aidx is not None:
                        a = float(vals[aidx])
                        if a > 1:
                            a = a / 255
                    else:
                        a = 1.0
                    cols.append((r, g, b, a))
        else:
            raise RuntimeError(
                f"Unsupported PLY format: {fmt}. "
                "Only ascii, binary_little_endian, binary_big_endian are supported"
            )
        return verts, cols


def import_ply(filepath, setup_geonodes=False, point_radius=0.01, color_attribute="Col"):
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

    Returns:
        The newly created ``bpy.types.Object``.
    """
    verts, cols = load_ply_vertices(filepath)
    mesh = bpy.data.meshes.new(name=f"PLY_{bpy.path.display_name_from_filepath(filepath)}")
    mesh.from_pydata(verts, [], [])
    mesh.validate(clean_customdata=False)
    if cols:
        try:
            ca = mesh.color_attributes.new(name=color_attribute, type='BYTE_COLOR', domain='POINT')
        except Exception:
            ca = mesh.color_attributes.new(name=color_attribute, type='FLOAT_COLOR', domain='POINT')
        for i, c in enumerate(cols):
            ca.data[i].color = c
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
        ng = make_geonodes_group("PCD_View_Geo", point_radius, mat)
        assign_geonodes_modifier(obj, ng, point_radius)
        if mat.name not in [m.name for m in obj.data.materials]:
            obj.data.materials.append(mat)
        obj.active_material = mat

    return obj
