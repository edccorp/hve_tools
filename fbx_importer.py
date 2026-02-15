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

MATERIAL_NAME_PREFIXES = ("meshMaterial",)


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


def normalize_name(name: str) -> str:
    """Return a lowercase name with underscores replaced by spaces."""
    return name.lower().replace("_", " ")


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

    Both names are normalized by replacing underscores with spaces and splitting
    into lowercase tokens using ``re.split('[\\W_]+')``. The vehicle tokens are
    then matched against consecutive tokens from each colon-delimited segment of
    ``obj_name``.  Trailing numeric tokens or generic ``"object(s)"`` tokens, as
    well as common wheel descriptors like ``"wheel"``, ``"tire"``,
    ``"geometry"``, or ``"steering"``, are ignored to allow names like
    ``"Wheel_FL: Heil Rear Wheel"``.

    Examples
    --------
    >>> belongs_to_vehicle('Wheel_FL: Heil Rear Wheel', 'Heil_Rear')
    True
    >>> belongs_to_vehicle('Wheel_FL: Heil Rear Wheel', 'Heil')
    False
    """

    vehicle_tokens = [
        t
        for t in re.split(r"[\W_]+", vehicle_name.replace("_", " ").lower())
        if t
    ]
    obj_name = obj_name.replace("_", " ")

    for segment in obj_name.split(":"):
        # Strip Blender numeric suffixes like ".001" before tokenizing
        segment = re.sub(r"\.\d+$", "", segment).lower()
        tokens = [t for t in re.split(r"[\W_]+", segment) if t]
        for i in range(len(tokens) - len(vehicle_tokens) + 1):
            if tokens[i : i + len(vehicle_tokens)] == vehicle_tokens:
                trailing = tokens[i + len(vehicle_tokens) :]
                if all(
                    t.isdigit()
                    or t
                    in {
                        "object",
                        "objects",
                        "wheel",
                        "wheels",
                        "tire",
                        "tires",
                        "geometry",
                        "steering",
                    }
                    for t in trailing
                ):
                    return True
    return False


def is_wheel_object(obj):
    """Return ``True`` if ``obj`` or any parent name contains ``wheel`` or ``tire``."""
    current = obj
    while current:
        name_lower = current.name.lower()
        if "wheel" in name_lower or "tire" in name_lower:
            return True
        current = current.parent
    return False


def _iter_layered_fcurve_collections(action):
    """Yield F-Curve collections from layered actions (Blender 5+)."""
    layers = getattr(action, "layers", None)
    if not layers:
        return

    for layer in layers:
        strips = getattr(layer, "strips", None) or ()
        for strip in strips:
            # Layered strips commonly expose channel bags directly.
            channelbags = getattr(strip, "channelbags", None) or ()
            for bag in channelbags:
                fcurves = getattr(bag, "fcurves", None)
                if fcurves is not None:
                    yield fcurves


def get_action_fcurve_collection(action):
    """Return the action F-Curve collection when available.

    Blender 5+ may return action types that no longer expose ``action.fcurves``
    directly. Returning ``None`` allows callers to safely skip direct F-Curve
    edits without raising ``AttributeError``.
    """
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        return fcurves

    for layered_fcurves in _iter_layered_fcurve_collections(action):
        return layered_fcurves

    return None


def iter_action_fcurve_collections(action):
    """Iterate all available F-Curve collections from an action."""
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        yield fcurves

    for layered_fcurves in _iter_layered_fcurve_collections(action):
        yield layered_fcurves


def iter_action_fcurves(action):
    """Iterate over F-Curves from ``action`` when supported."""
    for fcurve_collection in iter_action_fcurve_collections(action):
        for fcurve in fcurve_collection:
            yield fcurve


def offset_selected_animation(obj, frame_offset=-1, target_start_frame=0):
    """Offsets animation keyframes for all selected objects by the given frame amount."""

    if obj.animation_data and obj.animation_data.action:
        action = obj.animation_data.action
        if frame_offset is None:
            first_frame = None
            for fcurve in iter_action_fcurves(action):
                for keyframe in fcurve.keyframe_points:
                    if first_frame is None or keyframe.co.x < first_frame:
                        first_frame = keyframe.co.x

            if first_frame is None:
                return
            frame_offset = target_start_frame - first_frame

        if frame_offset == 0:
            return

        for fcurve in iter_action_fcurves(action):
            for keyframe in fcurve.keyframe_points:
                keyframe.co.x += frame_offset  # Offset keyframe time
                keyframe.handle_left.x += frame_offset  # Offset left handle
                keyframe.handle_right.x += frame_offset  # Offset right handle





def zero_main_vehicle_empty_transform_at_preroll(imported_objects, frame=-1):
    """Set top-level vehicle empties to zero location/rotation at ``frame``."""
    for obj in imported_objects:
        if obj.type != "EMPTY" or obj.parent is not None:
            continue
        if not (obj.animation_data and obj.animation_data.action):
            continue

        obj.location = (0.0, 0.0, 0.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.keyframe_insert(data_path="location", frame=frame)
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def ensure_preroll_keys(action, target_frame=-1):
    """Duplicate first location/rotation keys to ``target_frame`` when missing.

    This preserves the imported starting pose for a pre-roll frame instead of
    inserting synthetic zeroed transforms.
    """
    for fcurve_collection in iter_action_fcurve_collections(action):
        for fcurve in fcurve_collection:
            if not (
                fcurve.data_path.endswith("location")
                or fcurve.data_path.endswith("rotation_euler")
            ):
                continue

            keyframes = list(fcurve.keyframe_points)
            if not keyframes:
                continue

            # Skip if a preroll key already exists.
            if any(abs(k.co.x - target_frame) < 1e-6 for k in keyframes):
                continue

            first_key = min(keyframes, key=lambda k: k.co.x)
            if first_key.co.x < target_frame:
                continue

            new_key = fcurve.keyframe_points.insert(
                target_frame, first_key.co.y, options={'FAST'}
            )
            new_key.interpolation = first_key.interpolation

def adjust_animation(obj):
    """Adjusts animation for selected objects:
       - Subtracts 180° from X rotation
       - Scales Y and Z by -1
    """

    if obj.animation_data and obj.animation_data.action:
        action = obj.animation_data.action
        action_fcurves = get_action_fcurve_collection(action)
        #print(obj)           
        for fcurve in iter_action_fcurves(action):
            # Adjust X rotation (Euler)
            if fcurve.data_path.endswith("rotation_euler") and fcurve.array_index == 0:  # X Rotation
                for keyframe in fcurve.keyframe_points:
                    keyframe.co.y += math.radians(-180)  # Convert degrees to radians
                    keyframe.handle_left.y += math.radians(-180)
                    keyframe.handle_right.y += math.radians(-180)
        
        # Remove Scale Animation
        if action_fcurves is not None:
            scale_fcurves = [fcurve for fcurve in action_fcurves if fcurve.data_path.endswith("scale")]
            for fcurve in scale_fcurves:
                action_fcurves.remove(fcurve)  # Delete scale animation
            
        obj.scale.y *= -1
        obj.scale.z *= -1
         
        # Preserve a pre-roll frame by duplicating the first imported pose at
        # frame ``-1`` without forcing zero transforms.
        ensure_preroll_keys(action, target_frame=-1)
       
def copy_animated_rotation(parent, axis_keywords=None, debug=False):
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
    debug : bool, optional
        When ``True``, log details about source selection. Defaults to ``False``.

    Missing axes are skipped.
    """

    if not parent or parent.type != 'EMPTY':
        print("❌ Error: Please select an empty object as the target parent.")
        return

    axis_keywords = axis_keywords or ROTATION_AXIS_KEYWORDS

    norm_parent = normalize_name(parent.name)
    vehicle_id = parent.name.split(":")[-1].strip()
    if debug:
        print(f"🛠 Normalized parent name: '{norm_parent}'")

    # Get selected objects and filter by conditions
    selected_objects = [
        obj
        for obj in bpy.context.selected_objects
        if obj != parent
        and norm_parent in normalize_name(obj.name)
        and "objects" in obj.name.lower()
        and belongs_to_vehicle(obj.name, vehicle_id)
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
        obj
        for obj in bpy.context.selected_objects
        if obj != parent
        and norm_parent in normalize_name(obj.name)
        and belongs_to_vehicle(obj.name, vehicle_id)
    ]
    if debug:
        print(f"🛠 Candidate helper objects: {[obj.name for obj in selected_objects]}")

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
    if debug:
        print("🛠 Axis mapping:")
        for axis, src in sources.items():
            if src:
                print(f"   {axis} → {src.name}")
            else:
                print(f"   {axis} → <missing>")
        if missing:
            print(f"   Missing axes: {', '.join(missing)}")

    if missing:
        print(f"⚠️ Warning: Missing rotation sources for axis: {', '.join(missing)}")

    if debug and all(src is None for src in sources.values()):
        print(f"⚠️ No rotation sources found for '{parent.name}'")

    # Ensure the parent has animation data
    if not parent.animation_data or not parent.animation_data.action:
        print(f"❌ Error: Parent '{parent.name}' has no existing animation.")
        return

    # Get the parent's existing action
    parent_action = parent.animation_data.action
    parent_action_fcurves = get_action_fcurve_collection(parent_action)
    if parent_action_fcurves is None:
        print(f"⚠️ Warning: Parent '{parent.name}' action has no direct fcurve collection; skipping rotation copy.")
        return

    # Copy rotation keyframes from sources to the parent empty
    for axis_name, axis_index in zip(["Z", "Y", "X"], [2, 1, 0]):
        source = sources.get(axis_name)
        if not source or not (source.animation_data and source.animation_data.action):
            continue

        source_action = source.animation_data.action
        for fcurve in iter_action_fcurves(source_action):
            # Check if the curve corresponds to rotation
            if fcurve.data_path.endswith("rotation_euler") and fcurve.array_index == axis_index:
                # Try to find an existing F-Curve for the parent
                parent_fcurve = None
                for existing_fcurve in parent_action_fcurves:
                    if existing_fcurve.data_path == "rotation_euler" and existing_fcurve.array_index == axis_index:
                        parent_fcurve = existing_fcurve
                        break

                # If no existing F-Curve, create one
                if not parent_fcurve:
                    parent_fcurve = parent_action_fcurves.new(
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

    # The scene's master collection is not included in ``obj.users_collection``,
    # so explicitly unlink from it as well to ensure the object is fully
    # detached before relinking.
    active_root = bpy.context.scene.collection
    if obj.name in active_root.objects:
        active_root.objects.unlink(obj)

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
    action_fcurves = get_action_fcurve_collection(action)
    if action_fcurves is None:
        return
    frame_range = bpy.context.scene.frame_start, bpy.context.scene.frame_end

    for shape_key in obj.data.shape_keys.key_blocks:
        if shape_key.name == "Basis":
            continue  # Skip basis shape key

        fcurve = next(
            (fc for fc in action_fcurves if fc.data_path.endswith(f'key_blocks["{shape_key.name}"].value')),
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


def join_mesh_objects_per_vehicle(vehicle_names, imported_objects=None, imported_pointer_set=None):
    """Joins all imported MESH objects per vehicle separately, after baking shape keys."""

    def object_pointer(obj):
        return obj.as_pointer() if hasattr(obj, "as_pointer") else id(obj)

    if imported_objects is None:
        imported_objects = list(getattr(getattr(bpy.context, "scene", None), "objects", []))

    if imported_pointer_set is None:
        imported_pointer_set = {object_pointer(obj) for obj in imported_objects}
    else:
        imported_pointer_set = set(imported_pointer_set)

    for vehicle_name in vehicle_names:
        clean_vehicle_name = re.sub(r'\.\d+$', '', vehicle_name)
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

        mesh_objects = [
            obj for obj in mesh_objects if object_pointer(obj) in imported_pointer_set
        ]

        if not mesh_objects:
            mesh_objects = [
                obj
                for obj in imported_objects
                if (
                    obj.type == "MESH"
                    and object_pointer(obj) in imported_pointer_set
                    and belongs_to_vehicle(obj.name, clean_vehicle_name)
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
        print(f"✅ Joined {len(mesh_objects)} Mesh objects for {clean_vehicle_name}.")


def _normalize_image_path(image):
    """Resolve a stable absolute path for image comparisons."""
    if not image:
        return None
    filepath = getattr(image, 'filepath', None)
    if not filepath:
        return None
    resolved = bpy.path.abspath(filepath)
    return os.path.normcase(os.path.normpath(resolved))


def _get_principled_node(mat):
    if mat.node_tree:
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                return node
    return None


def _get_linked_image_path(principled_node, socket_name):
    if not principled_node:
        return None
    socket = principled_node.inputs.get(socket_name)
    if not socket:
        return None
    for link in getattr(socket, 'links', []):
        from_node = getattr(link, 'from_node', None)
        if from_node and from_node.type == 'TEX_IMAGE':
            return _normalize_image_path(getattr(from_node, 'image', None))
    return None


def _socket_value_signature(value):
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_socket_value_signature(v) for v in value)
    if hasattr(value, '__iter__'):
        return tuple(value)
    return repr(value)


def _socket_default_value_signature(socket):
    """Return a hashable representation of a socket's default value."""
    if socket is None:
        return None
    value = getattr(socket, 'default_value', None)
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_socket_value_signature(v) for v in value)
    # mathutils vectors/colors expose iterable protocol but are not hashable.
    if hasattr(value, '__iter__'):
        return tuple(value)
    return repr(value)


def _material_node_tree_signature(material):
    """Build a conservative signature for node-based material comparison."""
    if not getattr(material, 'use_nodes', False):
        return None

    node_tree = getattr(material, 'node_tree', None)
    nodes = getattr(node_tree, 'nodes', None)
    if nodes is None:
        return None

    node_list = list(nodes)
    node_index_map = {
        (node.as_pointer() if hasattr(node, 'as_pointer') else id(node)): index
        for index, node in enumerate(node_list)
    }

    node_signatures = []
    for index, node in enumerate(node_list):
        node_type = getattr(node, 'type', None)
        node_props = []

        if node_type == 'TEX_IMAGE':
            image = getattr(node, 'image', None)
            colorspace = getattr(getattr(image, 'colorspace_settings', None), 'name', None)
            node_props.extend([
                ('image_path', _normalize_image_path(image)),
                ('image_colorspace', colorspace),
                ('interpolation', getattr(node, 'interpolation', None)),
                ('projection', getattr(node, 'projection', None)),
                ('extension', getattr(node, 'extension', None)),
            ])

        input_values = []
        for socket_name, socket in sorted(getattr(node, 'inputs', {}).items(), key=lambda item: item[0]):
            links = getattr(socket, 'links', None) or []
            if links:
                link_targets = []
                for link in links:
                    from_node = getattr(link, 'from_node', None)
                    from_socket = getattr(link, 'from_socket', None)
                    from_id = from_node.as_pointer() if hasattr(from_node, 'as_pointer') else id(from_node)
                    from_index = node_index_map.get(from_id)
                    link_targets.append((
                        from_index,
                        getattr(from_node, 'type', None),
                        getattr(from_socket, 'name', None),
                    ))
                input_values.append((socket_name, ('LINKED', tuple(sorted(link_targets)))))
            else:
                input_values.append((socket_name, _socket_default_value_signature(socket)))

        node_signatures.append((index, node_type, tuple(node_props), tuple(input_values)))

    return tuple(node_signatures)


def materials_are_equal(mat1, mat2, tol=1e-4):
    """Compare two materials using shader settings and linked texture paths."""
    if mat1 == mat2:
        return True

    def _material_setting(material, *attribute_names):
        """Read the first available material setting across Blender versions."""
        for attribute_name in attribute_names:
            if hasattr(material, attribute_name):
                return getattr(material, attribute_name)
        return None

    if (
        mat1.use_nodes != mat2.use_nodes
        or _material_setting(mat1, 'blend_method', 'surface_render_method')
        != _material_setting(mat2, 'blend_method', 'surface_render_method')
        or _material_setting(mat1, 'shadow_method')
        != _material_setting(mat2, 'shadow_method')
        or _material_setting(mat1, 'use_backface_culling', 'show_transparent_back')
        != _material_setting(mat2, 'use_backface_culling', 'show_transparent_back')
    ):
        return False

    if any(
        not math.isclose(mat1.diffuse_color[i], mat2.diffuse_color[i], abs_tol=tol)
        for i in range(4)
    ):
        return False

    principled1 = _get_principled_node(mat1)
    principled2 = _get_principled_node(mat2)
    if bool(principled1) != bool(principled2):
        return False

    if principled1 and principled2:
        for param in ('Roughness', 'Specular', 'Metallic', 'Alpha'):
            input1 = principled1.inputs.get(param)
            input2 = principled2.inputs.get(param)
            value1 = getattr(input1, 'default_value', None)
            value2 = getattr(input2, 'default_value', None)
            if (value1 is None) != (value2 is None):
                return False
            if value1 is not None and not math.isclose(value1, value2, abs_tol=tol):
                return False

        for texture_socket in (
            'Base Color',
            'Roughness',
            'Metallic',
            'Normal',
            'Alpha',
            'Emission Color',
            'Emission',
        ):
            path1 = _get_linked_image_path(principled1, texture_socket)
            path2 = _get_linked_image_path(principled2, texture_socket)
            if path1 != path2:
                return False

    if _material_node_tree_signature(mat1) != _material_node_tree_signature(mat2):
        return False

    return True




def _material_base_name(name):
    """Return the material name without Blender's numeric duplicate suffix."""
    if not name:
        return name
    return re.sub(r"\.\d+$", "", name)


def _materials_can_merge_by_name(mat1, mat2):
    """Only merge materials that are duplicate instances of the same base name."""
    return _material_base_name(mat1.name) == _material_base_name(mat2.name)


def find_duplicate_materials_for_vehicle(vehicle_name, candidate_objects=None):
    """Find duplicate materials within a single vehicle's objects."""
    clean_vehicle_name = re.sub(r'\.\d+$', '', vehicle_name)
    materials = []
    seen_materials = set()
    objects = candidate_objects if candidate_objects is not None else bpy.data.objects
    for obj in objects:
        if obj is None:
            continue
        try:
            obj_type = obj.type
            obj_name = obj.name
        except ReferenceError:
            # Object was removed from Blender data (dangling StructRNA reference).
            continue
        if obj_type == 'MESH' and belongs_to_vehicle(obj_name, clean_vehicle_name):
            for slot in obj.material_slots:
                mat = slot.material
                if not mat:
                    continue
                if not mat.name.startswith(MATERIAL_NAME_PREFIXES):
                    continue
                mat_ptr = mat.as_pointer() if hasattr(mat, 'as_pointer') else id(mat)
                if mat_ptr in seen_materials:
                    continue
                seen_materials.add(mat_ptr)
                materials.append(mat)

    unique_materials = []
    material_map = {}

    for mat in materials:
        for unique_mat in unique_materials:
            if _materials_can_merge_by_name(mat, unique_mat) and materials_are_equal(mat, unique_mat):
                material_map[mat] = unique_mat
                break
        else:
            unique_materials.append(mat)

    return material_map


def deduplicate_material_slots_for_vehicle(vehicle_name, candidate_objects=None):
    """Remove duplicate material slots within each mesh object for a vehicle."""
    clean_vehicle_name = re.sub(r'\.\d+$', '', vehicle_name)
    objects = candidate_objects if candidate_objects is not None else bpy.data.objects
    removed_slots = 0

    for obj in objects:
        if obj is None:
            continue
        try:
            obj_type = obj.type
            obj_name = obj.name
            slots = list(obj.material_slots)
        except ReferenceError:
            continue

        if obj_type != 'MESH' or not belongs_to_vehicle(obj_name, clean_vehicle_name):
            continue
        if len(slots) < 2:
            continue

        unique_materials = []
        material_index_map = {}
        polygon_index_map = {}

        for index, slot in enumerate(slots):
            mat = slot.material
            mat_key = mat.as_pointer() if hasattr(mat, 'as_pointer') else id(mat)
            if mat_key not in material_index_map:
                material_index_map[mat_key] = len(unique_materials)
                unique_materials.append(mat)
            polygon_index_map[index] = material_index_map[mat_key]

        if len(unique_materials) == len(slots):
            continue

        mesh_data = getattr(obj, 'data', None)
        polygons = getattr(mesh_data, 'polygons', None)
        if polygons is not None:
            for poly in polygons:
                poly.material_index = polygon_index_map.get(poly.material_index, 0)

        mesh_materials = getattr(mesh_data, 'materials', None)
        if mesh_materials is not None and hasattr(mesh_materials, 'clear') and hasattr(mesh_materials, 'append'):
            mesh_materials.clear()
            for mat in unique_materials:
                mesh_materials.append(mat)
        elif isinstance(obj.material_slots, list):
            deduped_slots = []
            seen_keys = set()
            for slot in obj.material_slots:
                mat = slot.material
                mat_key = mat.as_pointer() if hasattr(mat, 'as_pointer') else id(mat)
                if mat_key in seen_keys:
                    continue
                seen_keys.add(mat_key)
                deduped_slots.append(slot)
            obj.material_slots[:] = deduped_slots

        removed_slots += len(slots) - len(unique_materials)

    return removed_slots


def replace_materials_for_vehicle(vehicle_name, material_map, candidate_objects=None):
    """Replace duplicate materials within a single vehicle's objects."""
    clean_vehicle_name = re.sub(r'\.\d+$', '', vehicle_name)
    objects = candidate_objects if candidate_objects is not None else bpy.data.objects
    for obj in objects:
        if obj is None:
            continue
        try:
            obj_type = obj.type
            obj_name = obj.name
        except ReferenceError:
            # Object was removed from Blender data (dangling StructRNA reference).
            continue
        if obj_type == 'MESH' and belongs_to_vehicle(obj_name, clean_vehicle_name):
            for slot in obj.material_slots:
                if slot.material in material_map:
                    slot.material = material_map[slot.material]

def remove_unused_materials():
    """Remove unused materials from Blender that start with 'meshMaterial' and have no users."""
    unused_materials = [mat for mat in bpy.data.materials if mat.name.startswith(MATERIAL_NAME_PREFIXES) and not mat.users]
    for mat in unused_materials:
        bpy.data.materials.remove(mat)

def merge_duplicate_materials_per_vehicle(vehicle_names, candidate_objects=None):
    """Runs material merging separately for each vehicle."""
    for vehicle_name in vehicle_names:
        clean_vehicle_name = re.sub(r'\.\d+$', '', vehicle_name)
        print(f"🔍 Processing materials for {clean_vehicle_name}...")
        material_map = find_duplicate_materials_for_vehicle(clean_vehicle_name, candidate_objects=candidate_objects)
        if material_map:
            replace_materials_for_vehicle(clean_vehicle_name, material_map, candidate_objects=candidate_objects)
            remove_unused_materials()

        removed_slots = deduplicate_material_slots_for_vehicle(
            clean_vehicle_name,
            candidate_objects=candidate_objects,
        )

        if material_map:
            print(f"✅ Merged {len(material_map)} duplicate 'meshMaterial' materials for {clean_vehicle_name}.")
        else:
            print(f"✅ No duplicate 'meshMaterial' materials found for {clean_vehicle_name}.")

        if removed_slots:
            print(f"✅ Removed {removed_slots} duplicate material slots for {clean_vehicle_name}.")


    
def import_fbx(context, fbx_file_path):
    # Store the current frame rate settings
    original_fps = context.scene.render.fps
    original_fps_base = context.scene.render.fps_base

    """Do something with the selected file(s)."""
    filename = bpy.path.basename(fbx_file_path).split('.')[0] 
    
    # Ensure the file exists
    if os.path.exists(fbx_file_path):
        # Capture existing scene objects before import so we can diff afterwards
        pre_import_ids = {obj.as_pointer() for obj in bpy.context.scene.objects}
        bpy.ops.import_scene.fbx(filepath=fbx_file_path)  # Import FBX
        print("FBX imported successfully!")

        # Determine which objects were added by the import
        post_import_objects = list(bpy.context.scene.objects)
        imported_objects = [obj for obj in post_import_objects if obj.as_pointer() not in pre_import_ids]
        imported_pointer_set = {obj.as_pointer() for obj in imported_objects}
        imported_names = [obj.name for obj in imported_objects]

        # Initialize max frame variable
        max_frame = 0
        
        # Find the highest keyframe in the imported animation
        for obj in imported_objects:
            if obj.animation_data and obj.animation_data.action:
                action = obj.animation_data.action
                fcurve_found = False
                for fcurve in iter_action_fcurves(action):
                    fcurve_found = True
                    for keyframe in fcurve.keyframe_points:
                        max_frame = max(max_frame, int(keyframe.co.x)) - 1 # Update max frame

                if not fcurve_found:
                    frame_end = int(action.frame_range[1]) - 1
                    max_frame = max(max_frame, frame_end)

        # Get the current frame end in Blender's timeline
        current_max_frame = context.scene.frame_end

        # Only update frame_end if the new max_frame is greater
        if max_frame > current_max_frame:
            context.scene.frame_end = max_frame
            #print(f"🎬 Timeline updated: New frame end set to {max_frame} (previous: {current_max_frame})")
        else:
            print(f"⏳ Timeline unchanged: Existing frame end ({current_max_frame}) is greater than or equal to imported max ({max_frame})")

                
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
            offset_selected_animation(obj, frame_offset=None, target_start_frame=0)
  
        # List of keywords to exclude from selection
        exclude_keywords = ["Wheel:", "shapenode"]  # Modify as needed     
       
        # Loop through imported objects
        for obj in imported_objects:
            # Check if none of the exclude keywords are in the object name
            if not any(keyword in obj.name for keyword in exclude_keywords):
                obj.select_set(True)  # Select the object

                # Run function to adjust X rotation and scale for selected objects
                adjust_animation(obj)

        zero_main_vehicle_empty_transform_at_preroll(imported_objects, frame=-1)

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
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)  # Select the object
                # Run the function
                copy_animated_rotation(obj, debug=True)

                # Rename the object by adding "_FBX" to the end of its name
                if not name.endswith(": FBX"):
                    obj.name = f"{name}: FBX"

        # Determine root vehicle names after any renaming or cleanup
        vehicle_names = get_root_vehicle_names(imported_objects)

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


        # Track which FBX collection each object ends up in
        object_collections = {}

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
            for obj in imported_objects:
                if belongs_to_vehicle(obj.name, clean_vehicle_name):
                    remove_from_all_collections(obj)
                    fbx_collection.objects.link(obj)
                    object_collections[obj.as_pointer()] = fbx_collection
 

            # Create subcollections 
            wheels_collection_name = f"Wheels: {vehicle_name}: {filename}: FBX"
            wheels_collection = ensure_collection_exists(wheels_collection_name, fbx_collection, hide = False, dont_render=False)       
       
            mesh_collection_name = f"Body Mesh: {vehicle_name}: {filename}: FBX"
            mesh_collection = ensure_collection_exists(mesh_collection_name, fbx_collection, hide = False, dont_render=False)       
        
            # Loop through imported objects
            for obj in imported_objects:
                existing_collection = object_collections.get(obj.as_pointer())
                if existing_collection and existing_collection != fbx_collection:
                    continue
                # Don't let a vehicle "claim" wheel-related helpers from other vehicles
                if not belongs_to_vehicle(obj.name, clean_vehicle_name):
                    continue
                if is_wheel_object(obj):
                    assign_objects_to_subcollection(wheels_collection_name, fbx_collection, obj)
                    object_collections[obj.as_pointer()] = wheels_collection
                    continue

                if not belongs_to_vehicle(obj.name, clean_vehicle_name):
                    continue

                if "Mesh" in obj.name:
                    assign_objects_to_subcollection(mesh_collection_name, fbx_collection, obj)

            target_name = clean_vehicle_name + ": FBX"  # Original name pattern
            new_name = f"CG: {vehicle_name} {filename}: FBX"  # New name pattern

            for obj in imported_objects:
                if obj.name == target_name:
                    obj.name = new_name
                    print(f"Renamed: {target_name} → {new_name}")

        # Ensure any remaining imported objects follow their parent's collection
        for obj in imported_objects:
            if obj.as_pointer() in object_collections:
                continue

            parent = obj.parent
            parent_collection = None
            while parent and parent_collection is None:
                parent_collection = object_collections.get(parent.as_pointer())
                parent = parent.parent

            target_collection = parent_collection or event_collection
            remove_from_all_collections(obj)
            target_collection.objects.link(obj)
                    
        # Join Mesh objects separately for each vehicle
        join_mesh_objects_per_vehicle(vehicle_names, imported_objects, imported_pointer_set)

        # Replace duplicate materials
        merge_duplicate_materials_per_vehicle(vehicle_names, candidate_objects=imported_objects)
 
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
