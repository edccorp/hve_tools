bl_info = {
    "name": "Scale by Two Points (Scene Units)",
    "author": "EDC",
    "version": (1, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Tool",
    "description": "Scales an object based on two selected vertices and a user-defined distance using scene units",
    "category": "Object",
}

import bpy
import bmesh
from mathutils import Vector

class ScaleByTwoPointsOperator(bpy.types.Operator):
    """Scale an object based on two selected vertices and scene units"""
    bl_idname = "object.scale_by_two_points"
    bl_label = "Scale by Two Points"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
  
    
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}

        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Enter Edit Mode and select two vertices")
            return {'CANCELLED'}
        bpy.ops.object.mode_set(mode='OBJECT')  
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)  # Apply scale
        bpy.ops.object.mode_set(mode='EDIT')

        # Get selected vertices
        bm = bmesh.from_edit_mesh(obj.data)
        selected_verts = [v for v in bm.verts if v.select]

        if len(selected_verts) != 2:
            self.report({'ERROR'}, "Select exactly two vertices")
            return {'CANCELLED'}

        v1, v2 = selected_verts
        current_distance = (v2.co - v1.co).length

        # Get scene unit scale
        unit_system = context.scene.unit_settings.system
        if unit_system == 'METRIC':
            unit_scale = 1
        elif unit_system == 'IMPERIAL':
            unit_scale = 0.3048
        else:
            unit_scale = 1
        
        print(f"unit_scale  ={unit_scale}")
        target_distance = context.scene.scale_target_distance * unit_scale
        print(f"target_distance ={target_distance}")
        if current_distance == 0:
            self.report({'ERROR'}, "Selected points are identical")
            return {'CANCELLED'}

        # Calculate scaling factor (target distance / current distance)
        scale_factor = target_distance / current_distance
        print(f"current_distance ={current_distance}")
        print(f"scale_factor ={scale_factor}")
        # Apply scaling
        bpy.ops.object.mode_set(mode='OBJECT')
        obj.scale = obj.scale * scale_factor  # Scale proportionally
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)  # Apply scale

        self.report({'INFO'}, f"Scaled object by factor: {scale_factor:.4f} (Target: {target_distance/unit_scale:.4f} {context.scene.unit_settings.system})")
        return {'FINISHED'}



### Registering Add-on ###
classes = [
    ScaleByTwoPointsOperator,
    ]
    
