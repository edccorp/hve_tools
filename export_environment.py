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


def clean_def(txt):
    # see report [#28256]

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


def get_environment_props(obj_main):
    """Return terrain property values from an object, with exporter defaults."""
    props = {
        "poName": "Asphalt, Normal",
        "poForceConst": 5000,
        "poForceLinear": 50000,
        "poForceQuad": 1000,
        "poForceCubic": 1000,
        "poRateDamping": 0.5,
        "poFriction": 1,
        "poForceUnload": 100000,
        "poBekkerConst": 0,
        "poKphi": 0,
        "poKc": 0,
        "poPcntMoisture": 0,
        "poPcntClay": 0.02,
        "poSurfaceType": "EdTypeRoad",
        "poWaterDepth": 0,
        "poStaticWater": 1,
        "polabel": "Untitled",
    }

    env_props_group = getattr(getattr(obj_main, "hve_env_props", None), "set_env_props", None)
    if env_props_group is None:
        return props

    idprop_preferred_keys = {"poRateDamping", "poFriction"}

    for key in props:
        value = None

        # Blender 4.5 can expose stale RNA values for some float fields.
        # Limit ID-property preference to the known-affected keys so enum
        # properties such as poSurfaceType keep their RNA identifier strings.
        if key in idprop_preferred_keys and hasattr(env_props_group, "get"):
            sentinel = object()
            idprop_value = env_props_group.get(key, sentinel)
            if idprop_value is not sentinel:
                value = idprop_value

        if value is None:
            value = getattr(env_props_group, key, None)

        if value is not None:
            props[key] = value

    return props


# -----------------------------------------------------------------------------
# Functions for writing output file
# -----------------------------------------------------------------------------

def export_env(file, dirname,
           global_matrix,
           depsgraph,
           scene,
           view_layer,
           use_mesh_modifiers=True,
           use_selection=True,
           use_normals=False,
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

    # Hierarchy export is always enabled for H3D output.
    use_hierarchy = True

    def get_default_material():
        material = bpy.data.materials.get("HVE_Default_Material")
        if material is None:
            material = bpy.data.materials.new(name="HVE_Default_Material")
        return material

    def writeMaterial(ident, material, material_id_index, world, image):
        print("MATERIAL_DEF")

        if material is None:
            material = get_default_material()
            print("Warning: missing material reference in environment export; using '%s'." % material.name)
        
        material_id = clean_def(material.name)
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

    # -------------------------------------------------------------------------
    # Main Export Function
    # -------------------------------------------------------------------------
    def export_main():
        world = scene.world
        image = ''
        material = ''
        objCount =0
        sepCount =0        
        bpy.data.meshes.tag(False)
        bpy.data.materials.tag(False)
        bpy.data.images.tag(False)
        material_id_index = set()
        if use_selection:
            objects = [obj for obj in view_layer.objects if obj.visible_get(view_layer=view_layer)
                       and obj.select_get(view_layer=view_layer)]
        else:
            objects = [obj for obj in view_layer.objects if obj.visible_get(view_layer=view_layer)]

        print('Info: starting HVE Environment export to %r...' % file.name)
        ident = ''

        filepath_quoted = quoteattr(os.path.basename(file.name))
        blender_ver_quoted = quoteattr('Blender %s' % bpy.app.version_string)

            
        fw('#Inventor V8.0 ascii\n\n')
        fw('Separator { #Main Separator \n\n')
        fw('  Info {\n')         
        fw('  string \"HVE VERSION 1.0 FILE\"\n')
        fw('  }\n') 

        fw('  \n')            


        objects_hierarchy = ((obj, []) for obj in objects)              

        for obj_main, obj_main_children in objects_hierarchy:
    # -------------------------------------------------------------------------
    #  Export Object Function
    # -------------------------------------------------------------------------

            obj_main_parent = None
 
            obj_children = obj_main_children
         
            if obj_main.type != 'EMPTY':    
                matrix_fallback = mathutils.Matrix()
                world = scene.world
                derived_dict = create_derived_objects(depsgraph, [obj_main])
                derived = list(derived_dict.values())[0]

                if use_hierarchy :
                    obj_main_matrix_world = obj_main.matrix_world
                    if obj_main_parent:
                        obj_main_matrix = obj_main_parent.matrix_world.inverted(matrix_fallback) @ obj_main_matrix_world
                    else:
                        obj_main_matrix = obj_main_matrix_world
                    obj_main_matrix_world_invert = obj_main_matrix_world.inverted(matrix_fallback)

                    obj_main_id = unique_name(obj_main, obj_main.name, uuid_cache_object, clean_func=clean_def, sep="_")
              
                    env_props = get_environment_props(obj_main)
                    poName = env_props["poName"]
                    poForceConst = env_props["poForceConst"]
                    poForceLinear = env_props["poForceLinear"]
                    poForceQuad = env_props["poForceQuad"]
                    poForceCubic = env_props["poForceCubic"]
                    poRateDamping = env_props["poRateDamping"]
                    poFriction = env_props["poFriction"]
                    poForceUnload = env_props["poForceUnload"]
                    poBekkerConst = env_props["poBekkerConst"]
                    poKphi = env_props["poKphi"]
                    poKc = env_props["poKc"]
                    poPcntMoisture = env_props["poPcntMoisture"]
                    poPcntClay = env_props["poPcntClay"]
                    poSurfaceType = env_props["poSurfaceType"]
                    poWaterDepth = env_props["poWaterDepth"]
                    poStaticWater = env_props["poStaticWater"]
                    polabel = env_props["polabel"]

                    
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
                                print(f"Warning: could not convert '{obj.name}' ({obj_type}) to mesh; skipping.")
                                me = None
                            # meshes created via to_mesh() are temporary and must be
                            # removed after export to avoid leaking datablocks
                            do_remove = True
                        else:
                            me = obj.data
                            do_remove = False
                        if me is not None:
                            # Mesh names from to_mesh() are not reliable for
                            # generating stable identifiers.  We use the owning
                            # object's name when creating export IDs and remove
                            # any temporary meshes once written.

                            # -------------------------------------------------------------------------
                            #  Write Indexed Face Set
                            # -------------------------------------------------------------------------

                            mesh = me
                            matrix = obj_matrix

                            obj_id = unique_name(obj, OB_ + obj.name, uuid_cache_object, clean_func=clean_def, sep="_")
                            mesh_id = unique_name(mesh, ME_ + obj.name, uuid_cache_mesh, clean_func=clean_def, sep="_")
                            mesh_id_group = mesh_id + 'group_'
                            mesh_id_coords = mesh_id + 'coords_'
                            mesh_id_normals = mesh_id + 'normals_'

                            use_normals_obj = any(not edge.smooth for edge in mesh.edges)
                            


                            mesh.tag = True
                            


                            is_uv = bool(mesh.uv_layers.active)

                            is_coords_written = False

                            mesh_materials = mesh.materials[:]
                            default_material = get_default_material()
                            if not mesh_materials:
                                print("Warning: object '%s' has no material slots; using '%s'." % (obj.name, default_material.name))
                                mesh_materials = [default_material]
                            else:
                                mesh_materials = [m if m is not None else default_material for m in mesh_materials]
                            mesh_material_tex = [None] * len(mesh_materials)
                            mesh_material_mtex = [None] * len(mesh_materials)
                            mesh_material_images = [None] * len(mesh_materials)

                            for i, material in enumerate(mesh_materials):
                                if material:
                                    if material.use_nodes == True:
                                        nodes = material.node_tree.nodes 
                                        principled = PrincipledBSDFWrapper(material, is_readonly=True)
                                        tex_principled = principled.base_color_texture
                                        if principled:
                                            principled_key = "base_color_texture"					
                                            tex_principled = getattr(principled,principled_key, None)                           
                                            if tex_principled is not None:
                                                if tex_principled.image:
                                                    #mesh_material_tex[i] = tex_principled
                                                    mesh_material_mtex[i] = tex_principled
                                                    mesh_material_images[i] = tex_principled.image
                                        #IF NODES ARE THERE FOR HVE
                                        hveTexture = nodes.get("hveTexture", None)
                                        if hveTexture is not None:
                                            hveTexture = nodes.get("hveTexture")
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
                                    is_smooth = False
                                    for i in polygons_group:
                                        if mesh_polygons[i].use_smooth:
                                            is_smooth = True
                                            break
                                    fw('  Separator { #Each Surface \n')
                                    fw('	  PickableSurfaceKit {\n')
                                    fw('	  fields [ SFString poName, SFFloat poForceConst, SFFloat poForceLinear, SFFloat poForceQuad,  \n')
                                    fw('	    SFFloat poForceCubic, SFFloat poRateDamping, SFFloat poFriction, SFFloat poForceUnload, \n')
                                    fw('	    SFFloat poBekkerConst, SFFloat poKphi, SFFloat poKc, SFFloat poPcntMoisture,  \n')
                                    fw('	    SFFloat poPcntClay, SFEnum poSurfaceType, SFFloat poWaterDepth, SFInt32 poStaticWater,  \n')
                                    fw('	    SFInt32 bSignalKit, SFInt32 nSignalID, SFNode poPickCB, SFNode poLabel, \n')
                                    fw('	    SFNode poUnPickStyle, SFNode poPickStyle, SFNode poTexCoord, SFNode poTexFunc, \n')
                                    fw('	    SFNode poTexBinding, SFNode poObject, SFNode poSimplifyTransform, SFNode poMarkersStyles, \n')
                                    fw('	    SFNode poMarkersCoords, SFNode poMarkersPoints, SFNode poSimplifyRegionSep, SFNode poMainSwitch,  \n')
                                    fw('	    SFNode poMainSep, SFNode poPickSwitch, SFNode poSimplifyUIStuff, SFNode poMarkersSep ] \n')
                                    fw('	  poName "%s"\n' % poName)             
                                    fw('	  poForceConst %s\n' % poForceConst)  
                                    fw('	  poForceLinear %s\n' % poForceLinear)        
                                    fw('	  poForceQuad %s\n' % poForceQuad)  
                                    fw('	  poForceCubic %s\n' % poForceCubic)  
                                    fw('	  poRateDamping %s\n' % poRateDamping)  
                                    fw('	  poFriction %s\n' % poFriction)        
                                    fw('	  poForceUnload %s\n' % poForceUnload)  
                                    fw('	  poBekkerConst %s\n' % poBekkerConst)  
                                    fw('	  poKphi %s\n' % poKphi)  
                                    fw('	  poKc %s\n' % poKc)  
                                    fw('	  poPcntMoisture %s\n' % poPcntMoisture)  
                                    fw('	  poPcntClay %s\n' % poPcntClay)  
                                    fw(' 	  poSurfaceType %s\n' % poSurfaceType)  
                                    fw('	  poWaterDepth %s\n' % poWaterDepth)  
                                    fw('      poStaticWater %d\n' % (1 if poStaticWater else 0))  
                                    fw('	  bSignalKit 0\n')
                                    fw('	  nSignalID -1\n')
                                    fw('	  poPickCB \n')
                                    fw('	  DEF poPickCB+%s EventCallback {\n' %(objCount))

                                    fw('	  	  }\n')
                                    
                                    fw('	  poLabel \n')
                                    fw('	  DEF poLabel+%s Label {\n'%(objCount))

                                    fw('		 label "%s"\n' % polabel)  
                                    fw('	  	  }\n')
                                    
                                    fw('	  poUnPickStyle\n')
                                    fw('	  DEF poUnPickStyle+%s PickStyle {\n'%(objCount))

                                    fw('		 style UNPICKABLE\n')
                                    fw('	  	  }\n')

                                    fw('	  poPickStyle\n')
                                    fw('	  DEF poPickStyle+%s PickStyle {\n'%(objCount))

                                    fw('		 style SHAPE\n')
                                    fw('	  	  }\n')

                                    fw('	  poTexCoord\n')
                                    fw('	  DEF poTexCoord+%s TextureCoordinate2 {\n'%(objCount))

                                    fw('		 point [  ]\n')
                                    fw('	  	  }\n')
                                    
                                    fw('	  poTexFunc\n')
                                    fw('	  DEF poTexFunc+%s TextureCoordinateFunction {\n'%(objCount))
                                    fw('	  	  }\n')
                                           
                                    fw('	  poTexBinding\n')
                                    fw('	  DEF poTexBinding+%s TextureCoordinateBinding {\n'%(objCount))

                                    fw('	  	  }\n')     
                                    
                                    
                                    fw('	  poObject\n')
                                    fw('	  DEF poObject+%s ShapeKit {\n'%(objCount))




                                    matrix = obj_main_matrix if obj_main_parent else global_matrix @ obj_main_matrix
                                    def_id = obj_main_id + _TRANSFORM

                                    loc, rot, sca = matrix.decompose()
                                    rot = rot.to_axis_angle()
                                    rot = (*rot[0], rot[1])
                                    fw('		 transform \n') 
                                    fw('		 Transform { #beginTransform\n')
                                    fw('		 translation %.6f %.6f %.6f\n' % loc[:])
                                    # fw('		 center %.6f %.6f %.6f\n' % (0, 0, 0))
                                    fw('		 scaleFactor %.6f %.6f %.6f\n' % sca[:])
                                    fw('		 rotation %.6f %.6f %.6f %.16f\n' % rot)
                                    fw('		 } #endTransform\n')
                                    
                                    #AppearanceKit
                                    fw('		 appearance\n' )                                  
                                    fw('		 AppearanceKit { \n' )
                                    fw('		  lightModel \n' )
                                    fw('		  LightModel {\n' )
                                    fw('			 model PHONG\n' )
                                    fw('		  }\n' ) 
                                    fw('		 shapeHints  \n' )
                                    fw('		 ShapeHints {\n' )
                                    fw('		  vertexOrdering COUNTERCLOCKWISE\n' )
                                    fw('		  shapeType UNKNOWN_SHAPE_TYPE\n' )                             
                                    fw('		  faceType CONVEX\n' )
                                    fw('		  }\n' ) 

                                    if image:
                                        
                                        # -------------------------------------------------------------------------
                                        #  Write Image Texture
                                        # -------------------------------------------------------------------------
                      

                                                                        
                                        image_id = unique_name(image, IM_ + image.name, uuid_cache_image, clean_func=clean_def, sep="_")

                                        image.tag = True
                                        fw('		  texture2 \n')
                                        fw('		  Texture2 { #beginTexture2\n')
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
                                        
                                        images = [f.replace('\\', '/') for f in images]
                                        images = [f for i, f in enumerate(images) if f not in images[:i]]

                                        fw('		  filename "%s"\n' % ' '.join(['%s' % escape(f) for f in images]))
                                        fw('		  } #endTexture2\n')

                                    if material:
                                        #-------------------------------------
                                        # Write Material
                                        #---------------                                        
                                        
                                        material_id = clean_def(material.name)
                                       
                                        # look up material name, use it if available

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
                                                    
                                                transp = 1-principledAlpha.default_value * (1-principledTransmissionWeight.default_value)
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
                                            
                                        fw('		  material \n')
                                        fw('		  Material { #beginMaterial\n')
                                        fw('		  diffuseColor %.3f %.3f %.3f\n' % clight_color(diffuseColor))
                                        fw('		  specularColor %.3f %.3f %.3f\n' % clight_color(specularColor))
                                        fw('		  emissiveColor %.3f %.3f %.3f\n' % clight_color(emissiveColor))
                                        fw('		  ambientColor %.3f %.3f %.3f\n' % clight_color(ambientColor))
                                        fw('		  shininess %.3f\n' % shininess)
                                        fw('		  transparency %s\n' % transparency)
                                        fw('		  } #endMaterial\n')
                                    fw('		  } #endAppearanceKit\n')
                                        
                                        
                                    if image:
                                        
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
                                        fw('		  texture2Transform \n')
                                        fw('		  Texture2Transform { #beginTexture2Transform')
                                        fw('\n')
                                        # fw('		  center="%.6f %.6f" ' % (0.0, 0.0))
                                        fw('		  translation %.6f %.6f\n' % loc)
                                        fw('		  scaleFactor %.6f %.6f\n' % (sca_x, sca_y))
                                        fw('		  rotation %.6f\n' % rot)
                                        fw('		  } #endTexture2Transform\n')
                                        mesh_loops_uv = mesh.uv_layers.active.data if is_uv else None			
                                        if is_uv:
                                            fw('		 textureCoordinate2 \n')                                  
                                            fw('		  TextureCoordinate2 { #beginTextureCoordinate2\n')
                                            fw('          point [ ')
                                            j = 0
                                            for i in polygons_group:
                                                for lidx in mesh_polygons[i].loop_indices: 
                                                    j +=1
                                            fw('%s , \n' % j)
                                            
                                            for i in polygons_group:
                                                for lidx in mesh_polygons[i].loop_indices:
                                                    fw('		  %.4f %.4f ,\n' % mesh_loops_uv[lidx].uv[:])
                                            fw('		  ]\n')
                                            fw('		  } #endTextureCoordinate2\n')


                 

      
                                    #-- IndexedFaceSet                   
                                    
                                    # --- Write IndexedFaceSet

                                    #if is_smooth:
                                        # use Auto-Smooth angle, if enabled. Otherwise make
                                        # the mesh perfectly smooth by creaseAngle > pi.
                                        #fw('		  ShapeHints { #beginShapeHints\n')
                                        #fw('		  creaseAngle %.4f\n' % ( 2.0))
                                        #fw('		  } #endShapeHints\n')
                                        
                                    if use_normals or use_normals_obj:
                                        # use normals binding, if enabled.  
                                        fw('		  normalbinding\n')                           
                                        fw('		  NormalBinding { #beginNormalBinding\n')                        
                                        fw('		  value PER_VERTEX_INDEXED\n')
                                        fw('		  } #endNormalBinding\n')        
                                                                
                                    # --- Write IndexedFaceSet Elements
                                    if True:
                                        fw('		  coordinate3 \n')
                                        fw('		  Coordinate3 { #beginCoordinate3\n')
                                        fw('		  point [ %s, \n' % len(mesh.vertices))
                                        for v in mesh.vertices:
                                            fw('		  %.6f %.6f %.6f ,\n' % v.co[:])
                                        fw('		  ]\n')
                                        fw('		  } #endCoordinate3\n')
                                        is_coords_written = True
                                        loop_normals = []
                                        normal_index_faces = []
                                        if use_normals or use_normals_obj:
                                            for poly_i in polygons_group:
                                                p = mesh_polygons[poly_i]
                                                face_nidx = []
                                                for lidx in p.loop_indices:
                                                    loop = mesh_loops[lidx]
                                                    n = getattr(loop, "normal", None)
                                                    if n is None:
                                                        cn = mesh.corner_normals[lidx]
                                                        n = getattr(cn, "vector", None) or getattr(cn, "normal", None)
                                                    if n is None:
                                                        n = p.normal
                                                    loop_normals.append((n.x, n.y, n.z))
                                                    face_nidx.append(len(loop_normals) - 1)
                                                normal_index_faces.append(face_nidx)

                                            fw('\t\t  normal\n')
                                            fw('\t\t  Normal { #beginNormal\n' )
                                            fw('\t\t  vector [\n')
                                            for nx, ny, nz in loop_normals:
                                                fw('\t\t  %.6f %.6f %.6f,\n' % (nx, ny, nz))
                                            fw('\t\t  ]\n')
                                            fw('\t\t  } #endNormal\n')
                                    if True:
                                        fw('		 shape \n')
                                        fw('		  IndexedFaceSet { #beginIndexedFaceSet\n' )
                                    # # for IndexedTriangleSet we use a uv per vertex so this isn't needed.
                                        if is_uv:
                                            
                                            fw('		  textureCoordIndex [ ')
                                            k = 0
                                            for i in polygons_group:
                                                k += 1
                                                poly_verts = mesh_polygons_vertices[i]
                                                for i in poly_verts:
                                                    k += 1    
                                            fw('%s ,\n' % k)
                                            j = 0
                                            for i in polygons_group:   
                                                num_poly_verts = len(mesh_polygons_vertices[i])                                        
                                                fw('		  %s, -1 ' % ', '.join((str(i) for i in range(j, j + num_poly_verts))))
                                                j += num_poly_verts
                                                fw('         ,\n')
                                            fw('            ]\n')
                                        # --- end textureCoordIndex							
                                        poly_verts = mesh_polygons_vertices[i]
                                        fw('		  coordIndex [' )
                                        k = 0 
                                        for i in polygons_group:
                                            k += 1
                                            poly_verts = mesh_polygons_vertices[i]
                                            for i in poly_verts:
                                                k += 1                             
                                        fw('%s ,\n' % k)
                                        j = 0 
                                        for i in polygons_group:
                                            poly_verts = mesh_polygons_vertices[i]
                                            fw('		  %s , -1 ' % ', '.join((str(i) for i in poly_verts)))
                                            fw('         ,\n')
                                        fw( '          ]\n')
                                        if use_normals or use_normals_obj:
                                            fw('          normalIndex [\n')
                                            for face_nidx in normal_index_faces:
                                                fw('          %s, -1,\n' % ', '.join(str(n) for n in face_nidx))
                                            fw('          ]\n')
                                        fw('        } #endIndexedFaceSet\n')							
                                        # --- end coordIndex
                                    fw('    \n' )
                                    fw('    } #endShapeKit\n')    
                                        
                                        
                                    fw('	  poSimplifyTransform\n')
                                    fw('	  DEF poSimplifyTransform+%s Transform {\n'%(objCount))            
                                    fw('      }\n')
                                    
                                    fw('	  poMarkersStyles\n')
                                    fw('	  DEF poMarkersStyles+%s Group {\n'%(objCount)) 
                                    fw('		 DrawStyle {\n')
                                    fw('		  pointSize 10\n')
                                    fw('		 }\n')
                                    fw('		 LightModel {\n')
                                    fw('		  model BASE_COLOR\n')
                                    fw('		 }\n')
                                    fw('		 MaterialBinding {\n')
                                    fw('		  value OVERALL\n')
                                    fw('		 }\n')
                                    fw('		 BaseColor {\n')
                                    fw('		  rgb 1 1 0\n')
                                    fw('		 }\n')
                                    fw('		 DepthBuffer {\n')
                                    fw('		  function ALWAYS\n')
                                    fw('      }	  }\n')

                                    fw('	  poMarkersCoords\n')
                                    fw('	  DEF poMarkersCoords+%s Coordinate3 {\n'%(objCount))            
                                    fw('		 point [  ]\n')
                                    fw('      }\n')        
                                    
                                    fw('	  poMarkersPoints\n')
                                    fw('	  DEF poMarkersPoints+%s PointSet {\n'%(objCount)) 
                                    fw('		 startIndex 0\n')
                                    fw('		 numPoints -1\n')
                                    fw('      }\n')
                                    
                                    fw('	  poSimplifyRegionSep\n')
                                    fw('	  DEF poSimplifyRegionSep+%s Separator {\n'%(objCount)) 
                                    fw('      }\n')
                                    
                                    fw('	  poMainSwitch\n')
                                    fw('	  Switch {\n')
                                    fw('		 whichChild  =\n')
                                    fw('		 DEF showOverlay%s GlobalField {\n'%(polabel)) 
                                    fw('		  type "SFInt32"\n')
                                    fw('		  showOverlay%s 0\n'%(polabel))         
                                    fw('		 }		 . showOverlay%s\n'%(polabel))   
                                    fw('		 DEF Separator+%s+%s Separator {\n'%(objCount,sepCount)) 
                                    sepCount += 1
                                    fw('		  USE poPickCB+%s\n'%(objCount))
                                    fw('		  USE poLabel+%s\n'%(objCount))
                                    fw('		  DEF Switch+%s Switch {\n'%(objCount))   
                                    fw('			 whichChild  0\n')
                                    fw('			 USE poUnPickStyle+%s\n'%(objCount))
                                    fw('			 USE poPickStyle+%s	  }\n'%(objCount))
                                    fw('		  USE poTexCoord+%s\n'%(objCount))
                                    fw('		  USE poTexFunc+%s\n'%(objCount))
                                    fw('		  USE poTexBinding+%s\n'%(objCount))
                                    fw('		  USE poObject+%s\n'%(objCount))  
                                    fw('		  DEF Separator+%s+%s Separator {\n'%(objCount,sepCount)) 
                                    sepCount += 1
                                    fw('			 USE poSimplifyTransform+%s\n'%(objCount))   
                                    fw('			 DEF Separator+%s+%s Separator {\n'%(objCount,sepCount)) 
                                    sepCount += 1
                                    fw('			 USE poMarkersStyles+%s\n'%(objCount))  
                                    fw('			 USE poMarkersCoords+%s\n'%(objCount))  
                                    fw('			 USE poMarkersPoints+%s			 }\n'%(objCount))  
                                    fw('			 USE poSimplifyRegionSep+%s			 }  }    }\n'%(objCount))  
                                    fw('	  poMainSep\n')  
                                    sepCount = 0
                                    fw('	  USE Separator+%s+%s \n'%(objCount,sepCount)) 
                                    sepCount += 1
                                    
                                    fw('	  poPickSwitch\n')  
                                    fw('	  USE Switch+%s\n'%(objCount))          
                                    fw('	  poSimplifyUIStuff\n')  
                                    fw('	  USE Separator+%s+%s \n'%(objCount,sepCount))  
                                    sepCount += 1
                                    fw('	  poMarkersSep\n')  
                                    fw('	  USE Separator+%s+%s \n'%(objCount,sepCount))  
                                    sepCount = 0
                                    objCount +=1
                                    fw('    }   \n')    
                                    fw(' }   \n') 
                            
                            # free mesh created with create_mesh()
                            if do_remove:
                                obj_for_mesh.to_mesh_clear()


                    else:
                        #print "Info: Ignoring [%s], object type [%s] not handle yet" % (object.name,object.getType)
                        pass

                #  if free:
                #   free_derived_objects(obj_main)



                if is_dummy_tx:
                    fw('		  Transform\n')
                    is_dummy_tx = False

                if use_hierarchy:
                    fw('		  \n')
                    
                
        fw('}\n')  


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
            export_env(file, dirname,
               global_matrix,
               context.evaluated_depsgraph_get(),
               context.scene,
               context.view_layer,
               use_mesh_modifiers=use_mesh_modifiers,
               use_selection=use_selection,
               use_normals=use_normals,
               path_mode=path_mode,
               name_decorations=name_decorations,
               )
    else:
        with open(filepath, 'w', encoding='utf-8') as file:
            export_env(file, dirname,
               global_matrix,
               context.evaluated_depsgraph_get(),
               context.scene,
               context.view_layer,
               use_mesh_modifiers=use_mesh_modifiers,
               use_selection=use_selection,
               use_normals=use_normals,
               path_mode=path_mode,
               name_decorations=name_decorations,
               )

    return {'FINISHED'}
