import bpy
from bpy.props import (
        BoolProperty,
        EnumProperty,
        FloatProperty,
        StringProperty,
        )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper,
        axis_conversion,
        path_reference_mode,
        )
import os

def export_contact_surfaces(dirname, file, scale=39.3701):
    """Function to export contact surface data."""
    if not os.path.exists(dirname):
        os.makedirs(dirname)
        

    base_src = os.path.dirname(bpy.data.filepath)
    base_dst = os.path.dirname(file.name)
    filename_strip = os.path.splitext(os.path.basename(file.name))[0]

    txt_path = os.path.join(base_dst, f"{filename_strip}.txt")
    csv_path = os.path.join(base_dst, f"{filename_strip}.csv")

    worksheet = "HVE Contact Surfaces Worksheet\n\n\n"
    csvstr = ""

    for obj in bpy.context.selected_objects:
        if obj.type != "MESH":
            continue
        matrix = obj.matrix_world
        for facenum, face in enumerate(obj.data.polygons):
            worksheet += f"Contact Surface: \t{obj.name}_{facenum}\n"
            worksheet += "\nCoordinates (in):\n\t\t\t First\t\t Middle\t\t Third"
            facestr = f"{obj.name}_{facenum}"
            xs, ys, zs = [], [], []

            for vertnum, idx in enumerate(face.vertices[:3]):
                facestr += f",vert_{vertnum+1}"
                coords = matrix @ obj.data.vertices[idx].co

                def lengthenstr(value, scale=scale, minlen=7):
                    value = f"{value * scale:.1f}"
                    while len(value) < minlen:
                        value += " "
                    return value

                xs.append(lengthenstr(coords.x))
                ys.append(lengthenstr(coords.y*-1))
                zs.append(lengthenstr(coords.z*-1))
                facestr += f",{coords.x * scale:.4f},{coords.y *-1 * scale:.4f},{coords.z *-1 * scale:.4f}"

            worksheet += f"\n\t\t x:\t {xs[0]}\t {xs[1]}\t {xs[2]}\n"
            worksheet += f"\n\t\t y:\t {ys[0]}\t {ys[1]}\t {ys[2]}\n"
            worksheet += f"\n\t\t z:\t {zs[0]}\t {zs[1]}\t {zs[2]}\n\n\n"
            csvstr += facestr + "\n"

    with open(txt_path, "w") as f:
        f.write(worksheet)
    with open(csv_path, "w") as f:
        f.write(csvstr)

    txt_path4veh = os.path.join(base_dst, f"{filename_strip}_veh.txt")

    surfaces = []
    for obj in bpy.context.selected_objects:
        if obj.type != "MESH":
            continue
        matrix = obj.matrix_world
        for facenum, face in enumerate(obj.data.polygons):
            verts = face.vertices[:3]
            coords = [(matrix @ obj.data.vertices[i].co) for i in verts]
            coords_in = [(v.x * scale, -v.y * scale, -v.z * scale) for v in coords]
            surfaces.append({
                "name": f"{obj.name}_{facenum}",
                "coords": coords_in
            })

    with open(txt_path4veh, "w") as f:
        f.write("Vehicle Contact Surfaces Data\n")
        f.write("#       do not change  \n")
        f.write(f"  NumSurfaces           n/a             {len(surfaces)}\n")
        f.write(f"  BindTo                n/a             0\n")

        for surf in surfaces:
            f.write(f"                                        {surf['name']}\n")
            f.write(f"  Location                              0\n")
            for i, (x, y, z) in enumerate(surf['coords']):
                f.write(f"  Corner {i+1}                              {x:.1f} {y:.1f} {z:.1f}\n")
            f.write(f"                                        TestMaterial\n")
            f.write(f"  fConst, fLinear, fQuad, fCubic        0 982.8 -18 -3.4\n")
            f.write(f"  damping, friction, fMax, deflMax      .55 .5 1580 2.5\n")
            f.write(f"  fUnload, maxDX                        740.0 4.0\n")


    return txt_path, csv_path, txt_path4veh
    
def save(context,
         filepath,
         global_scale
         ):

    bpy.path.ensure_ext(filepath, '.csv')

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT') 
        
    file = open(filepath, 'w', encoding='utf-8')    
    dirname = os.path.dirname(filepath)        

    export_contact_surfaces(dirname, 
           file,
           global_scale,
           )

    return {'FINISHED'}

