import bpy
import os
import re
import math
import threading
import mathutils  # Blender's math utilities library
bl_info = {
    "name": "HVE FBX Import",
    "category": "Import-Export",
    "author": "EDC",
    "blender": (3, 1, 0),
}


# Default mapping used to identify which helper objects provide rotation
# data for each Euler axis.  Each axis maps to a list of keywords and any
# object whose name contains one of these keywords (case-insensitive) will be
# used as the source for that axis.  Adjust this mapping or pass a custom one
# to :func:`copy_animated_rotation` to support alternative naming schemes.
ROTATION_AXIS_KEYWORDS = {
    "X": ["Camber", "Cam"],     # X-axis rotation
    "Y": ["Rotation", "Pitch"],  # Y-axis rotation
    "Z": ["Steering", "Yaw"],   # Z-axis rotation
}


def normalize_root_name(name: str) -> str:
    """Return the base vehicle identifier without numeric suffixes or colon paths."""
    name = re.sub(r"\.\d+$", "", name)
    return name.split(":")[0]


def get_root_vehicle_names(imported_objects):
    """Collect unique top-level empty names representing vehicles."""
    vehicle_names = []
    for obj in imported_objects:
        if obj.type == "EMPTY" and obj.parent is None:
            root = normalize_root_name(obj.name)
            if root not in vehicle_names:
                vehicle_names.append(root)
    return vehicle_names


def belongs_to_vehicle(obj_name: str, vehicle_name: str) -> bool:
    """Return ``True`` if ``obj_name`` appears to belong to ``vehicle_name``.

    Object names in imported FBX files often include the vehicle identifier as
    a separate word within colon-delimited segments (e.g., ``"Mesh:0 Honda"``
    or ``"Wheel: Axle 1: Left Honda objects"``).  The original implementation
    required a segment to exactly match ``vehicle_name`` which failed for cases
    where the vehicle name was preceded by numbers or additional words.

    This revised version splits each colon-delimited segment into whitespace
    separated parts and checks whether any part, after stripping Blender's
    numeric suffixes, matches ``vehicle_name`` (case-insensitive).
    """

    vehicle_name = vehicle_name.lower()
    for segment in obj_name.split(":"):
        normalized = re.sub(r"\.\d+$", "", segment).lower().strip()
        if vehicle_name in normalized.split():
            return True
    return False

def offset_selected_animation(obj, frame_offset=-1):
    """Offsets animation keyframes for all selected objects by the given frame amount."""

    if obj.animation_data and obj.animation_data.action:
        action = obj.animation_data.action
        for fcurve in action.fcurves:
            for keyframe in fcurve.keyframe_points:
                keyframe.co.x += frame_offset  # Offset keyframe time
                keyframe.handle_left.x += frame_offset  # Offset left handle
                keyframe.handle_right.x += frame_offset  # Offset right handle



def adjust_animation(obj):
    """Adjusts animation for selected objects:
       - Subtracts 180° from X rotation
       - Scales Y and Z by -1
    """

    if obj.animation_data and obj.animation_data.action:
        action = obj.animation_data.action
        #print(obj)           
        for fcurve in action.fcurves:
            # Adjust X rotation (Euler)
            if fcurve.data_path.endswith("rotation_euler") and fcurve.array_index == 0:  # X Rotation
                for keyframe in fcurve.keyframe_points:
                    keyframe.co.y += math.radians(-180)  # Convert degrees to radians
                    keyframe.handle_left.y += math.radians(-180)
                    keyframe.handle_right.y += math.radians(-180)
        
        # Remove Scale Animation
        scale_fcurves = [fcurve for fcurve in action.fcurves if fcurve.data_path.endswith("scale")]
        for fcurve in scale_fcurves:
            action.fcurves.remove(fcurve)  # Delete scale animation
            
        obj.scale.y *= -1
        obj.scale.z *= -1
         
        obj.location = (0, 0, 0)
        obj.rotation_euler = (0, 0, 0)

        obj.keyframe_insert(data_path="location", frame=-1)
        obj.keyframe_insert(data_path="rotation_euler", frame=-1)
       
def copy_animated_rotation(parent, axis_keywords=None):
    """Copy rotation animation from axis-specific helper objects to ``parent``.

    Parameters
    ----------
    parent : bpy.types.Object
        Target empty to receive the rotation animation.
    axis_keywords : dict, optional
        Mapping of axis name ("X", "Y", "Z") to lists of name fragments.
        Objects whose names contain any of these fragments (case-insensitive)
        are used as rotation sources for the corresponding axis. If ``None``,
        :data:`ROTATION_AXIS_KEYWORDS` is used.

    Missing axes are skipped.
    """

    if not parent or parent.type != 'EMPTY':
        print("❌ Error: Please select an empty object as the target parent.")
        return

    axis_keywords = axis_keywords or ROTATION_AXIS_KEYWORDS

    # Get selected objects and filter by conditions
    selected_objects = [
        obj for obj in bpy.context.selected_objects
        if obj != parent and parent.name in obj.name and "objects" in obj.name.lower()
    ]

    if not selected_objects:
        print(f"❌ No matching objects found to parent under '{parent.name}'.")
        return

    # Set parent for filtered objects
    for obj in selected_objects:
        obj.parent = parent  # Set the selected objects' parent

    #print(f"✅ Parented {len(selected_objects)} objects to '{parent.name}': {[obj.name for obj in selected_objects]}")

    # Get selected objects (excluding the parent) and only keep objects that contain the parent's name
    selected_objects = [
        obj for obj in bpy.context.selected_objects
        if obj != parent and parent.name in obj.name
    ]

    # Initialize rotation source objects dictionary
    sources = {axis: None for axis in axis_keywords}

    # Assign source objects based on their names (case-insensitive partial match)
    for obj in selected_objects:
        name = obj.name.lower()
        for axis, keywords in axis_keywords.items():
            if any(k.lower() in name for k in keywords):
                sources[axis] = obj
                break

    missing = [axis for axis, src in sources.items() if src is None]
    if missing:
        print(f"⚠️ Warning: Missing rotation sources for axis: {', '.join(missing)}")

    # Ensure the parent has animation data
    if not parent.animation_data or not parent.animation_data.action:
        print(f"❌ Error: Parent '{parent.name}' has no existing animation.")
        return

    # Get the parent's existing action
    parent_action = parent.animation_data.action

    # Copy rotation keyframes from sources to the parent empty
    for axis_name, axis_index in zip(["Z", "Y", "X"], [2, 1, 0]):
        source = sources.get(axis_name)
        if not source or not (source.animation_data and source.animation_data.action):
            continue

        source_action = source.animation_data.action
        for fcurve in source_action.fcurves:
            # Check if the curve corresponds to rotation
            if fcurve.data_path.endswith("rotation_euler") and fcurve.array_index == axis_index:
                # Try to find an existing F-Curve for the parent
                parent_fcurve = None
                for existing_fcurve in parent_action.fcurves:
                    if existing_fcurve.data_path == "rotation_euler" and existing_fcurve.array_index == axis_index:
                        parent_fcurve = existing_fcurve
                        break

                # If no existing F-Curve, create one
                if not parent_fcurve:
                    parent_fcurve = parent_action.fcurves.new(
                        data_path="rotation_euler",
                        index=axis_index,
                        action_group="Rotation",
                    )

                # Clear existing keyframes in the parent F-Curve
                parent_fcurve.keyframe_points.clear()

                # Copy keyframe points from the source to the parent
                for keyframe in fcurve.keyframe_points:
                    parent_fcurve.keyframe_points.insert(
                        keyframe.co.x, keyframe.co.y, options={'FAST'}
                    )

                #print(f"✅ Replaced {axis_name} rotation from '{source.name}' → '{parent.name}'")

    #print(f"🎯 Finished replacing animated rotations for '{parent.name}'")

    # 🚀 DELETE the source objects after copying animation
    for source in sources.values():
        if source:
            bpy.data.objects.remove(source, do_unlink=True)

def remove_from_all_collections(obj):
    """Remove an object from all Blender collections before reassigning it.

    Iterates over a copy of ``obj.users_collection`` to avoid mutating the
    collection while unlinking, ensuring the object is removed from every
    collection that currently uses it.
    """
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)

def assign_objects_to_subcollection(collection_name, parent_collection, objects):
    """
    Create a subcollection under the given parent collection and assign objects to it.

    Parameters:
    - collection_name (str): Name of the subcollection.
    - parent_collection (bpy.types.Collection): Parent collection under which the subcollection will be created.
    - objects (list of bpy.types.Object]): List of objects to add to the subcollection.
    """
    if not parent_collection:
        print(f"Error: Parent collection '{parent_collection}' does not exist.")
        return

    # Ensure objects is a list
    if not isinstance(objects, list):
        objects = [objects]  # Convert single object to a list


    # Check if subcollection exists, if not, create it
    sub_collection = bpy.data.collections.get(collection_name)
    if not sub_collection:
        sub_collection = bpy.data.collections.new(collection_name)
        parent_collection.children.link(sub_collection)  # Add as a subcollection

    # Remove objects from existing collections and reassign them
    for obj in objects:
        if obj:
            remove_from_all_collections(obj)  # Remove from any existing collection
            if obj.name not in sub_collection.objects:
                sub_collection.objects.link(obj)

def assign_objects_to_collection(collection_name, objects):
    """
    Create a subcollection under the given parent collection and assign objects to it.

    Parameters:
    - collection_name (str.
    - objects (list of bpy.types.Object]): List of objects to add to the subcollection.
    """
    
    
    collection = bpy.data.collections.get(collection_name)
    if not collection:
        print(f"Error: Parent collection '{parent_collection}' does not exist.")
        return

    # Ensure objects is a list
    if not isinstance(objects, list):
        objects = [objects]  # Convert single object to a list

    # Remove objects from existing collections and reassign them
    for obj in objects:
        if obj:            
            if obj.name not in collection.objects:
                collection.objects.link(obj)

def ensure_collection_exists(collection_name, parent_collection=None, hide=False, dont_render=False):
    """
    Ensures that a Blender collection exists. If not, creates and links it to the scene or parent collection.

    Parameters:
    - collection_name (str): The name of the collection.
    - parent_collection (bpy.types.Collection, optional): The parent collection to link the new collection under.

    Returns:
    - bpy.types.Collection: The created or existing collection.
    """
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        collection = bpy.data.collections.new(collection_name)
        if parent_collection:
            parent_collection.children.link(collection)
        else:
            bpy.context.scene.collection.children.link(collection)  # Link to scene if no parent
        print(f"✅ Collection '{collection_name}' created successfully.")
    else:
        print(f"🔍 Collection '{collection_name}' already exists.")

    # Set visibility properties
    collection.hide_viewport = hide  # Hide from viewport
    collection.hide_render = dont_render    # Hide from rendering
    
    return collection

def bake_shape_keys_to_keyframes(obj):
    """Bakes shape key animations into keyframes only if the object has shape keys."""
    if not obj.data.shape_keys or not obj.data.shape_keys.animation_data:
        return  # Skip if no shape keys or no animation

    action = obj.data.shape_keys.animation_data.action
    frame_range = bpy.context.scene.frame_start, bpy.context.scene.frame_end

    for shape_key in obj.data.shape_keys.key_blocks:
        if shape_key.name == "Basis":
            continue  # Skip basis shape key

        fcurve = next(
            (fc for fc in action.fcurves if fc.data_path.endswith(f'key_blocks["{shape_key.name}"].value')),
            None
        )

        if fcurve:
            for frame in range(frame_range[0], frame_range[1] + 1, 10):  # Process every 5 frames (speeds up baking)
                shape_key.value = fcurve.evaluate(frame)
                shape_key.keyframe_insert(data_path="value", frame=frame)

    print(f"✅ Shape keys baked for {obj.name}")

def bake_shape_keys_threaded(obj_list):
    """Runs shape key baking in parallel threads for multiple objects."""
    threads = []
    for obj in obj_list:
        if obj.data.shape_keys:
            thread = threading.Thread(target=bake_shape_keys_to_keyframes, args=(obj,))
            thread.start()
            threads.append(thread)

    for thread in threads:
        thread.join()  # Wait for all threads to complete


def _gather_meshes(collection):
    """Recursively collect mesh objects from ``collection`` and its children."""
    meshes = [obj for obj in collection.objects if obj.type == "MESH"]
    for child in collection.children:
        meshes.extend(_gather_meshes(child))
    return meshes


def join_mesh_objects_per_vehicle(vehicle_names):
    """Joins all imported MESH objects per vehicle separately, after baking shape keys."""
    for vehicle_name in vehicle_names:
        # Collect all mesh objects for this vehicle. Search for collections that
        # begin with "Body Mesh: {vehicle_name}:". If found, use objects from
        # those collections. Otherwise fall back to scanning the entire scene.
        collection_prefix = f"Body Mesh: {vehicle_name}:"
        body_mesh_collections = [
            col for col in bpy.data.collections if col.name.startswith(collection_prefix)
        ]

        mesh_objects = []
        for col in body_mesh_collections:
            mesh_objects.extend(_gather_meshes(col))

        if not mesh_objects:
            candidates = bpy.context.scene.objects
            mesh_objects = [
                obj
                for obj in candidates
                if (
                    obj.type == "MESH"
                    and belongs_to_vehicle(obj.name, vehicle_name)
                    and not (
                        re.search(r"wheel", obj.name, re.IGNORECASE)
                        or any(
                            "Wheels" in col.name
                            for col in getattr(obj, "users_collection", [])
                        )
                    )
                )
            ]

        if len(mesh_objects) <= 1:
            if mesh_objects:
                print(
                    f"ℹ️ Only one Mesh object found for {vehicle_name}; no join required."
                )
            else:
                print(
                    f"⚠️ Not enough Mesh objects to join for {vehicle_name}. Skipping."
                )
            continue

        # Bake shape keys for these objects before joining
        bake_shape_keys_threaded(mesh_objects)

        # Deselect all objects to prevent unwanted merging
        bpy.ops.object.select_all(action="DESELECT")

        # Set the first valid object as active
        active_obj = mesh_objects[0]
        bpy.context.view_layer.objects.active = active_obj
        for obj in mesh_objects:
            obj.select_set(True)

        # Join the objects
        bpy.ops.object.join()

        # Deselect after join to avoid cross-vehicle merging
        bpy.ops.object.select_all(action="DESELECT")
        print(f"✅ Joined {len(mesh_objects)} Mesh objects for {vehicle_name}.")


def materials_are_equal(mat1, mat2, tol=1e-4):
    """Compare two materials including color, roughness, specular and diffuse textures."""
    if mat1.name == mat2.name:
        return False  # Skip if it's the same material

    def get_diffuse_texture(mat):
        if mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    for output in getattr(node, 'outputs', []):
                        for link in getattr(output, 'links', []):
                            if getattr(link.to_socket, 'name', '') == "Base Color":
                                return node
        return None

    tex1 = get_diffuse_texture(mat1)
    tex2 = get_diffuse_texture(mat2)

    if bool(tex1) != bool(tex2):
        return False
    if tex1 and tex2:
        image1 = getattr(tex1, 'image', None)
        image2 = getattr(tex2, 'image', None)
        path1 = getattr(image1, 'filepath', None) if image1 else None
        path2 = getattr(image2, 'filepath', None) if image2 else None
        if path1 != path2:
            return False
    else:
        if hasattr(mat1, 'diffuse_color') and hasattr(mat2, 'diffuse_color'):
            for i in range(3):
                if not math.isclose(mat1.diffuse_color[i], mat2.diffuse_color[i], abs_tol=tol):
                    return False
        else:
            return False

    def principled_params(mat):
        if mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    rough = node.inputs.get('Roughness')
                    spec = node.inputs.get('Specular')
                    rough_val = getattr(rough, 'default_value', None)
                    spec_val = getattr(spec, 'default_value', None)
                    return rough_val, spec_val
        return None, None

    r1, s1 = principled_params(mat1)
    r2, s2 = principled_params(mat2)

    if (r1 is None) != (r2 is None):
        return False
    if r1 is not None and not math.isclose(r1, r2, abs_tol=tol):
        return False
    if (s1 is None) != (s2 is None):
        return False
    if s1 is not None and not math.isclose(s1, s2, abs_tol=tol):
        return False

    return True

def find_duplicate_materials_for_vehicle(vehicle_name):
    """Find duplicate materials within a single vehicle's objects."""
    materials = []
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and belongs_to_vehicle(obj.name, vehicle_name):
            materials.extend([slot.material for slot in obj.material_slots if slot.material and slot.material.name.startswith("meshMaterial")])

    unique_materials = []
    material_map = {}

    for mat in materials:
        for unique_mat in unique_materials:
            if materials_are_equal(mat, unique_mat):
                material_map[mat] = unique_mat
                break
        else:
            unique_materials.append(mat)

    return material_map

def replace_materials_for_vehicle(vehicle_name, material_map):
    """Replace duplicate materials within a single vehicle's objects."""
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and belongs_to_vehicle(obj.name, vehicle_name):
            for slot in obj.material_slots:
                if slot.material in material_map:
                    slot.material = material_map[slot.material]

def remove_unused_materials():
    """Remove unused materials from Blender that start with 'meshMaterial' and have no users."""
    unused_materials = [mat for mat in bpy.data.materials if mat.name.startswith("meshMaterial") and not mat.users]
    for mat in unused_materials:
        bpy.data.materials.remove(mat)

def merge_duplicate_materials_per_vehicle(vehicle_names):
    """Runs material merging separately for each vehicle."""
    for vehicle_name in vehicle_names:
        print(f"🔍 Processing materials for {vehicle_name}...")
        material_map = find_duplicate_materials_for_vehicle(vehicle_name)
        if material_map:
            replace_materials_for_vehicle(vehicle_name, material_map)
            remove_unused_materials()
            print(f"✅ Merged {len(material_map)} duplicate 'meshMaterial' materials for {vehicle_name}.")
        else:
            print(f"✅ No duplicate 'meshMaterial' materials found for {vehicle_name}.")


    
def import_fbx(context, fbx_file_path):
    # Store the current frame rate settings
    original_fps = context.scene.render.fps
    original_fps_base = context.scene.render.fps_base

    """Do something with the selected file(s)."""
    filename = bpy.path.basename(fbx_file_path).split('.')[0] 
    
    # Ensure the file exists
    if os.path.exists(fbx_file_path):
        bpy.ops.import_scene.fbx(filepath=fbx_file_path)  # Import FBX
        print("FBX imported successfully!")
                
        # Get names of the newly imported objects
        imported_objects = bpy.context.selected_objects  # FBX import automatically selects new objects
        imported_names = [obj.name for obj in imported_objects]

        # Initialize max frame variable
        max_frame = 0
        
        # Find the highest keyframe in the imported animation
        for obj in imported_objects:
            if obj.animation_data and obj.animation_data.action:
                action = obj.animation_data.action
                for fcurve in action.fcurves:
                    for keyframe in fcurve.keyframe_points:
                        max_frame = max(max_frame, int(keyframe.co.x)) - 1 # Update max frame

        # Get the current frame end in Blender's timeline
        current_max_frame = context.scene.frame_end

        # Only update frame_end if the new max_frame is greater
        if max_frame > current_max_frame:
            context.scene.frame_end = max_frame
            #print(f"🎬 Timeline updated: New frame end set to {max_frame} (previous: {current_max_frame})")
        else:
            print(f"⏳ Timeline unchanged: Existing frame end ({current_max_frame}) is greater than or equal to imported max ({max_frame})")

        # Determine root vehicle names from imported objects
        vehicle_names = get_root_vehicle_names(imported_objects)

                
                
        # Define name replacements in sequential order
        name_replacements = {
            "Axle 2": "Axle 3:",
            "Axle 1": "Axle 2:",
            "Axle 0": "Axle 1:",
            "Left": "Left:",
            "Right": "Right:",
            "shapenode": "Mesh:"
        }

        # Loop through selected objects and apply replacements
        for obj in imported_objects:
            for old_part, new_part in name_replacements.items():
                if old_part in obj.name:  # Check if the old_part exists in the name
                    obj.name = obj.name.replace(old_part, new_part)  # Replace the text
        
        # Loop through selected objects and apply modifiers
        for obj in imported_objects:
            if ("Mesh" in obj.name or "Geometry" in obj.name) and obj.type == 'MESH':  # Ensure it's a mesh object
                # --- First Modifier: MergeByDistance ---
                existing_merge_modifier = None
                for mod in obj.modifiers:
                    if mod.type == 'NODES' and mod.name == "MergeByDistance":
                        existing_merge_modifier = mod
                        break

                if existing_merge_modifier is None:
                    merge_modifier = obj.modifiers.new(name="MergeByDistance", type='NODES')

                    # Check if the MergeByDistance node group exists
                    merge_node_group = bpy.data.node_groups.get("MergeByDistance")

                    if merge_node_group is None:
                        merge_node_group = bpy.data.node_groups.new(name="MergeByDistance", type='GeometryNodeTree')
                        merge_node_group.use_fake_user = True  # Prevent deletion
                        merge_node_group.is_modifier = True

                        # Add input and output nodes
                        input_node = merge_node_group.nodes.new(type='NodeGroupInput')
                        output_node = merge_node_group.nodes.new(type='NodeGroupOutput')

                        merge_node_group.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
                        merge_node_group.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

                        # Position nodes
                        input_node.location = (-200, 0)
                        output_node.location = (400, 0)

                        # Create Merge by Distance Node
                        merge_by_distance_node = merge_node_group.nodes.new(type='GeometryNodeMergeByDistance')
                        merge_by_distance_node.location = (0, 0)

                        # Connect nodes
                        merge_node_group.links.new(input_node.outputs["Geometry"], merge_by_distance_node.inputs["Geometry"])
                        merge_node_group.links.new(merge_by_distance_node.outputs["Geometry"], output_node.inputs["Geometry"])

                    # Assign the node group to the modifier
                    merge_modifier.node_group = merge_node_group
                else:
                    merge_modifier = existing_merge_modifier
                    print(f"Using existing 'MergeByDistance' modifier for {obj.name}.")

                # --- Second Modifier: Smooth by Angle ---
                existing_smooth_modifier = None
                for mod in obj.modifiers:
                    if mod.type == 'NODES' and mod.name == "SmoothByAngle":
                        existing_smooth_modifier = mod
                        break

                if existing_smooth_modifier is None:
                    smooth_modifier = obj.modifiers.new(name="SmoothByAngle", type='NODES')
                    
                     # Check if the SmoothByAngle node group exists
                    smooth_node_group = bpy.data.node_groups.get("SmoothByAngle")

                    if smooth_node_group is None:
                        # Create a new Geometry Nodes group
                        smooth_node_group = bpy.data.node_groups.new(name="SmoothByAngle", type='GeometryNodeTree')
                        smooth_node_group.use_fake_user = True  # Prevent deletion
                        smooth_node_group.is_modifier = True
                        
                        # Create Group Input and Group Output nodes
                        group_input = smooth_node_group.nodes.new(type="NodeGroupInput")
                        group_output = smooth_node_group.nodes.new(type="NodeGroupOutput")
                        group_input.location = (-400, 0)
                        group_output.location = (400, 0)


                        # Add inputs
                        input_mesh = smooth_node_group.interface.new_socket(name="Mesh", in_out='INPUT', socket_type='NodeSocketGeometry')
                        #input_angle = smooth_node_group.interface.new_socket(name="Angle", in_out='INPUT', socket_type='NodeSocketFloat')
                        input_ignore_sharpness = smooth_node_group.interface.new_socket(name="Ignore Sharpness", in_out='INPUT', socket_type='NodeSocketBool')

                        # Add outputs
                        output_mesh = smooth_node_group.interface.new_socket(name="Mesh", in_out='OUTPUT', socket_type='NodeSocketGeometry')
                        
                        #Create Angle value node
                        angle = smooth_node_group.nodes.new('ShaderNodeValue')
                        angle.outputs[0].default_value = 15.0
                        angle.location = (-400, -150)
                        
                        
                        # Create a Math Node and set it to "To Radians"
                        to_radians_node = smooth_node_group.nodes.new(type="ShaderNodeMath")  # Math Node
                        to_radians_node.operation = 'RADIANS'  # Set the operation to "To Radians"
                        to_radians_node.location = (-200, -150)  # Position in node ed                        itor
                        
                        # Create Edge Angle node
                        edge_angle = smooth_node_group.nodes.new('GeometryNodeInputMeshEdgeAngle')

                        # Create Less Than or Equal node
                        compare_angle = smooth_node_group.nodes.new('FunctionNodeCompare')
                        compare_angle.data_type = 'FLOAT'
                        compare_angle.operation = 'LESS_EQUAL'

                        # Create Is Edge Smooth node
                        is_edge_smooth = smooth_node_group.nodes.new('GeometryNodeInputEdgeSmooth')
                        #is_edge_smooth.domain = 'EDGE'                        
                        # Create Boolean OR for Edge Smoothness
                        boolean_or_edge = smooth_node_group.nodes.new('FunctionNodeBooleanMath')
                        boolean_or_edge.operation = 'OR'

                        # Create Boolean AND to combine conditions
                        boolean_and = smooth_node_group.nodes.new('FunctionNodeBooleanMath')
                        boolean_and.operation = 'AND'

                        # Create Set Shade Smooth (Edges)
                        set_shade_smooth_edge = smooth_node_group.nodes.new('GeometryNodeSetShadeSmooth')
                        set_shade_smooth_edge.domain = 'EDGE'
                        
                        # Create Is Face Smooth node
                        is_face_smooth = smooth_node_group.nodes.new('GeometryNodeInputShadeSmooth')

                        # Create Boolean OR for Face Smoothness
                        boolean_or_face = smooth_node_group.nodes.new('FunctionNodeBooleanMath')
                        boolean_or_face.operation = 'OR'

                        # Create Set Shade Smooth (Faces)
                        set_shade_smooth_face = smooth_node_group.nodes.new('GeometryNodeSetShadeSmooth')

                        # Connecting Nodes

                        smooth_node_group.links.new(edge_angle.outputs['Unsigned Angle'], compare_angle.inputs[0])            
                        smooth_node_group.links.new(angle.outputs['Value'], to_radians_node.inputs[0])
                        smooth_node_group.links.new(to_radians_node.outputs['Value'], compare_angle.inputs[1])
                        
                        smooth_node_group.links.new(compare_angle.outputs['Result'], boolean_and.inputs[0])

                        smooth_node_group.links.new(is_face_smooth.outputs['Smooth'], boolean_or_face.inputs[0])
                        smooth_node_group.links.new(group_input.outputs['Ignore Sharpness'], boolean_or_face.inputs[1])
                        smooth_node_group.links.new(boolean_or_face.outputs['Boolean'], boolean_and.inputs[1]) 
             
                        smooth_node_group.links.new(is_edge_smooth.outputs['Smooth'], boolean_or_edge.inputs[0])
                        smooth_node_group.links.new(group_input.outputs['Ignore Sharpness'], boolean_or_edge.inputs[1])

                        smooth_node_group.links.new(boolean_or_edge.outputs['Boolean'], set_shade_smooth_edge.inputs['Selection'])
                        smooth_node_group.links.new(group_input.outputs['Mesh'], set_shade_smooth_edge.inputs['Geometry'])
                        smooth_node_group.links.new(boolean_and.outputs['Boolean'], set_shade_smooth_edge.inputs['Shade Smooth'])           
                  
                        smooth_node_group.links.new(set_shade_smooth_edge.outputs['Geometry'], set_shade_smooth_face.inputs['Geometry'])            
                        smooth_node_group.links.new(set_shade_smooth_face.outputs['Geometry'], group_output.inputs['Mesh'])

                    # Assign the node group to the modifier
                    smooth_modifier.node_group = smooth_node_group
                else:
                    smooth_modifier = existing_smooth_modifier
                    print(f"Using existing 'SmoothByAngle' modifier for {obj.name}.")




        # Loop through imported objects
        for obj in imported_objects:
            # Offset keyframes for all selected objects by 1 frame
            offset_selected_animation(obj,frame_offset=-1) 
  
        # List of keywords to exclude from selection
        exclude_keywords = ["Wheel:", "shapenode"]  # Modify as needed     
       
        # Loop through imported objects
        for obj in imported_objects:
            # Check if none of the exclude keywords are in the object name
            if not any(keyword in obj.name for keyword in exclude_keywords):
                obj.select_set(True)  # Select the object

                # Run function to adjust X rotation and scale for selected objects
                adjust_animation(obj)      
                
                
        # Derive keywords used for rotation helpers so they aren't processed as wheels
        exclude_keywords = [
            kw.lower() for kws in ROTATION_AXIS_KEYWORDS.values() for kw in kws
        ]
        exclude_keywords += ["objects", "geometry"]
        include_keywords = ["wheel"]

        # Loop through imported objects
        for obj in imported_objects:
            try:
                name = obj.name
            except ReferenceError:
                # Object was removed (e.g. by copy_animated_rotation); skip it
                continue

            name_lower = name.lower()

            # Condition: Name must contain at least one include keyword AND none of the exclude keywords
            if any(kw in name_lower for kw in include_keywords) and not any(
                kw in name_lower for kw in exclude_keywords
            ):
                obj.select_set(True)  # Select the object
                # Run the function
                copy_animated_rotation(obj)

                # Rename the object by adding "_FBX" to the end of its name
                if not name.endswith(": FBX"):
                    obj.name = f"{name}: FBX"

        # Create the event collection
        event_collection_name = f"HVE: {filename}"
        event_collection = ensure_collection_exists(event_collection_name, bpy.context.scene.collection, hide = False, dont_render=False)
 
        # Ensure the layer collection exists before setting it as active
        layer_collection = None
        for lc in bpy.context.view_layer.layer_collection.children:
            if lc.name == event_collection.name:
                layer_collection = lc
                break

        if layer_collection:
            bpy.context.view_layer.active_layer_collection = layer_collection


        # Move all selected objects to a new collection
        for vehicle_name in vehicle_names:
            # Remove any trailing '.###' from vehicle_name (e.g., 'Car.001' -> 'Car')
            clean_vehicle_name = re.sub(r'\.\d+$', '', vehicle_name)

        
            fbx_collection_name = f"HVE: {filename}: {vehicle_name}: FBX"            
            fbx_collection = ensure_collection_exists(fbx_collection_name, event_collection, hide = False, dont_render=False)
            
            # Ensure the layer collection exists before setting it as active
            layer_collection = None
            for lc in bpy.context.view_layer.layer_collection.children:
                if lc.name == fbx_collection.name:
                    layer_collection = lc
                    break

            if layer_collection:
                bpy.context.view_layer.active_layer_collection = layer_collection

            # Move objects to the collection
            for obj in bpy.context.selected_objects:
                if belongs_to_vehicle(obj.name, clean_vehicle_name):
                    # Remove object from other collections (if necessary)
                    for coll in obj.users_collection:
                        coll.objects.unlink(obj)
                    
                    # Add to the new collection
                    fbx_collection.objects.link(obj)     
 

            # Create subcollections 
            wheels_collection_name = f"Wheels: {vehicle_name}: {filename}: FBX"
            wheels_collection = ensure_collection_exists(wheels_collection_name, fbx_collection, hide = False, dont_render=False)       
       
            mesh_collection_name = f"Body Mesh: {vehicle_name}: {filename}: FBX"
            mesh_collection = ensure_collection_exists(mesh_collection_name, fbx_collection, hide = False, dont_render=False)       
        
            # Loop through imported objects
            for obj in bpy.context.selected_objects:
                # Condition: Name must contain at least one include keyword AND none of the exclude keywords
                if ("Wheel" in obj.name and belongs_to_vehicle(obj.name, vehicle_name)):
                    obj.select_set(True)  # Select the object
                    # Run the function
                    assign_objects_to_subcollection(wheels_collection_name, fbx_collection, obj)
                if ("Mesh" in obj.name and belongs_to_vehicle(obj.name, vehicle_name)):
                    obj.select_set(True)  # Select the object
                    # Run the function
                    assign_objects_to_subcollection(mesh_collection_name, fbx_collection, obj)
            
            target_name = vehicle_name + ": FBX"  # Original name pattern
            new_name = f"CG: {vehicle_name} {filename}: FBX"  # New name pattern

            for obj in bpy.context.selected_objects:
                          
                if obj.name == target_name:
                    obj.name = new_name
                    print(f"Renamed: {target_name} → {new_name}")
                    
        # Join Mesh objects separately for each vehicle
        join_mesh_objects_per_vehicle(vehicle_names)    

        # Replace duplicate materials
        merge_duplicate_materials_per_vehicle(vehicle_names)
 
       # Restore the original frame rate settings
        context.scene.render.fps = original_fps
        context.scene.render.fps_base = original_fps_base
        print(f"🔄 Frame rate restored to {original_fps}/{original_fps_base}")
        
        context.scene.frame_start = 0
        bpy.ops.file.find_missing_files(directory="C:\\Users\\Public\\HVE\\supportfiles")
        
        
    else:
        print("Error: File not found!")

    
    
def load(context,
         filepath,
         ):


    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT') 
        
    dirname = os.path.dirname(filepath)        

    import_fbx(context, 
            filepath, 
            )

    return {'FINISHED'}


