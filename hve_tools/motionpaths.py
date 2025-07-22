import bpy

bl_info = {
    'name': 'Motion Path to Curve',
    'category': 'Converter',
    'author': 'EDC',
    'version': (1, 7),
    'blender': (4, 3, 0),
    'description': 'Generates motion paths and converts them into curves, organizing them in a collection.',
}


def get_or_create_motion_path_collection():
    """Creates a collection called 'Motion Paths' if it doesn't exist."""
    collection_name = "Motion Paths"
    if collection_name in bpy.data.collections:
        return bpy.data.collections[collection_name]
    
    new_collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(new_collection)
    return new_collection


def create_motion_path(ob):
    """Generates a motion path for the given object."""
    bpy.context.view_layer.objects.active = ob
    # Ensure motion path settings exist
    # Ensure motion path settings exist
    if ob.motion_path:
        bpy.ops.object.paths_clear()  # Clear any existing motion path

    # Create a motion path for the object
    bpy.ops.object.paths_calculate()
    
    return ob.motion_path is not None

def delete_motion_path(ob):
    """Generates a motion path for the given object."""
    bpy.context.view_layer.objects.active = ob
    # Ensure motion path settings exist
    # Ensure motion path settings exist
    if ob.motion_path:
        bpy.ops.object.paths_clear()  # Clear any existing motion path

    
    return ob.motion_path is not None


def create_curve_from_motion_path(ob, context):
    """Creates a curve based on an object's motion path and adds it to the 'Motion Paths' collection."""
    if not ob.motion_path or not ob.motion_path.points:
        print(f"Skipping {ob.name}: No valid motion path found.")
        return None
    
    mp = ob.motion_path

    # Create a new curve data block
    path = bpy.data.curves.new(name=f"{ob.name}_path", type='CURVE')
    curve_obj = bpy.data.objects.new(name=f"{ob.name}_path", object_data=path)

    # Link to the 'Motion Paths' collection
    motion_path_collection = get_or_create_motion_path_collection()
    motion_path_collection.objects.link(curve_obj)

    path.dimensions = '3D'
    spline = path.splines.new(type='BEZIER')
    spline.bezier_points.add(len(mp.points) - 1)

    for i, p  in enumerate(spline.bezier_points):
        p.co = mp.points[i].co
        p.handle_right_type = 'VECTOR'
        p.handle_left_type = 'VECTOR'

    return curve_obj


def toggle_motion_path_visibility():
    """Toggles the visibility of motion paths for selected objects."""
    # Find the active 3D Viewport
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    # Toggle the motion paths overlay
                    space.overlay.show_motion_paths = not space.overlay.show_motion_paths
                    state = "enabled" if space.overlay.show_motion_paths else "disabled"
                    print(f"Motion Paths overlay {state}.")


class GenerateMotionPathOperator(bpy.types.Operator):
    """Generates motion paths for selected objects"""
    bl_idname = "object.generate_motion_path"
    bl_label = "Generate Motion Paths"
    bl_options = {'REGISTER', 'UNDO'}


    def execute(self, context):
        count = 0
        for ob in bpy.context.selected_objects:
            if create_motion_path(ob):
                count += 1
        
        self.report({'INFO'}, f"Generated motion paths for {count} objects.")
        return {'FINISHED'}
        
class RemoveMotionPathOperator(bpy.types.Operator):
    """Generates motion paths for selected objects"""
    bl_idname = "object.remove_motion_path"
    bl_label = "Remove Motion Paths"
    bl_options = {'REGISTER', 'UNDO'}


    def execute(self, context):
        count = 0
        for ob in bpy.context.selected_objects:
            if delete_motion_path(ob):
                count += 1
        
        self.report({'INFO'}, f"Generated motion paths for {count} objects.")
        return {'FINISHED'}

class ConvertAllObjectsOperator(bpy.types.Operator):
    """Converts all objects' motion paths to curves"""
    bl_idname = "object.convert_motion_path_all"
    bl_label = "Convert All Objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for ob in bpy.data.objects:
            if create_curve_from_motion_path(ob, context):
                count += 1

        self.report({'INFO'}, f"Converted {count} motion paths to curves.")
        return {'FINISHED'}


class ConvertSelectedObjectsOperator(bpy.types.Operator):
    """Converts selected objects' motion paths to curves"""
    bl_idname = "object.convert_motion_path_selected"
    bl_label = "Convert Selected Objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for ob in bpy.context.selected_objects:
            if create_curve_from_motion_path(ob, context):
                count += 1

        self.report({'INFO'}, f"Converted {count} motion paths to curves.")
        return {'FINISHED'}


class ToggleMotionPathVisibilityOperator(bpy.types.Operator):
    """Toggles the visibility of motion paths for selected objects"""
    bl_idname = "object.toggle_motion_path_visibility"
    bl_label = "Toggle Motion Paths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):        
        
        toggle_motion_path_visibility()
        self.report({'INFO'}, "Toggled motion path visibility.")
        return {'FINISHED'}



classes = (
    GenerateMotionPathOperator,
    RemoveMotionPathOperator,
    ConvertAllObjectsOperator,
    ConvertSelectedObjectsOperator,
    ToggleMotionPathVisibilityOperator,    
)


