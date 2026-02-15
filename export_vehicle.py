# ##### 
"""
This script exports to H3D format.

Usage:
Run this script from "File->Export" menu.  A pop-up will ask whether you
want to export only selected or all relevant objects.


"""

import math
import os
import re

import bpy
import bmesh
import mathutils

from bpy_extras.io_utils import create_derived_objects #, free_derived_objects
from bpy_extras.node_shader_utils import PrincipledBSDFWrapper
from bpy_extras.node_shader_utils import ShaderImageTextureWrapper

def clight_color(col):
    return tuple([max(min(c, 1.0), 0.0) for c in col])


def matrix_direction_neg_z(matrix):
    return (matrix.to_3x3() @ mathutils.Vector((0.0, 0.0, -1.0))).normalized()[:]


def prefix_quoted_str(value, prefix):
    return value[0] + prefix + value[1:]


def suffix_quoted_str(value, suffix):
    return value[:-1] + suffix + value[-1:]


def bool_as_str(value):
    return ('false', 'true')[bool(value)]


def get_vehicle_light_type(obj):
    """Return an object's configured HVE light type when available."""
    vehicle_light = getattr(obj, 'hve_vehicle_light', None)
    if vehicle_light is None:
        return None

    make_light = getattr(vehicle_light, 'make_light', None)
    if make_light is None:
        return None

    return getattr(make_light, 'type', None)


def extract_switch_material_names(light_text):
    """Return material identifiers used by switch entries in a light block."""
    return re.findall(r'\{USE\s+([^}]+)\}', light_text or "")


def get_vehicle_light_switch_text(light_type):
    """Return the HVE switch block text for a configured vehicle light type."""
    light_switch_text = {
        "HVE_HEADLIGHT_LEFT": "#HVE_HEADLIGHT_LEFT \n    DEF HVE_LIGHT_HEADLIGHT_LEFT_Low Switch {USE LIGHT_WHITE_LO}\n    DEF HVE_LIGHT_HEADLIGHT_LEFT_High Switch {USE LIGHT_WHITE_HI}\n",
        "HVE_HEADLIGHT_RIGHT": "#HVE_HEADLIGHT_RIGHT \n    DEF HVE_LIGHT_HEADLIGHT_RIGHT_Low Switch {USE LIGHT_WHITE_LO}\n    DEF HVE_LIGHT_HEADLIGHT_RIGHT_High Switch {USE LIGHT_WHITE_HI}\n",
        "HVE_REVERSE_LEFT": "#HVE_REVERSE_LEFT \n    DEF HVE_LIGHT_BACKUPLIGHT_LEFT Switch {USE LIGHT_WHITE_ON}\n",
        "HVE_REVERSE_RIGHT": "#HVE_REVERSE_RIGHT \n    DEF HVE_LIGHT_BACKUPLIGHT_RIGHT Switch {USE LIGHT_WHITE_ON}\n",
        "HVE_FOGLIGHT_LEFT": "#HVE_FOGLIGHT_LEFT \n    DEF HVE_LIGHT_HEADLIGHT_LEFT_Fog Switch {USE LIGHT_WHITE_ON}\n",
        "HVE_FOGLIGHT_RIGHT": "#HVE_FOGLIGHT_RIGHT \n    DEF HVE_LIGHT_HEADLIGHT_RIGHT_Fog Switch {USE LIGHT_WHITE_ON}\n",
        "HVE_AMBERTURN_LEFT": "#HVE_AMBERTURN_LEFT \n    DEF HVE_LIGHT_RUNNINGLIGHT_FRONT_LEFT Switch {USE LIGHT_AMBER_LO}\n    DEF HVE_LIGHT_SIGNALLIGHT_FRONT_LEFT Switch {USE LIGHT_AMBER_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_FRONT_LEFT Switch {USE LIGHT_AMBER_HI}\n",
        "HVE_AMBERTURN_RIGHT": "#HVE_AMBERTURN_RIGHT \n    DEF HVE_LIGHT_RUNNINGLIGHT_FRONT_RIGHT Switch {USE LIGHT_AMBER_LO}\n    DEF HVE_LIGHT_SIGNALLIGHT_FRONT_RIGHT Switch {USE LIGHT_AMBER_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_FRONT_RIGHT Switch {USE LIGHT_AMBER_HI}\n",
        "HVE_AMBERTAIL_LEFT": "#HVE_AMBERTAIL_LEFT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_LEFT Switch {USE LIGHT_AMBER_LO}\n    DEF HVE_LIGHT_SIGNALLIGHT_REAR_LEFT Switch {USE LIGHT_AMBER_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_REAR_LEFT Switch {USE LIGHT_AMBER_HI}\n",
        "HVE_AMBERTAIL_RIGHT": "#HVE_AMBERTAIL_RIGHT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_RIGHT Switch {USE LIGHT_AMBER_LO}\n    DEF HVE_LIGHT_SIGNALLIGHT_REAR_RIGHT Switch {USE LIGHT_AMBER_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_REAR_RIGHT Switch {USE LIGHT_AMBER_HI}\n",
        "HVE_BRAKETURN_LEFT": "#HVE_BRAKETURN_LEFT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_LEFT Switch {USE LIGHT_RED_LO}\n    DEF HVE_LIGHT_BRAKELIGHT_REAR_LEFT Switch {USE LIGHT_RED_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_REAR_LEFT Switch {USE LIGHT_RED_HI}\n    DEF HVE_LIGHT_SIGNALLIGHT_REAR_LEFT Switch {USE LIGHT_RED_HI}\n",
        "HVE_BRAKETURN_RIGHT": "#HVE_BRAKETURN_RIGHT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_RIGHT Switch {USE LIGHT_RED_LO}\n    DEF HVE_LIGHT_BRAKELIGHT_REAR_RIGHT Switch {USE LIGHT_RED_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_REAR_RIGHT Switch {USE LIGHT_RED_HI}\n    DEF HVE_LIGHT_SIGNALLIGHT_REAR_RIGHT Switch {USE LIGHT_RED_HI}\n",
        "HVE_BRAKE_LEFT": "#HVE_BRAKE_LEFT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_LEFT Switch {USE LIGHT_RED_LO}\n    DEF HVE_LIGHT_BRAKELIGHT_REAR_LEFT Switch {USE LIGHT_RED_HI}\n",
        "HVE_BRAKE_RIGHT": "#HVE_BRAKE_RIGHT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_RIGHT Switch {USE LIGHT_RED_LO}\n    DEF HVE_LIGHT_BRAKELIGHT_REAR_RIGHT Switch {USE LIGHT_RED_HI}\n",
        "HVE_BRAKE_CENTER": "#HVE_BRAKE_CENTER \n    DEF HVE_LIGHT_BRAKELIGHT_CENTER Switch {USE LIGHT_RED_HI}\n",
    }
    return light_switch_text.get(light_type, "")


def clean_def(txt):
    # see report [#28256]
    print("text " + txt)
    if not txt:
        txt = "None"
    # no digit start
    if txt[0] in "1234567890+-":
        txt = "_" + txt
    return txt.translate({
        # control characters 0x0-0x1f
        # 0x00: "_",
        0x01: "_",
        0x02: "_",
        0x03: "_",
        0x04: "_",
        0x05: "_",
        0x06: "_",
        0x07: "_",
        0x08: "_",
        0x09: "_",
        0x0a: "_",
        0x0b: "_",
        0x0c: "_",
        0x0d: "_",
        0x0e: "_",
        0x0f: "_",
        0x10: "_",
        0x11: "_",
        0x12: "_",
        0x13: "_",
        0x14: "_",
        0x15: "_",
        0x16: "_",
        0x17: "_",
        0x18: "_",
        0x19: "_",
        0x1a: "_",
        0x1b: "_",
        0x1c: "_",
        0x1d: "_",
        0x1e: "_",
        0x1f: "_",

        0x7f: "_",  # 127

        0x20: "_",  # space
        0x22: "_",  # "
        0x27: "_",  # '
        0x23: "_",  # #
        0x2c: "_",  # ,
        0x2e: "_",  # .
        0x5b: "_",  # [
        0x5d: "_",  # ]
        0x5c: "_",  # \
        0x7b: "_",  # {
        0x7d: "_",  # }
        })


def find_material_by_switch_id(materials, switch_material_id):
    """Resolve a Blender material matching a switch material identifier."""
    for material in materials:
        if material.name == switch_material_id:
            return material
        if clean_def(material.name) == switch_material_id:
            return material
    return None


def active_color_layer(mesh):
    """Return active color data layer across Blender 3.x/4.x APIs."""
    if hasattr(mesh, "vertex_colors") and mesh.vertex_colors:
        layer = mesh.vertex_colors.active
        if layer is not None:
            return layer

    color_attrs = getattr(mesh, "color_attributes", None)
    if color_attrs:
        layer = color_attrs.active_color
        if layer is not None and getattr(layer, "domain", None) == 'CORNER':
            return layer
        layer = color_attrs.render_color_index if hasattr(color_attrs, 'render_color_index') else None
        if isinstance(layer, int) and 0 <= layer < len(color_attrs):
            cand = color_attrs[layer]
            if getattr(cand, "domain", None) == 'CORNER':
                return cand
        for cand in color_attrs:
            if getattr(cand, "domain", None) == 'CORNER':
                return cand
    return None


def build_hierarchy(objects):
    """ returns parent child relationships, skipping
    """
    objects_set = set(objects)
    par_lookup = {}

    def test_parent(parent):
        while (parent is not None) and (parent not in objects_set):
            parent = parent.parent
        return parent

    for obj in objects:
        par_lookup.setdefault(test_parent(obj.parent), []).append((obj, []))

    for parent, children in par_lookup.items():
        for obj, subchildren in children:
            subchildren[:] = par_lookup.get(obj, [])

    return par_lookup.get(None, [])


# -----------------------------------------------------------------------------
# Functions for writing output file
# -----------------------------------------------------------------------------

def export(file, dirname,
           global_matrix,
           depsgraph,
           scene,
           view_layer,
           use_mesh_modifiers=True,
           use_selection=True,
           use_normals=False,
           use_hierarchy=True,
           path_mode='AUTO',
           name_decorations=True,
           ):

    # -------------------------------------------------------------------------
    # Global Setup
    # -------------------------------------------------------------------------
    import bpy_extras
    from bpy_extras.io_utils import unique_name
    from xml.sax.saxutils import quoteattr, escape

    if name_decorations:
        # If names are decorated, the uuid map can be split up
        # by type for efficiency of collision testing
        # since objects of different types will always have
        # different decorated names.
        uuid_cache_object = {}    # object
        uuid_cache_light = {}      # 'LA_' + object.name
        uuid_cache_view = {}      # object, different namespace
        uuid_cache_mesh = {}      # mesh
        uuid_cache_material = {}  # material
        uuid_cache_image = {}     # image
        uuid_cache_world = {}     # world
        CA_ = 'CA_'
        OB_ = 'OB_'
        ME_ = 'ME_'
        IM_ = 'IM_'
        WO_ = 'WO_'
        MA_ = 'MA_'
        LA_ = 'LA_'
        group_ = 'group_'
    else:
        # If names are not decorated, it may be possible for two objects to
        # have the same name, so there has to be a unified dictionary to
        # prevent uuid collisions.
        uuid_cache = {}
        uuid_cache_object = uuid_cache           # object
        uuid_cache_light = uuid_cache             # 'LA_' + object.name
        uuid_cache_view = uuid_cache             # object, different namespace
        uuid_cache_mesh = uuid_cache             # mesh
        uuid_cache_material = uuid_cache         # material
        uuid_cache_image = uuid_cache            # image
        uuid_cache_world = uuid_cache            # world
        del uuid_cache
        CA_ = ''
        OB_ = ''
        ME_ = ''
        IM_ = ''
        WO_ = ''
        MA_ = ''
        LA_ = ''
        group_ = ''

    _TRANSFORM = '_TRANSFORM'

    # store files to copy
    copy_set = set()

    fw = file.write
    base_src = os.path.dirname(bpy.data.filepath)
    base_dst = os.path.dirname(file.name)
    filename_strip = os.path.splitext(os.path.basename(file.name))[0]
    gpu_shader_cache = {}

    # -------------------------------------------------------------------------
    # File Writing Functions
    # -------------------------------------------------------------------------

    def writeHeader(ident, material, material_id_index, world, image, objects):
        print("HEADER")
        filepath_quoted = quoteattr(os.path.basename(file.name))
        blender_ver_quoted = quoteattr('Blender %s' % bpy.app.version_string)

            
        fw("#Inventor V2.1 ascii\n\n")
        fw("  Info {\n")         
        #fw("  #string \"HVE VERSION 1.0 FILE\"\n")
        fw("}\n")       
        fw("Separator\n")
        fw("{\n")
        fw('Transform { #beginGlobalTransform\n')
        fw('translation 0.000000 0.000000 0.000000\n')        
        fw('scaleFactor 1.000000 1.000000 1.000000\n')
        fw('rotation 0.000000 1.000000 0.000000 0.000000\n')
        fw('} #endGlobalTransform\n')                                            
        fw("  ShapeHints\n")
        fw("  {\n")
        fw("    vertexOrdering COUNTERCLOCKWISE\n")
        fw("    creaseAngle 0.5")
        fw("  }\n")
        fw("  Separator {\n")

        ident = '  '         
        materials2write = []
        for obj in objects:
            material_slots = obj.material_slots
            for m in material_slots:
                material = m.material
                if material not in materials2write:
                    materials2write.append(material)

        #mat_list = bpy.data.materials
        for idx, material in enumerate(materials2write):
            writeMaterial(ident, material, material_id_index, world, image)
        fw("  }\n")
       
        return ident

        
    def writeFooter(ident):
        print("FOOTER")
        #fw("}\n")
        #missing closing brace somewhere
        fw("}\n")       
        return ident

    def writeTransform_begin(ident, matrix, def_id):
        print("TRANSFORM_BEGIN")
        ident = ident + '  '
        fw("%s# %s\n" % (ident, def_id))
        if def_id is not None:
            fw('%sDEF %s\n' % (ident, def_id))
        else:
            fw('\n')
        fw('%sTransform { #beginTransform\n' % ident)
        ident_step = ident + '          '
        loc, rot, sca = matrix.decompose()
        rot = rot.to_axis_angle()
        rot = (*rot[0], rot[1])
        print ("Rotation")
        print (rot)
        fw(ident_step + 'translation %.6f %.6f %.6f\n' % loc[:])
        # fw(ident_step + 'center %.6f %.6f %.6f\n' % (0, 0, 0))
        fw(ident_step + 'scaleFactor %.6f %.6f %.6f\n' % sca[:])
        fw(ident_step + 'rotation %.6f %.6f %.6f %.16f\n' % rot)
        fw(ident_step + '} #endTransform\n')
        ident += '\t'
        return ident

    def writeTransform_end(ident):
        print("TRANSFORM_END")
        ident = ident[:-1]
        fw('%s\n' % ident)
        return ident

    def write_vehicle_light_switch(ident, obj, material_id_index, world, image):
        light_switch_prop = get_vehicle_light_type(obj)
        if light_switch_prop is None:
            return None

        light_text = get_vehicle_light_switch_text(light_switch_prop)
        if not light_text:
            return None

        for matname in extract_switch_material_names(light_text):
            material = find_material_by_switch_id(bpy.data.materials, matname)
            if material is not None:
                writeMaterial(
                    ident,
                    material,
                    material_id_index,
                    world,
                    image,
                    material_def_name=matname,
                )

        return light_text


    def writeIndexedFaceSet(ident, obj, mesh, matrix, world, material_id_index):
        print("INDEXED_FACE")
        obj_id = unique_name(obj, OB_ + obj.name, uuid_cache_object, clean_func=clean_def, sep="_")
        # Meshes generated for export may share Blender's internal names;
        # base the exported identifier on the object name instead.
        mesh_id = unique_name(mesh, ME_ + obj.name, uuid_cache_mesh, clean_func=clean_def, sep="_")
        mesh_id_group = mesh_id + 'group_'
        mesh_id_coords = mesh_id + 'coords_'
        mesh_id_normals = mesh_id + 'normals_'

        me = obj.data 
        bm = bmesh.new()
        bm.from_mesh(me)

        for edge in bm.edges:
            if not edge.smooth:
                use_normals_obj = True
            else:    
                use_normals_obj = False
        bm.to_mesh(me)
        bm.free()
        
        ident = writeTransform_begin(ident, matrix, obj_id + '_ifs' + _TRANSFORM)

        if mesh.tag:
            fw('%sUSE %s \n' % (ident, mesh_id_group))
            fw('%sGroup { #beginMeshIdGroup\n' % (ident))
        else:
            mesh.tag = True
            fw('%sDEF %s \n'  % (ident, mesh_id_group))
            fw('%sGroup { #beginMeshIdGroup\n' % (ident))
            ident += '\t'

            is_uv = bool(mesh.uv_layers.active)

            is_coords_written = False

            mesh_materials = mesh.materials[:]
            if not mesh_materials:
                mesh_materials = [None]
            mesh_material_tex = [None] * len(mesh_materials)
            mesh_material_mtex = [None] * len(mesh_materials)
            mesh_material_images = [None] * len(mesh_materials)

            for i, material in enumerate(mesh_materials):
                if material:
                    if material.use_nodes == True:
                        nodes = material.node_tree.nodes 
                        principled = PrincipledBSDFWrapper(material, is_readonly=True)
                        tex_principled = principled.base_color_texture
                        print(material)
                        print(principled)
                        print(tex_principled)
                        if principled:
                            principled_key = "base_color_texture"					
                            tex_principled = getattr(principled,principled_key, None)                           
                            if tex_principled is not None:
                                if tex_principled.image:
                                    #mesh_material_tex[i] = tex_principled
                                    print(tex_principled)
                                    print(tex_principled.image)
                                    mesh_material_mtex[i] = tex_principled
                                    mesh_material_images[i] = tex_principled.image
                        #IF NODES ARE THERE FOR HVE
                        hveTexture = nodes.get("hveTexture", None)
                        if hveTexture is not None:
                            hveTexture = nodes.get("hveTexture")
                            print(hveTexture)
                            mesh_material_mtex[i] = tex_principled
                            mesh_material_images[i] = hveTexture.image
                        else:
                            print("no hveTexture")
            # fast access!
            mesh_vertices = mesh.vertices[:]
            mesh_loops = mesh.loops[:]
            mesh_polygons = mesh.polygons[:]
            mesh_polygons_materials = [p.material_index for p in mesh_polygons]
            mesh_polygons_vertices = [p.vertices[:] for p in mesh_polygons]

            if len(set(mesh_material_images)) > 0:  # make sure there is at least one image
                mesh_polygons_image = [mesh_material_images[material_index] for material_index in mesh_polygons_materials]
            else:
                mesh_polygons_image = [None] * len(mesh_polygons)

            mesh_polygons_image_unique = set(mesh_polygons_image)

            # group faces
            polygons_groups = {}
            for material_index in range(len(mesh_materials)):
                for image in mesh_polygons_image_unique:
                    polygons_groups[material_index, image] = []
            del mesh_polygons_image_unique

            for i, (material_index, image) in enumerate(zip(mesh_polygons_materials, mesh_polygons_image)):
                polygons_groups[material_index, image].append(i)

            color_layer = active_color_layer(mesh)
            is_col = color_layer is not None
            mesh_loops_col = color_layer.data if is_col else None

            if is_col:
                def calc_vertex_color():
                    vert_color = [None] * len(mesh.vertices)
                    for i, p in enumerate(mesh_polygons):
                        for lidx in p.loop_indices:
                            l = mesh_loops[lidx]
                            if vert_color[l.vertex_index] is None:
                                vert_color[l.vertex_index] = mesh_loops_col[lidx].color[:]
                            elif vert_color[l.vertex_index] != mesh_loops_col[lidx].color[:]:
                                return False, ()
                    return True, vert_color
                is_col_per_vertex, vert_color = calc_vertex_color()
                del calc_vertex_color
            for (material_index, image), polygons_group in polygons_groups.items():
                if polygons_group:
                    material = mesh_materials[material_index]
                    fw('%sSeparator{ #beginMaterialIndex\n' % ident)
                    ident += '\t'
                    is_smooth = False
                    for i in polygons_group:
                        if mesh_polygons[i].use_smooth:
                            is_smooth = True
                            break
                    ident += '\t'

                    if image:
                        writeImageTexture(ident, image)
                        print("WRITETEXTURE")
                        # transform by mtex
                        loc = mesh_material_mtex[material_index].translation[:2]

                        # mtex_scale * tex_repeat
                        sca_x, sca_y = mesh_material_mtex[material_index].scale[:2]

                        # sca_x *= mesh_material_tex[material_index].repeat_x
                        # sca_y *= mesh_material_tex[material_index].repeat_y

                        # # flip x/y is a sampling feature, convert to transform
                        # if mesh_material_tex[material_index].use_flip_axis:
                            # rot = math.pi / -2.0
                            # sca_x, sca_y = sca_y, -sca_x
                        # else:
                            # rot = 0.0
                        rot = 0.0
                        ident_step = ident + (' ' * (-len(ident) + \
                        fw('%sTexture2Transform { #beginTexture2Transform' % ident)))
                        fw('\n')
                        # fw('center="%.6f %.6f" ' % (0.0, 0.0))
                        fw(ident_step + 'translation %.6f %.6f\n' % loc)
                        fw(ident_step + 'scaleFactor %.6f %.6f\n' % (sca_x, sca_y))
                        fw(ident_step + 'rotation %.6f\n' % rot)
                        fw(ident_step + '} #endTexture2Transform\n')
                        mesh_loops_uv = mesh.uv_layers.active.data if is_uv else None			
                        if is_uv:
                            ident_step = ident + (' ' * (-len(ident) + \
                            fw('%sTextureCoordinate2 { #beginTextureCoordinate2\n' % ident)))
                            fw('%spoint [\n' % ident) 
                            for i in polygons_group:
                                for lidx in mesh_polygons[i].loop_indices:
                                    fw(ident_step + '%.4f %.4f ,\n' % mesh_loops_uv[lidx].uv[:])
                            fw(ident_step +'] \n')
                            fw(ident_step +'} #endTextureCoordinate2\n')

                    lightSwitch = None 
                    lightSwitchProp = get_vehicle_light_type(obj)
                    if lightSwitchProp is not None:
                        print("Lightswitch= ", lightSwitchProp)
                        def writelightmaterial(lightText):
                            matnames = extract_switch_material_names(lightText)
                            for matname in matnames:
                                material = find_material_by_switch_id(bpy.data.materials, matname)
                                if material is not None:
                                    writeMaterial(
                                        ident,
                                        material,
                                        material_id_index,
                                        world,
                                        image,
                                        material_def_name=matname,
                                    )

                        if lightSwitchProp == "HVE_HEADLIGHT_LEFT":
                            lightText = "#HVE_HEADLIGHT_LEFT \n    DEF HVE_LIGHT_HEADLIGHT_LEFT_Low Switch {USE LIGHT_WHITE_LO}\n    DEF HVE_LIGHT_HEADLIGHT_LEFT_High Switch {USE LIGHT_WHITE_HI}\n"
                        elif lightSwitchProp == "HVE_HEADLIGHT_RIGHT":
                            lightText ="#HVE_HEADLIGHT_RIGHT \n    DEF HVE_LIGHT_HEADLIGHT_RIGHT_Low Switch {USE LIGHT_WHITE_LO}\n    DEF HVE_LIGHT_HEADLIGHT_RIGHT_High Switch {USE LIGHT_WHITE_HI}\n"
                        elif lightSwitchProp == "HVE_REVERSE_LEFT":
                            lightText ="#HVE_REVERSE_LEFT \n    DEF HVE_LIGHT_BACKUPLIGHT_LEFT Switch {USE LIGHT_WHITE_ON}\n"
                        elif lightSwitchProp == "HVE_REVERSE_RIGHT":
                            lightText ="#HVE_REVERSE_RIGHT \n    DEF HVE_LIGHT_BACKUPLIGHT_RIGHT Switch {USE LIGHT_WHITE_ON}\n"
                        elif lightSwitchProp == "HVE_FOGLIGHT_LEFT":
                            lightText ="#HVE_FOGLIGHT_LEFT \n    DEF HVE_LIGHT_HEADLIGHT_LEFT_Fog Switch {USE LIGHT_WHITE_ON}\n"
                        elif lightSwitchProp == "HVE_FOGLIGHT_RIGHT":
                            lightText ="#HVE_FOGLIGHT_RIGHT \n    DEF HVE_LIGHT_HEADLIGHT_RIGHT_Fog Switch {USE LIGHT_WHITE_ON}\n"
                        elif lightSwitchProp == "HVE_AMBERTURN_LEFT":
                            lightText ="#HVE_AMBERTURN_LEFT \n    DEF HVE_LIGHT_RUNNINGLIGHT_FRONT_LEFT Switch {USE LIGHT_AMBER_LO}\n    DEF HVE_LIGHT_SIGNALLIGHT_FRONT_LEFT Switch {USE LIGHT_AMBER_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_FRONT_LEFT Switch {USE LIGHT_AMBER_HI}\n"
                        elif lightSwitchProp == "HVE_AMBERTURN_RIGHT":
                            lightText ="#HVE_AMBERTURN_RIGHT \n    DEF HVE_LIGHT_RUNNINGLIGHT_FRONT_RIGHT Switch {USE LIGHT_AMBER_LO}\n    DEF HVE_LIGHT_SIGNALLIGHT_FRONT_RIGHT Switch {USE LIGHT_AMBER_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_FRONT_RIGHT Switch {USE LIGHT_AMBER_HI}\n"  
                        elif lightSwitchProp == "HVE_AMBERTAIL_LEFT":
                            lightText ="#HVE_AMBERTAIL_LEFT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_LEFT Switch {USE LIGHT_AMBER_LO}\n    DEF HVE_LIGHT_SIGNALLIGHT_REAR_LEFT Switch {USE LIGHT_AMBER_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_REAR_LEFT Switch {USE LIGHT_AMBER_HI}\n"
                        elif lightSwitchProp == "HVE_AMBERTAIL_RIGHT":
                            lightText ="#HVE_AMBERTAIL_RIGHT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_RIGHT Switch {USE LIGHT_AMBER_LO}\n    DEF HVE_LIGHT_SIGNALLIGHT_REAR_RIGHT Switch {USE LIGHT_AMBER_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_REAR_RIGHT Switch {USE LIGHT_AMBER_HI}\n"
                        elif lightSwitchProp == "HVE_BRAKETURN_LEFT":
                            lightText ="#HVE_BRAKETURN_LEFT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_LEFT Switch {USE LIGHT_RED_LO}\n    DEF HVE_LIGHT_BRAKELIGHT_REAR_LEFT Switch {USE LIGHT_RED_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_REAR_LEFT Switch {USE LIGHT_RED_HI}\n    DEF HVE_LIGHT_SIGNALLIGHT_REAR_LEFT Switch {USE LIGHT_RED_HI}\n"
                        elif lightSwitchProp == "HVE_BRAKETURN_RIGHT":
                            lightText ="#HVE_BRAKETURN_RIGHT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_RIGHT Switch {USE LIGHT_RED_LO}\n    DEF HVE_LIGHT_BRAKELIGHT_REAR_RIGHT Switch {USE LIGHT_RED_HI}\n    DEF HVE_LIGHT_EMERGENCYFLASHERLIGHT_REAR_RIGHT Switch {USE LIGHT_RED_HI}\n    DEF HVE_LIGHT_SIGNALLIGHT_REAR_RIGHT Switch {USE LIGHT_RED_HI}\n"
                        elif lightSwitchProp == "HVE_BRAKE_LEFT":
                            lightText =    "#HVE_BRAKE_LEFT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_LEFT Switch {USE LIGHT_RED_LO}\n    DEF HVE_LIGHT_BRAKELIGHT_REAR_LEFT Switch {USE LIGHT_RED_HI}\n"
                        elif lightSwitchProp == "HVE_BRAKE_RIGHT":
                            lightText =    "#HVE_BRAKE_RIGHT \n    DEF HVE_LIGHT_RUNNINGLIGHT_REAR_RIGHT Switch {USE LIGHT_RED_LO}\n    DEF HVE_LIGHT_BRAKELIGHT_REAR_RIGHT Switch {USE LIGHT_RED_HI}\n"
                        elif lightSwitchProp == "HVE_BRAKE_CENTER":
                            lightText = "#HVE_BRAKE_CENTER \n    DEF HVE_LIGHT_BRAKELIGHT_CENTER Switch {USE LIGHT_RED_HI}\n"  
                        else:
                            lightText = ""
                        if lightText is not None:
                            lightSwitch = lightText
                            print(lightSwitch)                        
                            #fw('%s \n' % (lightSwitch))
                            writelightmaterial(lightText)
                    ident = ident[:-1]
                    if material:
                        writeMaterial(ident, material, material_id_index, world, image)                   
                    if lightSwitch is not None:
                            fw('%s \n' % (lightSwitch))

                    #-- IndexedFaceSet                   
                    
                    ident_step = ident + (' ' * (-len(ident) + \
                    fw('%s' % ident)))

                    # --- Write IndexedFaceSet

                    if is_smooth:
                        # use Auto-Smooth angle, if enabled. Otherwise make
                        # the mesh perfectly smooth by creaseAngle > pi.
                        fw('ShapeHints { #beginShapeHints\n')
                        fw(ident_step + 'creaseAngle %.4f\n' % ( 2.0))
                        fw(ident_step + '} #endShapeHints\n')
                        
                    if use_normals or use_normals_obj:

                        # use normals binding, if enabled.             
                        fw('NormalBinding { #beginNormalBinding\n')                        
                        fw(ident_step + 'value PER_VERTEX_INDEXED\n')
                        fw(ident_step + '} #endNormalBinding\n')        
                                                
                    # --- Write IndexedFaceSet Elements
                    if True:
                        if is_coords_written:
                            fw('%sUSE %s \n' % (ident, mesh_id_coords))
                            if use_normals or use_normals_obj:
                                fw('%sUSE %s \n' % (ident, mesh_id_normals))
                        else:
                            ident_step = ident + (' ' * (-len(ident) + \
                            fw('DEF %s\n' % mesh_id_coords)))
                            fw('%sCoordinate3 { #beginCoordinate3\n' % ident)
                            fw(ident_step + 'point [\n')
                            for v in mesh.vertices:
                                fw(ident_step +'%.6f %.6f %.6f ,\n' % v.co[:])
                            fw(ident_step +']\n')
                            fw(ident_step + '} #endCoordinate3\n')
                            is_coords_written = True
                            if use_normals or use_normals_obj:
                                ident_step = ident + (' ' * (-len(ident) + \
                                fw('DEF %s' % mesh_id_normals)))
                                fw('%sNormal { #beginNormal\n' % ident)
                                fw(ident_step + 'vector [')
                                for v in mesh.vertices:
                                    fw('%.6f %.6f %.6f,\n ' % v.normal[:])
                                fw(ident_step +']\n')
                                fw(ident_step + '} #endNormal\n')									
                    if True:
                        fw('%sIndexedFaceSet { #beginIndexedFaceSet\n' % ident)
                    # # for IndexedTriangleSet we use a uv per vertex so this isn't needed.
                        if is_uv:
                            fw(ident_step + 'textureCoordIndex [\n')
                            j = 0
                            for i in polygons_group:
                                num_poly_verts = len(mesh_polygons_vertices[i])
                                fw(ident_step +'%s, -1 ' % ', '.join((str(i) for i in range(j, j + num_poly_verts))))
                                j += num_poly_verts
                                fw('  ,\n')
                            fw(ident_step +']\n')
                        # --- end textureCoordIndex							
                        fw(ident_step + 'coordIndex [\n')
                        for i in polygons_group:
                            poly_verts = mesh_polygons_vertices[i]
                            fw(ident_step +'%s , -1 ' % ', '.join((str(i) for i in poly_verts)))
                            fw('  ,\n')
                        fw(ident_step +']\n')
                        fw(ident_step +'} #endIndexedFaceSet\n')							
                        # --- end coordIndex
                    ident += '\t'
                    ident = ident[:-1]
                    fw('%s} #endMaterialIndex\n' % ident)
            ident = ident[:-1]
            fw('%s} #endMeshIdGroup\n' % ident)
            ident = ident[:-1]
        ident = writeTransform_end(ident)



    def writeMaterial(ident, material, material_id_index, world, image, material_def_name=None):
        print("MATERIAL_DEF")
        
        material_id = material_def_name or clean_def(material.name)
        print("materialid " + material_id)
        
   
        # look up material name, use it if available
        if material_id in material_id_index:

            fw('%s USE %s #MaterialReference\n' % (ident, material_id))

        else:
            material_id_index.add(material_id)
            material.tag = True
            if material.use_nodes == True:
                nodes = material.node_tree.nodes           
                principled = nodes.get("Principled BSDF", None)
                if principled is not None:
                    for input in principled.inputs:
                        print(input.name)
                    principledBaseColor = principled.inputs['Base Color']    
                    principledEmissionColor = principled.inputs['Emission Color']
                    principledEmissionStrength = principled.inputs['Emission Strength']
                    principledMetallic = principled.inputs['Metallic']
                    principledRoughness = principled.inputs['Roughness']
                    principledSpecularTint = principled.inputs['Specular Tint']
                    principledSpecularIORLevel= principled.inputs['Specular IOR Level']
                    principledAlpha = principled.inputs['Alpha']
                    principledTransmissionWeight = principled.inputs['Transmission Weight']
                                        
                    emit = 0.0 #material.emit
                    ambient = 0.5 #material.ambient / 3.0

                    if world and 0:
                        ambiColor = ((material.ambient * 2.0) * world.ambient_color)[:]
                    else:
                        ambiColor = 0.0, 0.0, 0.0

                    baseColor = principledBaseColor.default_value[0],principledBaseColor.default_value[1], principledBaseColor.default_value[2]
                    emisColor = principledEmissionColor.default_value[0]*principledEmissionStrength.default_value,principledEmissionColor.default_value[1]*principledEmissionStrength.default_value, principledEmissionColor.default_value[2]*principledEmissionStrength.default_value
                    metallic = principledMetallic.default_value
                    roughness = principledRoughness.default_value
                    specular = principledSpecularIORLevel.default_value
                    specular_tint = principledSpecularTint.default_value
                    shine = 1.0 - roughness	             	
                    if metallic > 0.5:
                        specColor = tuple(c * specular for c in baseColor)
                        diffColor = tuple(c * shine for c in baseColor)
                    else:
                        whiteColor = 1.0, 1.0, 1.0
                        specColor = tuple(c * specular for c in whiteColor)
                        diffColor = baseColor
                    if image:
                        shine = 0.0
                        
                    transp = principledAlpha.default_value * principledTransmissionWeight.default_value
                else:
                    diffColor = 1.0, 1.0, 1.0
                    specColor = 0, 0, 0
                    emisColor = 0, 0, 0
                    ambiColor = 0, 0, 0
                    shine = 0
                    transp = 0
                #IF NODES ARE THERE FOR HVE
                
                diffuseColor = nodes.get("diffuseColor", None)
                if diffuseColor is not None:
                    diffuseColor = nodes.get("diffuseColor", None).outputs[0].default_value
                    diffuseColor = diffuseColor[0], diffuseColor[1], diffuseColor[2]
                else:
                    diffuseColor = diffColor
                ambientColor = nodes.get("ambientColor", None)
                if ambientColor is not None:
                    ambientColor = nodes.get("ambientColor", None).outputs[0].default_value
                    ambientColor = ambientColor[0], ambientColor[1], ambientColor[2]
                else:
                    ambientColor = ambiColor
                    
                specularColor = nodes.get("specularColor", None)
                if specularColor is not None:
                    specularColor = nodes.get("specularColor", None).outputs[0].default_value
                    specularColor = specularColor[0], specularColor[1], specularColor[2]   
                else:
                    specularColor = specColor
                    
                emissiveColor = nodes.get("emissiveColor", None)
                if emissiveColor is not None:
                    emissiveColor = nodes.get("emissiveColor", None).outputs[0].default_value
                    emissiveColor = emissiveColor[0], emissiveColor[1], emissiveColor[2]
                else:
                    emissiveColor = emisColor
                    
                shininess = nodes.get("shininess", None)
                if shininess is not None:
                    shininess = nodes.get("shininess", None).inputs[0].default_value
                else:
                    shininess = shine
                    
                transparency = nodes.get("transparency", None)
                if transparency is not None:
                    transparency = nodes.get("transparency", None).inputs[0].default_value
                    print('transparency')
                    print(transparency)
                else:
                    transparency = transp
            else:
                diffuseColor = 1.0, 1.0, 1.0
                specularColor = 0, 0, 0
                emissiveColor = 0, 0, 0
                ambientColor = 0, 0, 0
                shininess = 0
                transparency = 0
                
            ident_step = ident + (' ' * (-len(ident) + \
            fw('%sDEF %s\n' % (ident, material_id))))
            fw('%sMaterial { #beginMaterial\n' % ident)
            fw(ident_step + 'diffuseColor %.3f %.3f %.3f\n' % clight_color(diffuseColor))
            fw(ident_step + 'specularColor %.3f %.3f %.3f\n' % clight_color(specularColor))
            fw(ident_step + 'emissiveColor %.3f %.3f %.3f\n' % clight_color(emissiveColor))
            fw(ident_step + 'ambientColor %.3f %.3f %.3f\n' % clight_color(ambientColor))
            fw(ident_step + 'shininess %.3f\n' % shininess)
            fw(ident_step + 'transparency %s\n' % transparency)
            fw(ident_step + '} #endMaterial\n')

    def writeImageTexture(ident, image):
        image_id = unique_name(image, IM_ + image.name, uuid_cache_image, clean_func=clean_def, sep="_")

        if image.tag:
            fw('%sUSE %s \n' % (ident, image_id))
        else:
            image.tag = True

            ident_step = ident + (' ' * (-len(ident) + \
            fw('%sDEF %s\n' % (ident, image_id))))
            fw('%sTexture2 { #beginTexture2\n' % ident)
            # collect image paths, can load multiple
            # [relative, name-only, absolute]
            filepath = image.filepath
           
            filepath_full = bpy.path.abspath(filepath, library=image.library)
            filepath_ref = bpy_extras.io_utils.path_reference(filepath_full, base_src, base_dst, path_mode, "textures", copy_set, image.library)
            filepath_base = os.path.basename(filepath_full)
            images = [
                filepath_ref,
                #filepath_base,
            ]
            # if path_mode != 'RELATIVE':
                # images.append(filepath_full)
            
#ATTEMT TO COPY IMAGES TO SAVE TO DIRECTORY            
        #    filepath = filepath.replace('//', '/')     
        #    imagepath =  filepath               
            #imagepath = dirname + filepath   
        #    imagepath = imagepath.replace('\\','/')
           # img = image
         #   img.filepath=imagepath
         #   print (img.filepath)
          #  img.save()
            
            images = [f.replace('\\', '/') for f in images]
            images = [f for i, f in enumerate(images) if f not in images[:i]]

            fw(ident_step + 'filename "%s"\n' % ' '.join(['%s' % escape(f) for f in images]))
            fw(ident_step + '} #endTexture2\n')

    

    # -------------------------------------------------------------------------
    # Export Object Hierarchy (recursively called)
    # -------------------------------------------------------------------------
    def export_object(ident, obj_main_parent, obj_main, obj_children, material_id_index):
        matrix_fallback = mathutils.Matrix()
        world = scene.world
        #print(obj_main)
        #free, derived = create_derived_objects(depsgraph, obj_main)
        derived_dict = create_derived_objects(depsgraph, [obj_main])
        derived = list(derived_dict.values())[0]
        ident = ident + '  '
        if use_hierarchy:
            obj_main_matrix_world = obj_main.matrix_world
            if obj_main_parent:
                obj_main_matrix = obj_main_parent.matrix_world.inverted(matrix_fallback) @ obj_main_matrix_world
            else:
                obj_main_matrix = obj_main_matrix_world
            obj_main_matrix_world_invert = obj_main_matrix_world.inverted(matrix_fallback)

            obj_main_id = unique_name(obj_main, obj_main.name, uuid_cache_object, clean_func=clean_def, sep="_")
            fw(ident + "Separator { #beginSeparator1\n")  
                  
            print("MATRIX= ")
            print(obj_main_matrix)
            ident = writeTransform_begin(ident, obj_main_matrix if obj_main_parent else global_matrix @ obj_main_matrix, obj_main_id + _TRANSFORM)
            
        # Set here just incase we dont enter the loop below.
        is_dummy_tx = False

        for obj, obj_matrix in (() if derived is None else derived):
            obj_type = obj.type

            if use_hierarchy:
                # make transform node relative
                obj_matrix = obj_main_matrix_world_invert @ obj_matrix
            else:
                obj_matrix = global_matrix @ obj_matrix

            # H3D - use for writing a dummy transform parent
            is_dummy_tx = False

            if obj_type == 'CAMERA':
                
                print("CAMERA")

            elif obj_type in {'MESH', 'CURVE', 'SURFACE', 'FONT'}:
                if (obj_type != 'MESH') or (use_mesh_modifiers and obj.is_modified(scene, 'PREVIEW')):
                    obj_for_mesh = obj.evaluated_get(depsgraph) if use_mesh_modifiers else obj
                    try:
                        me = obj_for_mesh.to_mesh()
                    except RuntimeError:
                        me = None
                    # meshes created via to_mesh() are temporary and must be
                    # cleaned up once written out
                    do_remove = True
                else:
                    me = obj.data
                    do_remove = False
                if me is not None:
                    # Mesh names generated by to_mesh() are read-only and may be
                    # duplicated across objects.  The exporter derives a unique
                    # identifier from the owning object name instead, so the
                    # temporary mesh does not need to be renamed here.  The mesh
                    # is removed after export to keep Blender's data-blocks
                    # untouched.
                    writeIndexedFaceSet(ident, obj, me, obj_matrix, world, material_id_index)

                    # free mesh created with create_mesh()
                    if do_remove:
                        obj_for_mesh.to_mesh_clear()
            elif obj_type == 'LIGHT':
                light_switch = write_vehicle_light_switch(ident, obj, material_id_index, world, '')
                if light_switch is not None:
                    fw('%s \n' % (light_switch))



            else:
                #print "Info: Ignoring [%s], object type [%s] not handle yet" % (object.name,object.getType)
                pass

        #  if free:
        #   free_derived_objects(obj_main)

        # ---------------------------------------------------------------------
        # write out children recursively
        # ---------------------------------------------------------------------
        for obj_child, obj_child_children in obj_children:
            export_object(ident, obj_main, obj_child, obj_child_children, material_id_index)

        if is_dummy_tx:
            ident = ident[:-1]
            fw('%sTransform\n' % ident)
            is_dummy_tx = False

        if use_hierarchy:
            ident = writeTransform_end(ident)
            
        fw('%s} #endSeparator1\n' % ident)
    # -------------------------------------------------------------------------
    # Main Export Function
    # -------------------------------------------------------------------------
    def export_main():
        world = scene.world
        image = ''
        material = ''
        bpy.data.meshes.tag(False)
        bpy.data.materials.tag(False)
        bpy.data.images.tag(False)
        material_id_index = set()
        if use_selection:
            objects = [obj for obj in view_layer.objects if obj.visible_get(view_layer=view_layer)
                       and obj.select_get(view_layer=view_layer)]
        else:
            objects = [obj for obj in view_layer.objects if obj.visible_get(view_layer=view_layer)]

        print('Info: starting H3D export to %r...' % file.name)
        ident = ''
        ident = writeHeader(ident, material, material_id_index, world, image, objects)


        ident = ''

        if use_hierarchy:
            objects_hierarchy = build_hierarchy(objects)
        else:
            objects_hierarchy = ((obj, []) for obj in objects)

        for obj_main, obj_main_children in objects_hierarchy:
            export_object(ident, None, obj_main, obj_main_children, material_id_index)

        ident = writeFooter(ident)


    export_main()

    # -------------------------------------------------------------------------
    # global cleanup
    # -------------------------------------------------------------------------
    # copy all collected files.
    # print(copy_set)
    bpy_extras.io_utils.path_reference_copy(copy_set)

    print('Info: finished H3D export to %r' % file.name)


##########################################################
# Callbacks, needed before Main
##########################################################


def gzip_open_utf8(filepath, mode):
    """Workaround for py3k only allowing binary gzip writing"""

    import gzip

    # need to investigate encoding
    file = gzip.open(filepath, mode)
    write_real = file.write

    def write_wrap(data):
        return write_real(data.encode("utf-8"))

    file.write = write_wrap

    return file


def save(context,
         filepath,
         *,
         use_selection=True,
         use_mesh_modifiers=False,
         use_normals=False,
         use_compress=False,
         use_hierarchy=True,
         global_matrix=None,
         path_mode='AUTO',
         name_decorations=True
         ):

    bpy.path.ensure_ext(filepath, '.h3d' if use_compress else '.h3d')

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')

    if global_matrix is None:
        global_matrix = mathutils.Matrix()

    dirname = os.path.dirname(filepath)

    if use_compress:
        with gzip_open_utf8(filepath, 'w') as file:
            export(file, dirname,
                   global_matrix,
                   context.evaluated_depsgraph_get(),
                   context.scene,
                   context.view_layer,
                   use_mesh_modifiers=use_mesh_modifiers,
                   use_selection=use_selection,
                   use_normals=use_normals,
                   use_hierarchy=use_hierarchy,
                   path_mode=path_mode,
                   name_decorations=name_decorations,
                   )
    else:
        with open(filepath, 'w', encoding='utf-8') as file:
            export(file, dirname,
                   global_matrix,
                   context.evaluated_depsgraph_get(),
                   context.scene,
                   context.view_layer,
                   use_mesh_modifiers=use_mesh_modifiers,
                   use_selection=use_selection,
                   use_normals=use_normals,
                   use_hierarchy=use_hierarchy,
                   path_mode=path_mode,
                   name_decorations=name_decorations,
                   )

    return {'FINISHED'}
