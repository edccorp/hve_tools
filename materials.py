#!/usr/bin/python
# -*- coding: utf-8 -*-

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  Authors:             Thomas Larsson
#  Script copyright (C) Thomas Larsson 2014-2018
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
import os
import math
D = math.pi/180

# ---------------------------------------------------------------------
#
# ---------------------------------------------------------------------

def buildMaterial(mhMaterial, scn, cfg):
    mname = mhMaterial["name"]
    mat = bpy.data.materials.new(mname)
    buildMaterialCycles(mat, mhMaterial, scn, cfg)
    return mname, mat



# ---------------------------------------------------------------------
#   Cycles
# ---------------------------------------------------------------------

class NodeTree:
    def __init__(self, tree):
        self.nodes = tree.nodes
        self.links = tree.links
        self.ycoords = 10*[500]

    def addNode(self, n, stype):
        node = self.nodes.new(type = stype)
        node.location = (n*250-500, self.ycoords[n])
        self.ycoords[n] -= 250
        return node


def buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name):
    mat_list = bpy.data.materials
    if name in mat_list:
        print("MATERIAL ALREADY THERE")
    else:
        mat = bpy.data.materials.new(name)
        print("Creating CYCLES material", mat.name)
        mat.use_nodes= True
        mat.node_tree.nodes.clear()
        tree = NodeTree(mat.node_tree)
        links = mat.node_tree.links
        
        texture = tree.addNode(1, 'ShaderNodeTexImage')
        texture.label = "hveTexture"
        texture.name = "hveTexture"
        
        diffuseColor = tree.addNode(1, 'ShaderNodeRGB')
        diffuseColor.label = "diffuseColor"
        diffuseColor.name = "diffuseColor"
        diffuseColor.outputs[0].default_value =  diffColor
        
        mixDiffuseTexture = tree.addNode(2, 'ShaderNodeMixRGB')
        mixDiffuseTexture.label = "mixDiffuseTexture"
        mixDiffuseTexture.name = "mixDiffuseTexture" 
        
        ambientColor = tree.addNode(1, 'ShaderNodeRGB')
        ambientColor.label = "ambientColor"
        ambientColor.name = "ambientColor"
        ambientColor.outputs[0].default_value =  ambiColor 
        
        specularColor = tree.addNode(1, 'ShaderNodeRGB')
        specularColor.label = "specularColor"
        specularColor.name = "specularColor"
        specularColor.outputs[0].default_value =  specColor
           
        shininess = tree.addNode(1, 'ShaderNodeClamp')
        shininess.label = "shininess"
        shininess.name = "shininess"
        shininess.clamp_type = 'RANGE'
        shininess.inputs[0].default_value =  shine   
        
        mapRoughness = tree.addNode(2, 'ShaderNodeMapRange')
        mapRoughness.label = "mapRoughness"
        mapRoughness.name = "mapRoughness"    
        mapRoughness.interpolation_type = 'LINEAR'
        mapRoughness.inputs[1].default_value = 0
        mapRoughness.inputs[2].default_value = 1    
        mapRoughness.inputs[3].default_value = 1    
        mapRoughness.inputs[4].default_value = 0    
        
        emissiveColor = tree.addNode(1, 'ShaderNodeRGB')
        emissiveColor.label = "emissiveColor"
        emissiveColor.name = "emissiveColor"
        emissiveColor.outputs[0].default_value =  emisColor

        transparency = tree.addNode(1, 'ShaderNodeClamp')
        transparency.label = "transparency"
        transparency.name = "transparency"
        transparency.inputs[0].default_value =  transp
        transparency.clamp_type = 'RANGE'
        
        mapAlpha = tree.addNode(2, 'ShaderNodeMapRange')
        mapAlpha.label = "mapAlpha"
        mapAlpha.name = "mapAlpha"    
        mapAlpha.interpolation_type = 'LINEAR'
        mapAlpha.inputs[1].default_value = 0
        mapAlpha.inputs[2].default_value = 1    
        mapAlpha.inputs[3].default_value = 1    
        mapAlpha.inputs[4].default_value = 0   
        
        principled = tree.addNode(3, 'ShaderNodeBsdfPrincipled')
        principled.name = "principledBSDF"
        principled.label = "principledBSDF"    
        
        outputMaterial = tree.addNode(4, 'ShaderNodeOutputMaterial')
        
        links.new(texture.outputs[0],mixDiffuseTexture.inputs[1])
        links.new(diffuseColor.outputs[0],mixDiffuseTexture.inputs[2])    
        links.new(mixDiffuseTexture.outputs[0],principled.inputs[0])
        links.new(ambientColor.outputs[0],principled.inputs[3])   
        links.new(specularColor.outputs[0],principled.inputs[5])
        links.new(shininess.outputs[0],mapRoughness.inputs[0])
        links.new(transparency.outputs[0],mapAlpha.inputs[0])
        links.new(mapRoughness.outputs[0],principled.inputs[7])
        links.new(mapAlpha.outputs[0],principled.inputs[18])
        links.new(emissiveColor.outputs[0],principled.inputs[17])    
        links.new(principled.outputs[0],outputMaterial.inputs[0])
        
        mat.use_fake_user = True

def buildGenericMaterial(ob, scn):
    diffColor = (1, 1, 1, 1)
    ambiColor = (0.2, 0.2, 0.2, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (0, 0, 0, 1)
    shine = 1
    transp = 0
    name = "HVE_Generic"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)

def buildStandardMaterials(ob, scn):
    diffColor = (.6, .6, .6, 1)
    ambiColor = (0.2, 0.2, 0.2, 1)
    specColor = (.6, .6, .6, 1)
    emisColor = (0, 0, 0, 1)
    shine = 1
    transp = 0
    name = "BODY"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)    
    diffColor = (.3, .3, .3, 1)
    ambiColor = (0.2, 0.2, 0.2, 1)
    specColor = (1, 1, 1, 1)
    emisColor = (0, 0, 0, 1)
    shine = .9
    transp = 0.2
    name = "GLASS"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)    
    diffColor = (.5, .5, .5, 1)
    ambiColor = (0.2, 0.2, 0.2, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (0, 0, 0, 1)
    shine = 1
    transp = 0
    name = "TRIM"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)        
    diffColor = (0, 0, 0, 1)
    ambiColor = (0.2, 0.2, 0.2, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (0, 0, 0, 1)
    shine = 1
    transp = 0
    name = "BLACK"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)     
    diffColor = (.6, .6, .6, 1)
    ambiColor = (0.2, 0.2, 0.2, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (0, 0, 0, 1)
    shine = .3
    transp = 0
    name = "CHROME"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)    
    diffColor = (.8, .8, .8, 1)
    ambiColor = (0.2, 0.2, 0.2, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (0, 0, 0, 1)
    shine = .9
    transp = 0
    name = "NONCHROME"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)    
    diffColor = (.7, .5, .3, 1)
    ambiColor = (0.35, 0.25, 0.15, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (0, 0, 0, 1)
    shine = 0
    transp = 0
    name = "INTERIOR"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)        
    diffColor = (.1, .1, .1, 1)
    ambiColor = (0.2, 0.2, 0.2, 1)
    specColor = (.1, .1, .1, 1)
    emisColor = (0, 0, 0, 1)
    shine = .1
    transp = 0
    name = "VINYL"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)
    diffColor = (.4, .4, .4, 1)
    ambiColor = (0.2, 0.2, 0.2, 1)
    specColor = (.2, .2, .2, 1)
    emisColor = (0, 0, 0, 1)
    shine = .5
    transp = 0
    name = "VANSHELL"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)
    diffColor = (.1, 1, .1, 1)
    ambiColor = (.5, .5, .5, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (0, 0, 0, 1)
    shine = 0
    transp = 0
    name = "EDC"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)


def buildLightMaterials(ob, scn):
    diffColor = (1, 1, 1, 1)
    ambiColor = (1, 1, 1, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (1, 1, 1, 1)
    shine = 1
    transp = 0
    name = "LIGHT_WHITE_HI"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)    
    diffColor = (.7, .7, .7, 1)
    ambiColor = (.7, .7, .7, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (.4, .4, .4, 1)
    shine = 1
    transp = 0
    name = "LIGHT_WHITE_LO"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)    
    diffColor = (.6, .6, .6, 1)
    ambiColor = (0.3, 0.3, 0.3, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (0, 0, 0, 1)
    shine = 1
    transp = 0
    name = "LIGHT_WHITE_OFF"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)        
    diffColor = (1, .2, .2, 1)
    ambiColor = (1, .2, .2, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (1, .2, .2, 1)
    shine = 1
    transp = 0
    name = "LIGHT_WHITE_ON"
    
    diffColor = (1, .6, 0, 1)
    ambiColor = (1, .6, 0, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (1, 1, .2, 1)
    shine = 1
    transp = 0
    name = "LIGHT_AMBER_HI"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)    
    diffColor = (.6, .4, .2, 1)
    ambiColor = (.6, .4, .2, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (.3, .2, 0, 1)
    shine = 1
    transp = 0
    name = "LIGHT_AMBER_LO"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)    
    diffColor = (.6, .4, 0, 1)
    ambiColor = (0.2, 0.1, 0, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (0, 0, 0, 1)
    shine = 1
    transp = 0
    name = "LIGHT_AMBER_OFF"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)
        
    diffColor = (1, .2, .2, 1)
    ambiColor = (1, .2, .2, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (1, .2, .2, 1)
    shine = 1
    transp = 0
    name = "LIGHT_RED_HI"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)
    diffColor = (.6, .1, .1, 1)
    ambiColor = (.6, .1, .1, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (.4, 0, 0, 1)
    shine = 1
    transp = 0
    name = "LIGHT_RED_LO"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)
    diffColor = (.6, .1, .1, 1)
    ambiColor = (0.3, .05, 0.05, 1)
    specColor = (0, 0, 0, 1)
    emisColor = (0, 0, 0, 1)
    shine = 1
    transp = 0
    name = "LIGHT_RED_OFF"
    buildMaterial4HVE(ob, scn, diffColor, ambiColor, specColor, emisColor, shine, transp, name)
   
    
class HVE_OT_AddHVEMaterial(bpy.types.Operator):
    bl_idname = "hve_material.add_hve_material"
    bl_label = "Add generic material"
    bl_description = "Add a generic HVE material"
    bl_options = {'UNDO'}

    @classmethod
    def poll(self, context):
        ob = context.object
        return (ob)

    def execute(self, context):
        buildGenericMaterial(context.object, context.scene)
        return{'FINISHED'}
        
class HVE_OT_AddStandardMaterials(bpy.types.Operator):
    bl_idname = "hve_material.add_standard_materials"
    bl_label = "Add standard materials"
    bl_description = "Add standard HVE materials"
    bl_options = {'UNDO'}

    @classmethod
    def poll(self, context):
        ob = context.object
        return (ob)

    def execute(self, context):
        buildStandardMaterials(context.object, context.scene)
        return{'FINISHED'}
        
class HVE_OT_MakeLightMaterials(bpy.types.Operator):
    bl_idname = "hve_material.add_hve_light_materials"
    bl_label = "Add HVE light materials"
    bl_description = "Add HVE light materials"
    bl_options = {'UNDO'}

    @classmethod
    def poll(self, context):
        ob = context.object
        return (ob)

    def execute(self, context):
        buildLightMaterials(context.object, context.scene)
        return{'FINISHED'}
        

        
#----------------------------------------------------------
#   Initialize
#----------------------------------------------------------

classes = (
    HVE_OT_AddHVEMaterial,
    HVE_OT_AddStandardMaterials,
    HVE_OT_MakeLightMaterials,
)
