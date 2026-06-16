import bpy
import os
import re
import math
import threading
import ctypes
import struct
import time
from contextlib import contextmanager
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


class ImportTimingReport:
    """Collect and print coarse timings for the HVE FBX import pipeline."""

    def __init__(self):
        self._entries = []
        self._started_at = time.perf_counter()

    @contextmanager
    def phase(self, name):
        started_at = time.perf_counter()
        try:
            yield
        finally:
            self.finish_phase((name, started_at))

    def start_phase(self, name):
        return name, time.perf_counter()

    def finish_phase(self, phase):
        name, started_at = phase
        elapsed = time.perf_counter() - started_at
        self._entries.append((name, elapsed))
        print(f"⏱️ HVE FBX timing | {name}: {elapsed:.2f}s")

    def print_summary(self):
        total_elapsed = time.perf_counter() - self._started_at
        if not self._entries:
            print(f"⏱️ HVE FBX timing | total: {total_elapsed:.2f}s")
            return

        print("⏱️ HVE FBX timing summary:")
        for name, elapsed in sorted(self._entries, key=lambda entry: entry[1], reverse=True):
            percent = (elapsed / total_elapsed * 100.0) if total_elapsed else 0.0
            print(f"   {elapsed:7.2f}s ({percent:5.1f}%)  {name}")
        print(f"   {total_elapsed:7.2f}s          total")


class BlenderImportProgress:
    """Mirror long-running FBX import progress into Blender's main UI."""

    def __init__(self, context, operator=None, total_steps=1):
        self.context = context
        self.operator = operator
        self.total_steps = max(int(total_steps), 1)
        self.current_step = 0
        self._wm = getattr(context, "window_manager", None)
        self._started = False

    def begin(self, message):
        if self._wm and hasattr(self._wm, "progress_begin"):
            self._wm.progress_begin(0, self.total_steps)
            self._started = True
        self.update(message, advance=False)

    def update(self, message, advance=True):
        if advance:
            self.current_step = min(self.current_step + 1, self.total_steps)

        progress_message = f"HVE FBX Import ({self.current_step}/{self.total_steps}): {message}"
        print(progress_message)

        if self.operator:
            self.operator.report({'INFO'}, progress_message)

        if self._wm:
            if hasattr(self._wm, "progress_update"):
                self._wm.progress_update(self.current_step)
            if hasattr(self._wm, "status_text_set"):
                self._wm.status_text_set(progress_message)

    def finish(self, message):
        self.update(message, advance=False)
        if self._wm:
            if hasattr(self._wm, "progress_update"):
                self._wm.progress_update(self.total_steps)
            if hasattr(self._wm, "status_text_set"):
                self._wm.status_text_set(None)
            if self._started and hasattr(self._wm, "progress_end"):
                self._wm.progress_end()
        if self.operator:
            self.operator.report({'INFO'}, message)


def report_import_progress(progress, message, advance=True):
    if progress is not None:
        progress.update(message, advance=advance)


def show_system_console_for_import(operator=None):
    """Best-effort: make Blender's system console visible for long FBX imports."""
    if os.name != "nt":
        return

    console_toggle = getattr(getattr(bpy.ops, "wm", None), "console_toggle", None)
    if not console_toggle or not console_toggle.poll():
        return

    console_toggle()
    message = "Opened Blender system console for live HVE FBX import details."
    print(message)
    if operator:
        operator.report({'INFO'}, message)


def normalize_name(name: str) -> str:
    """Return a lowercase name with underscores replaced by spaces."""
    return name.lower().replace("_", " ")


def normalize_root_name(name: str) -> str:
    """Return the base vehicle identifier without numeric suffixes or colon paths."""
    name = re.sub(r"\.\d+$", "", name)
    return name.split(":")[0]


def is_valid_blender_object(obj):
    """Return ``False`` when a Blender object reference has been removed.

    Blender keeps Python wrappers for removed RNA objects alive, but accessing
    properties on those wrappers raises ``ReferenceError``. Import bookkeeping
    lists can contain those stale wrappers after helper objects are deleted, so
    callers should filter them before reading names, types, parents, or
    animation data.
    """
    try:
        # Accessing ``name`` is enough to validate the StructRNA wrapper.
        obj.name
    except ReferenceError:
        return False
    return True


def get_root_vehicle_names(imported_objects):
    """Collect unique top-level empty names representing vehicles."""
    vehicle_names = []
    for obj in imported_objects:
        if not is_valid_blender_object(obj):
            continue
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

def force_zero_preroll_pose(obj, frame=-1):
    """Force obj to be at origin with no rotation at a given frame by setting/overwriting keys."""
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return

    action = obj.animation_data.action
    fcurves = get_action_fcurve_collection(action)

    # If we can edit fcurves directly (preferred)
    if fcurves is not None:
        # Ensure 3 location + 3 rotation fcurves exist, then set key at 'frame' to 0.0
        for data_path, indices in (("location", (0, 1, 2)), ("rotation_euler", (0, 1, 2))):
            for idx in indices:
                fc = None
                for existing in fcurves:
                    if existing.data_path == data_path and existing.array_index == idx:
                        fc = existing
                        break
                if fc is None:
                    fc = fcurves.new(data_path=data_path, index=idx)

                # Remove any existing key at this frame (avoid duplicates)
                for kp in list(fc.keyframe_points):
                    if abs(kp.co.x - frame) < 1e-6:
                        fc.keyframe_points.remove(kp)

                kp = fc.keyframe_points.insert(frame, 0.0, options={'FAST'})
                kp.interpolation = 'LINEAR'
        return

    # Fallback when action is layered / no direct fcurves exposed:
    # Use keyframe_insert safely.
    scene = bpy.context.scene
    cur_frame = scene.frame_current

    loc0 = obj.location.copy()
    rot0 = obj.rotation_euler.copy()

    scene.frame_set(frame)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.keyframe_insert(data_path="location", frame=frame)
    obj.keyframe_insert(data_path="rotation_euler", frame=frame)

    scene.frame_set(cur_frame)
    obj.location = loc0
    obj.rotation_euler = rot0

def adjust_animation(obj, apply_x_rotation_offset=True):
    """Adjust imported animation orientation and strip scale animation."""
    animation_data = getattr(obj, "animation_data", None)
    action = getattr(animation_data, "action", None)
    if not action:
        return

    app_version = getattr(getattr(bpy, "app", None), "version", (5, 0, 0))
    action_fcurves = get_action_fcurve_collection(action)
    fcurves_to_edit = getattr(action, "fcurves", None) if (4, 5, 0) <= app_version < (5, 0, 0) else action_fcurves

    if apply_x_rotation_offset:
        for fcurve in iter_action_fcurves(action):
            if fcurve.data_path.endswith("rotation_euler") and fcurve.array_index == 0:
                for keyframe in fcurve.keyframe_points:
                    keyframe.co.y += math.radians(-180)
                    keyframe.handle_left.y += math.radians(-180)
                    keyframe.handle_right.y += math.radians(-180)

    if fcurves_to_edit is not None:
        scale_fcurves = [
            fcurve for fcurve in fcurves_to_edit if fcurve.data_path.endswith("scale")
        ]
        for fcurve in scale_fcurves:
            fcurves_to_edit.remove(fcurve)

    obj.scale.y *= -1
    obj.scale.z *= -1

    if (4, 5, 0) <= app_version < (5, 0, 0):
        obj.location = (0, 0, 0)
        obj.rotation_euler = (0, 0, 0)
        obj.keyframe_insert(data_path="location", frame=-1)
        obj.keyframe_insert(data_path="rotation_euler", frame=-1)
    else:
        ensure_preroll_keys(action, target_frame=-1)


def zero_main_vehicle_empty_transform_at_preroll(imported_objects, frame=-1):
    """Zero only top-level animated EMPTY objects at the pre-roll frame."""
    for obj in imported_objects:
        if not (
            getattr(obj, "type", None) == "EMPTY"
            and getattr(obj, "parent", None) is None
            and getattr(obj, "animation_data", None)
        ):
            continue

        obj.location = (0.0, 0.0, 0.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.keyframe_insert(data_path="location", frame=frame)
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)



def copy_animated_rotation(parent, axis_keywords=None, debug=False, candidate_objects=None):
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
    candidate_objects : iterable, optional
        Objects to search for rotation helpers. Defaults to selected objects for
        backward compatibility with manual use.

    Missing axes are skipped.
    """

    if not parent or not is_valid_blender_object(parent) or parent.type != 'EMPTY':
        print("❌ Error: Please select an empty object as the target parent.")
        return

    axis_keywords = axis_keywords or ROTATION_AXIS_KEYWORDS

    norm_parent = normalize_name(parent.name)
    if debug:
        print(f"🛠 Normalized parent name: '{norm_parent}'")

    raw_candidates = candidate_objects if candidate_objects is not None else bpy.context.selected_objects
    candidates = [obj for obj in raw_candidates if is_valid_blender_object(obj)]

    # Parent legacy helper groups when present. Some HVE FBX files name
    # rotation carriers simply as "... Camber"/"... Steering" rather than
    # "... Camber Objects". Do not bail out when no "Objects" helpers exist;
    # the broader source-selection pass below still needs to consume those
    # axis helpers so they do not remain as origin empties in the import.
    parent_helper_objects = [
        obj
        for obj in candidates
        if obj != parent
        and norm_parent in normalize_name(obj.name)
        and "objects" in obj.name.lower()
    ]

    # Set parent for filtered legacy helper groups
    for obj in parent_helper_objects:
        obj.parent = parent

    #print(f"✅ Parented {len(parent_helper_objects)} objects to '{parent.name}': {[obj.name for obj in parent_helper_objects]}")

    # Get helper candidates (excluding the parent) and only keep objects that contain the parent's name
    selected_objects = [
        obj
        for obj in candidates
        if obj != parent
        and norm_parent in normalize_name(obj.name)
    ]
    if not selected_objects:
        print(f"❌ No matching objects found to parent under '{parent.name}'.")
        return

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

    # 🚀 DELETE the source objects after copying animation and remove them from
    # the import bookkeeping list so later passes don't touch stale StructRNA
    # wrappers.
    for source in sources.values():
        if source:
            if isinstance(candidate_objects, list):
                try:
                    candidate_objects.remove(source)
                except ValueError:
                    pass
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



def _iter_collection_tree(collection):
    """Yield ``collection`` and all nested child collections depth-first."""
    if collection is None:
        return

    yield collection
    for child in list(getattr(collection, "children", [])):
        yield from _iter_collection_tree(child)


def strip_blender_numeric_suffix(name: str) -> str:
    """Remove Blender's trailing numeric suffix (e.g. ``.001``) from ``name``."""
    return re.sub(r"\.\d+$", "", name)


def get_existing_fbx_collections(filename):
    """Return FBX-specific collections for ``filename`` without touching the shared HVE root."""
    filename_token = f": {filename}:"
    return [
        collection
        for collection in bpy.data.collections
        if collection.name.endswith(": FBX") and filename_token in collection.name
    ]


def overwrite_existing_fbx_objects(filename, imported_objects):
    """Remove same-named objects from prior FBX imports and reuse their original names."""
    collections_to_check = get_existing_fbx_collections(filename)
    imported_name_map = {}
    for obj in imported_objects:
        imported_name_map.setdefault(strip_blender_numeric_suffix(obj.name), []).append(obj)

    removed_names = set()
    for collection in collections_to_check:
        for obj in list(getattr(collection, "objects", [])):
            base_name = strip_blender_numeric_suffix(obj.name)
            if base_name not in imported_name_map:
                continue
            bpy.data.objects.remove(obj, do_unlink=True)
            removed_names.add(base_name)

    for obj in imported_objects:
        desired_name = strip_blender_numeric_suffix(obj.name)
        if desired_name in removed_names and obj.name != desired_name and bpy.data.objects.get(desired_name) is None:
            obj.name = desired_name

    for collection in sorted(collections_to_check, key=lambda col: col.name.count(":"), reverse=True):
        if list(getattr(collection, "objects", [])) or list(getattr(collection, "children", [])):
            continue
        bpy.data.collections.remove(collection)

    if removed_names:
        print(f"♻️ Overwrote {len(removed_names)} existing FBX objects for '{filename}'.")
        return True

    return False


def bake_shape_keys_to_keyframes(obj):
    """Bake shape key F-curves to dense per-frame keyframes before a join operation.

    Uses direct F-curve point manipulation (foreach_set) instead of keyframe_insert
    so the cost is one bulk write per shape key rather than one RNA round-trip per frame.
    """
    if not obj.data.shape_keys or not obj.data.shape_keys.animation_data:
        return

    action = obj.data.shape_keys.animation_data.action
    action_fcurves = get_action_fcurve_collection(action)
    if action_fcurves is None:
        return

    frame_start = bpy.context.scene.frame_start
    frame_end = bpy.context.scene.frame_end
    frames = list(range(frame_start, frame_end + 1))
    frame_count = len(frames)

    for shape_key in obj.data.shape_keys.key_blocks:
        if shape_key.name == "Basis":
            continue

        data_path = f'key_blocks["{shape_key.name}"].value'
        fcurve = next(
            (fc for fc in action_fcurves if fc.data_path.endswith(data_path)),
            None,
        )
        if fcurve is None:
            continue

        # Evaluate all values in one pass — cheap, no depsgraph update needed.
        values = [fcurve.evaluate(f) for f in frames]

        # Replace all existing keyframe points with the dense baked set.
        kps = fcurve.keyframe_points
        try:
            kps.clear()
        except AttributeError:
            # Blender < 3.6 fallback: remove points from end to avoid index shifting.
            for _ in range(len(kps)):
                kps.remove(kps[-1], fast=True)

        kps.add(frame_count)
        # foreach_set writes all coordinates in one C-level call — much faster than a Python loop.
        coords = [coord for pair in zip(frames, values) for coord in (float(pair[0]), pair[1])]
        kps.foreach_set("co", coords)
        for kp in kps:
            kp.interpolation = 'LINEAR'
        fcurve.update()

    print(f"✅ Shape keys baked for {obj.name}")

def bake_shape_keys_threaded(obj_list):
    """Bake shape keys for each object sequentially (Blender's API is not thread-safe)."""
    for obj in obj_list:
        if obj.data.shape_keys:
            bake_shape_keys_to_keyframes(obj)


def sanitize_cache_name(name):
    """Return a filesystem-safe cache stem for ``name``."""
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return sanitized or "mesh_cache"


def write_mdd_file(filepath, frame_times, frame_vertex_positions):
    """Write mesh deformation samples to an MDD point-cache file."""
    if not frame_times or not frame_vertex_positions:
        raise ValueError("MDD export requires at least one sampled frame.")

    frame_count = len(frame_times)
    if frame_count != len(frame_vertex_positions):
        raise ValueError("Frame time count must match sampled frame count.")

    point_count = len(frame_vertex_positions[0])
    for sample in frame_vertex_positions:
        if len(sample) != point_count:
            raise ValueError("All sampled frames must have the same vertex count.")

    with open(filepath, "wb") as handle:
        handle.write(struct.pack(">2i", frame_count, point_count))
        handle.write(struct.pack(f">{frame_count}f", *frame_times))
        for sample in frame_vertex_positions:
            flattened = [coord for vertex in sample for coord in vertex]
            handle.write(struct.pack(f">{len(flattened)}f", *flattened))


@contextmanager
def temporarily_disable_modifiers(obj):
    """Temporarily disable object modifiers while sampling raw shape-key deformation."""
    modifier_states = []
    for modifier in getattr(obj, "modifiers", []):
        modifier_states.append((modifier, modifier.show_viewport, modifier.show_render))
        modifier.show_viewport = False
        modifier.show_render = False

    try:
        yield
    finally:
        for modifier, show_viewport, show_render in modifier_states:
            modifier.show_viewport = show_viewport
            modifier.show_render = show_render



def sample_mesh_deformation_frames(obj, frame_start, frame_end):
    """Sample evaluated vertex positions for ``obj`` across the frame range."""
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    original_frame = scene.frame_current
    fps_base = scene.render.fps_base or 1.0
    fps = scene.render.fps / fps_base if fps_base else scene.render.fps
    fps = fps or 24.0

    frame_times = []
    frame_vertex_positions = []
    expected_vertex_count = len(getattr(obj.data, "vertices", []))

    try:
        with temporarily_disable_modifiers(obj):
            for frame in range(frame_start, frame_end + 1):
                scene.frame_set(frame)
                depsgraph.update()
                eval_obj = obj.evaluated_get(depsgraph)
                mesh = eval_obj.to_mesh()
                try:
                    vertex_positions = [tuple(vertex.co) for vertex in mesh.vertices]
                finally:
                    eval_obj.to_mesh_clear()

                if len(vertex_positions) != expected_vertex_count:
                    raise ValueError(
                        f"Vertex count changed while sampling shape keys for {obj.name}."
                    )

                frame_times.append((frame - frame_start) / fps)
                frame_vertex_positions.append(vertex_positions)
    finally:
        scene.frame_set(original_frame)

    return frame_times, frame_vertex_positions


def read_shape_key_frames_directly(obj):
    """Read vertex positions and frame numbers straight from shape key data blocks.

    This is orders of magnitude faster than sample_mesh_deformation_frames because
    it never calls scene.frame_set(), depsgraph.update(), or to_mesh().  It reads
    the stored vertex co values directly from each shape key block.

    Returns (frame_numbers, frame_vertex_positions) where frame_numbers are derived
    from the peak frame of each shape key's F-curve, or sequential integers if no
    F-curve data is available.  Returns ([], []) when the object has no usable
    shape keys.
    """
    shape_keys = getattr(getattr(obj, "data", None), "shape_keys", None)
    if not shape_keys:
        return [], []

    key_blocks = shape_keys.key_blocks
    if len(key_blocks) < 2:
        return [], []

    # Build a map from shape key name to the frame where its F-curve peaks (value == 1).
    # Fall back to sequential frame numbers when animation data is absent.
    action = getattr(getattr(shape_keys, "animation_data", None), "action", None)
    peak_frame_map = {}
    if action is not None:
        for fcurve in iter_action_fcurves(action):
            dp = getattr(fcurve, "data_path", "")
            if not dp.endswith('.value'):
                continue
            # Extract key name from data path like key_blocks["Name"].value
            import re as _re
            m = _re.search(r'key_blocks\["([^"]+)"\]', dp)
            if not m:
                continue
            key_name = m.group(1)
            best_frame = None
            best_value = -1.0
            for kp in getattr(fcurve, "keyframe_points", []):
                if kp.co.y > best_value:
                    best_value = kp.co.y
                    best_frame = kp.co.x
            if best_frame is not None:
                peak_frame_map[key_name] = best_frame

    frame_numbers = []
    frame_vertex_positions = []
    sequential = 0

    for kb in key_blocks:
        if kb.name == "Basis":
            continue
        frame = peak_frame_map.get(kb.name, sequential)
        sequential += 1
        positions = [tuple(p.co) for p in kb.data]
        frame_numbers.append(frame)
        frame_vertex_positions.append(positions)

    if not frame_numbers:
        return [], []

    # Ensure frames are in ascending order.
    pairs = sorted(zip(frame_numbers, frame_vertex_positions), key=lambda p: p[0])
    frame_numbers = [p[0] for p in pairs]
    frame_vertex_positions = [p[1] for p in pairs]

    return frame_numbers, frame_vertex_positions


def clear_object_shape_keys(obj):
    """Remove all shape keys from ``obj`` if present."""
    if not getattr(getattr(obj, "data", None), "shape_keys", None):
        return

    clear_method = getattr(obj, "shape_key_clear", None)
    if callable(clear_method):
        clear_method()
        return

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shape_key_remove(all=True, apply_mix=False)


def max_vertex_deviation(sample_a, sample_b):
    """Return the maximum per-vertex Euclidean distance between two samples."""
    if len(sample_a) != len(sample_b):
        raise ValueError("Vertex samples must have matching lengths.")

    max_distance = 0.0
    for vertex_a, vertex_b in zip(sample_a, sample_b):
        dx = vertex_a[0] - vertex_b[0]
        dy = vertex_a[1] - vertex_b[1]
        dz = vertex_a[2] - vertex_b[2]
        max_distance = max(max_distance, math.sqrt(dx * dx + dy * dy + dz * dz))
    return max_distance


def interpolated_sample(sample_a, sample_b, factor):
    """Linearly interpolate between two sampled vertex states."""
    if len(sample_a) != len(sample_b):
        raise ValueError("Vertex samples must have matching lengths.")

    return [
        (
            vertex_a[0] + (vertex_b[0] - vertex_a[0]) * factor,
            vertex_a[1] + (vertex_b[1] - vertex_a[1]) * factor,
            vertex_a[2] + (vertex_b[2] - vertex_a[2]) * factor,
        )
        for vertex_a, vertex_b in zip(sample_a, sample_b)
    ]


def select_adaptive_sample_indices(frame_numbers, frame_vertex_positions, tolerance=0.01):
    """Select representative sample indices using recursive interpolation error."""
    if not frame_numbers or not frame_vertex_positions:
        return []
    if len(frame_numbers) != len(frame_vertex_positions):
        raise ValueError("Frame numbers must match sampled vertex positions.")

    kept = {0, len(frame_numbers) - 1}

    def subdivide(start_idx, end_idx):
        if end_idx - start_idx <= 1:
            return

        start_frame = frame_numbers[start_idx]
        end_frame = frame_numbers[end_idx]
        frame_span = end_frame - start_frame
        if frame_span <= 0:
            return

        worst_idx = None
        worst_error = -1.0
        start_sample = frame_vertex_positions[start_idx]
        end_sample = frame_vertex_positions[end_idx]

        for idx in range(start_idx + 1, end_idx):
            factor = (frame_numbers[idx] - start_frame) / frame_span
            estimated = interpolated_sample(start_sample, end_sample, factor)
            error = max_vertex_deviation(frame_vertex_positions[idx], estimated)
            if error > worst_error:
                worst_error = error
                worst_idx = idx

        if worst_idx is not None and worst_error > tolerance:
            kept.add(worst_idx)
            subdivide(start_idx, worst_idx)
            subdivide(worst_idx, end_idx)

    subdivide(0, len(frame_numbers) - 1)
    return sorted(kept)


def set_shape_key_geometry(shape_key, vertex_positions):
    """Copy sampled coordinates into ``shape_key`` data."""
    if len(shape_key.data) != len(vertex_positions):
        raise ValueError("Shape key vertex count does not match sampled positions.")

    for point, coords in zip(shape_key.data, vertex_positions):
        point.co = coords


def set_mesh_vertex_positions(mesh, vertex_positions):
    """Overwrite ``mesh`` vertices with sampled coordinates."""
    if len(mesh.vertices) != len(vertex_positions):
        raise ValueError("Mesh vertex count does not match sampled positions.")

    for vertex, coords in zip(mesh.vertices, vertex_positions):
        vertex.co = coords
    update = getattr(mesh, "update", None)
    if callable(update):
        update()


def keyframe_shape_key_sample(key_block, previous_frame, frame, next_frame):
    """Animate a reduced sample key so it crossfades between neighbors."""
    key_block.value = 0.0
    key_block.keyframe_insert(data_path="value", frame=previous_frame)
    key_block.value = 1.0
    key_block.keyframe_insert(data_path="value", frame=frame)
    if next_frame is not None:
        key_block.value = 0.0
        key_block.keyframe_insert(data_path="value", frame=next_frame)


def set_shape_key_fcurve_interpolation(shape_keys, key_name, interpolation="LINEAR"):
    """Set interpolation mode for all F-Curves driving ``key_name``."""
    animation_data = getattr(shape_keys, "animation_data", None)
    action = getattr(animation_data, "action", None)
    if action is None:
        return

    action_fcurves = get_action_fcurve_collection(action)
    if action_fcurves is None:
        return

    data_path = f'key_blocks["{key_name}"].value'
    for fcurve in action_fcurves:
        if getattr(fcurve, "data_path", None) != data_path:
            continue
        for keyframe in getattr(fcurve, "keyframe_points", []):
            keyframe.interpolation = interpolation


def trim_sample_indices(frame_numbers, frame_vertex_positions, selected_indices, max_samples):
    """Trim adaptive samples while preserving endpoints."""
    selected_indices = list(selected_indices)
    while len(selected_indices) > max_samples and len(selected_indices) > 2:
        removable = []
        for pos in range(1, len(selected_indices) - 1):
            current_idx = selected_indices[pos]
            prev_idx = selected_indices[pos - 1]
            next_idx = selected_indices[pos + 1]
            frame_span = frame_numbers[next_idx] - frame_numbers[prev_idx]
            if frame_span <= 0:
                removable.append((float("inf"), current_idx))
                continue

            factor = (frame_numbers[current_idx] - frame_numbers[prev_idx]) / frame_span
            estimated = interpolated_sample(
                frame_vertex_positions[prev_idx],
                frame_vertex_positions[next_idx],
                factor,
            )
            error = max_vertex_deviation(frame_vertex_positions[current_idx], estimated)
            removable.append((error, current_idx))

        _, idx_to_remove = min(removable, key=lambda item: item[0])
        selected_indices.remove(idx_to_remove)

    return selected_indices


def rebuild_shape_keys_from_samples(obj, sample_frames, sample_vertex_positions):
    """Replace imported shape keys with a reduced, self-contained sampled set."""
    if not sample_frames or not sample_vertex_positions:
        return []
    if len(sample_frames) != len(sample_vertex_positions):
        raise ValueError("Sample frame count must match sampled vertex positions.")

    # Capture the existing Basis geometry before clearing, so the resting pose is preserved.
    existing_basis = obj.data.shape_keys
    if existing_basis and existing_basis.key_blocks:
        basis_positions = [tuple(kb.co) for kb in existing_basis.key_blocks[0].data]
    else:
        basis_positions = [tuple(v.co) for v in obj.data.vertices]

    clear_object_shape_keys(obj)
    set_mesh_vertex_positions(obj.data, basis_positions)
    obj.shape_key_add(name="Basis", from_mix=False)

    reduced_keys = []
    for idx, frame in enumerate(sample_frames[1:], start=1):
        key_name = f"Baked_{frame:04d}"
        key_block = obj.shape_key_add(name=key_name, from_mix=False)
        set_shape_key_geometry(key_block, sample_vertex_positions[idx])
        previous_frame = sample_frames[idx - 1]
        next_frame = sample_frames[idx + 1] if idx + 1 < len(sample_frames) else None
        keyframe_shape_key_sample(key_block, previous_frame, frame, next_frame)
        set_shape_key_fcurve_interpolation(obj.data.shape_keys, key_name)
        reduced_keys.append(key_name)

    return reduced_keys


def reduce_shape_key_meshes_with_adaptive_samples(
    vehicle_names,
    tolerance=0.01,
    max_samples=24,
    imported_objects=None,
    imported_pointer_set=None,
):
    # None means no hard cap — tolerance alone controls how many samples are kept.
    """Rebuild joined meshes with a smaller self-contained shapekey set."""
    scene = bpy.context.scene
    reduced_objects = []
    seen_pointers = set()
    imported_pointer_set = imported_pointer_set or set()

    for vehicle_name in vehicle_names:
        collection_prefix = f"Body Mesh: {vehicle_name}:"
        body_mesh_collections = [
            col for col in bpy.data.collections if col.name.startswith(collection_prefix)
        ]

        mesh_objects = []
        for col in body_mesh_collections:
            mesh_objects.extend(_gather_meshes(col))

        # Restrict to objects from this import when a pointer set is provided.
        if imported_pointer_set:
            mesh_objects = [
                obj for obj in mesh_objects
                if (obj.as_pointer() if hasattr(obj, "as_pointer") else id(obj)) in imported_pointer_set
            ]

        if not mesh_objects:
            clean_vehicle_name = re.sub(r"\.\d+$", "", vehicle_name)
            source_objects = imported_objects if imported_objects is not None else bpy.context.scene.objects
            mesh_objects = [
                obj
                for obj in source_objects
                if obj.type == "MESH" and belongs_to_vehicle(obj.name, clean_vehicle_name)
                and (not imported_pointer_set or (obj.as_pointer() if hasattr(obj, "as_pointer") else id(obj)) in imported_pointer_set)
            ]

        for obj in mesh_objects:
            pointer = obj.as_pointer() if hasattr(obj, "as_pointer") else id(obj)
            if pointer in seen_pointers:
                continue
            seen_pointers.add(pointer)

            if not getattr(getattr(obj, "data", None), "shape_keys", None):
                continue

            # Read vertex positions directly from shape key data — no frame-setting needed.
            frame_numbers, frame_vertex_positions = read_shape_key_frames_directly(obj)
            if not frame_numbers:
                continue

            selected_indices = select_adaptive_sample_indices(
                frame_numbers,
                frame_vertex_positions,
                tolerance=tolerance,
            )
            if max_samples is not None:
                selected_indices = trim_sample_indices(
                    frame_numbers,
                    frame_vertex_positions,
                    selected_indices,
                    max_samples,
                )

            selected_frames = [frame_numbers[idx] for idx in selected_indices]
            selected_positions = [frame_vertex_positions[idx] for idx in selected_indices]
            reduced_keys = rebuild_shape_keys_from_samples(
                obj,
                selected_frames,
                selected_positions,
            )
            reduced_objects.append((obj.name, selected_frames, reduced_keys))

    if reduced_objects:
        print(
            f"✅ Reduced shapekeys on {len(reduced_objects)} mesh object(s) via adaptive sampling."
        )
    else:
        print("ℹ️ No shape-keyed meshes found to reduce.")

    return reduced_objects


def _gather_meshes(collection):
    """Recursively collect mesh objects from ``collection`` and its children."""
    meshes = [obj for obj in collection.objects if obj.type == "MESH"]
    for child in collection.children:
        meshes.extend(_gather_meshes(child))
    return meshes


def object_pointer(obj):
    """Return a stable pointer value for Blender objects and test doubles."""
    return obj.as_pointer() if hasattr(obj, "as_pointer") else id(obj)


def get_body_mesh_objects_for_vehicle(vehicle_name, imported_objects=None, imported_pointer_set=None):
    """Collect imported non-wheel body mesh objects for ``vehicle_name``."""
    clean_vehicle_name = re.sub(r"\.\d+$", "", vehicle_name)

    if imported_objects is None:
        imported_objects = list(getattr(getattr(bpy.context, "scene", None), "objects", []))

    if imported_pointer_set is None:
        imported_pointer_set = {object_pointer(obj) for obj in imported_objects}
    else:
        imported_pointer_set = set(imported_pointer_set)

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

    # Preserve order but remove duplicates that can appear through nested collections.
    unique_mesh_objects = []
    seen = set()
    for obj in mesh_objects:
        pointer = object_pointer(obj)
        if pointer in seen:
            continue
        seen.add(pointer)
        unique_mesh_objects.append(obj)

    return unique_mesh_objects


def has_shape_key_animation(obj):
    """Return whether ``obj`` contains shape keys that may need storage conversion."""
    shape_keys = getattr(getattr(obj, "data", None), "shape_keys", None)
    if not shape_keys:
        return False
    key_blocks = getattr(shape_keys, "key_blocks", [])
    return any(getattr(key_block, "name", "") != "Basis" for key_block in key_blocks)


def create_mesh_cache_directory(source_fbx_path):
    """Create and return the directory used for exported point-cache files."""
    fbx_dir = os.path.dirname(source_fbx_path) or os.getcwd()
    fbx_name = os.path.splitext(os.path.basename(source_fbx_path))[0] or "fbx_import"
    cache_dir = os.path.join(fbx_dir, f"{sanitize_cache_name(fbx_name)}_mesh_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def attach_mdd_mesh_cache_modifier(obj, mdd_filepath, frame_start):
    """Attach an MDD Mesh Cache modifier to ``obj`` for the exported cache file."""
    modifier = obj.modifiers.new(name="HVE MDD Mesh Cache", type="MESH_CACHE")

    if hasattr(modifier, "cache_format"):
        modifier.cache_format = "MDD"

    path_value = mdd_filepath
    relpath = getattr(getattr(bpy, "path", None), "relpath", None)
    if callable(relpath):
        path_value = relpath(mdd_filepath)

    if hasattr(modifier, "filepath"):
        modifier.filepath = path_value
    if hasattr(modifier, "frame_start"):
        modifier.frame_start = frame_start
    if hasattr(modifier, "frame_scale"):
        modifier.frame_scale = 1.0
    if hasattr(modifier, "eval_factor"):
        modifier.eval_factor = 1.0

    return modifier


def export_shape_key_animation_to_mdd(obj, cache_dir, frame_start, frame_end):
    """Bake ``obj`` shape-key deformation to an external MDD file and attach it."""
    if not has_shape_key_animation(obj):
        return None

    frame_times, frame_vertex_positions = sample_mesh_deformation_frames(
        obj,
        frame_start,
        frame_end,
    )
    cache_name = f"{sanitize_cache_name(obj.name)}.mdd"
    cache_path = os.path.join(cache_dir, cache_name)
    write_mdd_file(cache_path, frame_times, frame_vertex_positions)
    clear_object_shape_keys(obj)
    attach_mdd_mesh_cache_modifier(obj, cache_path, frame_start)
    print(f"✅ Exported MDD mesh cache for {obj.name}: {cache_path}")
    return cache_path


def export_body_shape_key_animations_to_mdd(
    vehicle_names,
    source_fbx_path,
    imported_objects=None,
    imported_pointer_set=None,
):
    """Convert body mesh shape-key animation to external MDD files."""
    scene = bpy.context.scene
    cache_dir = create_mesh_cache_directory(source_fbx_path)
    exported = []

    for vehicle_name in vehicle_names:
        for obj in get_body_mesh_objects_for_vehicle(
            vehicle_name,
            imported_objects,
            imported_pointer_set,
        ):
            cache_path = export_shape_key_animation_to_mdd(
                obj,
                cache_dir,
                scene.frame_start,
                scene.frame_end,
            )
            if cache_path:
                exported.append((obj.name, cache_path))

    if exported:
        print(f"✅ Exported {len(exported)} body mesh MDD cache file(s).")
    else:
        print("ℹ️ No body mesh shape-key animation found for MDD export.")

    return exported


def join_mesh_objects_per_vehicle(vehicle_names, imported_objects=None, imported_pointer_set=None):
    """Joins all imported MESH objects per vehicle separately, after baking shape keys."""

    for vehicle_name in vehicle_names:
        clean_vehicle_name = re.sub(r'\.\d+$', '', vehicle_name)
        mesh_objects = get_body_mesh_objects_for_vehicle(
            vehicle_name,
            imported_objects,
            imported_pointer_set,
        )

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

    def node_tree_signature(mat):
        node_tree = getattr(mat, "node_tree", None)
        if not node_tree:
            return None

        signature = []
        for node in node_tree.nodes:
            if getattr(node, "type", None) == 'BSDF_PRINCIPLED':
                input_signature = []
                for input_name, socket in sorted(getattr(node, "inputs", {}).items()):
                    links = getattr(socket, "links", []) or []
                    if links:
                        link_signature = []
                        for link in links:
                            from_node = getattr(link, "from_node", None)
                            image = getattr(from_node, "image", None)
                            link_signature.append((
                                getattr(from_node, "type", None),
                                getattr(image, "filepath", None) if image else None,
                                getattr(from_node, "interpolation", None),
                                getattr(from_node, "projection", None),
                                getattr(from_node, "extension", None),
                                getattr(getattr(link, "from_socket", None), "name", None),
                            ))
                        input_signature.append((input_name, tuple(link_signature)))
                    else:
                        value = getattr(socket, "default_value", None)
                        if isinstance(value, (list, tuple)):
                            value = tuple(value)
                        input_signature.append((input_name, value))
                signature.append((getattr(node, "type", None), tuple(input_signature)))
            elif getattr(node, "type", None) == 'TEX_IMAGE':
                image = getattr(node, "image", None)
                signature.append((
                    getattr(node, "type", None),
                    getattr(image, "filepath", None) if image else None,
                    getattr(node, "interpolation", None),
                    getattr(node, "projection", None),
                    getattr(node, "extension", None),
                ))

        return tuple(signature)

    if node_tree_signature(mat1) != node_tree_signature(mat2):
        return False

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
    clean_vehicle_name = re.sub(r'\.\d+$', '', vehicle_name)
    materials = []
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and belongs_to_vehicle(obj.name, clean_vehicle_name):
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
    clean_vehicle_name = re.sub(r'\.\d+$', '', vehicle_name)
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and belongs_to_vehicle(obj.name, clean_vehicle_name):
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
        clean_vehicle_name = re.sub(r'\.\d+$', '', vehicle_name)
        print(f"🔍 Processing materials for {clean_vehicle_name}...")
        material_map = find_duplicate_materials_for_vehicle(clean_vehicle_name)
        if material_map:
            replace_materials_for_vehicle(clean_vehicle_name, material_map)

            for obj in bpy.data.objects:
                if obj.type == 'MESH' and belongs_to_vehicle(obj.name, clean_vehicle_name):
                    collapse_material_slots(obj)

            remove_unused_materials()
            print(f"✅ Merged {len(material_map)} duplicate 'meshMaterial' materials for {clean_vehicle_name}.")
        else:
            print(f"✅ No duplicate 'meshMaterial' materials found for {clean_vehicle_name}.")

def collapse_material_slots(obj):
    """Merge identical material slots and remove unused ones on a mesh."""
    if obj.type != 'MESH':
        return

    mesh = getattr(obj, "data", None)
    slots = obj.material_slots

    if not slots:
        return

    if mesh is None or not hasattr(mesh, "polygons"):
        seen_material_names = set()
        for i in reversed(range(len(slots))):
            mat = slots[i].material
            mat_name = getattr(mat, "name", None)
            if mat is None or mat_name in seen_material_names:
                if mat is not None and hasattr(mat, "users"):
                    mat.users -= 1
                del slots[i]
            else:
                seen_material_names.add(mat_name)
        return

    # Build map: material -> first slot index
    mat_to_index = {}
    remap = {}

    for i, slot in enumerate(slots):
        mat = slot.material
        if mat is None:
            continue

        if mat.name not in mat_to_index:
            mat_to_index[mat.name] = i
        remap[i] = mat_to_index[mat.name]

    # Remap polygon material indices
    for poly in mesh.polygons:
        if poly.material_index in remap:
            poly.material_index = remap[poly.material_index]

    # Remove unused slots
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='OBJECT')

    # Must remove from highest index downward
    for i in reversed(range(len(slots))):
        mat = slots[i].material
        if mat is None:
            obj.active_material_index = i
            bpy.ops.object.material_slot_remove()
            continue

        # Check if any poly uses this slot
        if not any(p.material_index == i for p in mesh.polygons):
            obj.active_material_index = i
            bpy.ops.object.material_slot_remove()

def add_x_rotation_offset_from_frame(obj, start_frame=0, degrees=180.0):
    """Add degrees to X rotation keyframes at/after start_frame, leaving earlier keys (e.g. -1) untouched."""
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return

    action = obj.animation_data.action
    delta = math.radians(degrees)

    for fcurve in iter_action_fcurves(action):
        if fcurve.data_path.endswith("rotation_euler") and fcurve.array_index == 0:
            for kp in fcurve.keyframe_points:
                if kp.co.x >= start_frame - 1e-6:
                    kp.co.y += delta
                    kp.handle_left.y += delta
                    kp.handle_right.y += delta


def set_new_materials_metallic_zero(new_materials):
    """Set Principled BSDF metallic to zero for a sequence of imported materials."""
    for mat in new_materials:
        node_tree = getattr(mat, "node_tree", None)
        if not node_tree:
            continue

        for node in node_tree.nodes:
            if getattr(node, "type", None) != 'BSDF_PRINCIPLED':
                continue
            metallic_input = node.inputs.get('Metallic')
            if metallic_input is not None:
                metallic_input.default_value = 0.0



def import_fbx(
    context,
    fbx_file_path,
):
    timing_report = ImportTimingReport()
    progress = BlenderImportProgress(context, total_steps=14)
    progress.begin("Starting HVE FBX import")
    original_fps = context.scene.render.fps
    original_fps_base = context.scene.render.fps_base

    """Do something with the selected file(s)."""
    filename = bpy.path.basename(fbx_file_path).split('.')[0]

    # Ensure the file exists
    if os.path.exists(fbx_file_path):
        # Capture existing scene objects before import so we can diff afterwards
        report_import_progress(progress, "Preparing scene snapshot")
        with timing_report.phase("snapshot scene before native FBX import"):
            pre_import_ids = {obj.as_pointer() for obj in bpy.context.scene.objects}
            pre_import_material_ids = {mat.as_pointer() for mat in bpy.data.materials}

        report_import_progress(progress, "Running Blender FBX importer")
        with timing_report.phase("native Blender FBX import"):
            bpy.ops.import_scene.fbx(filepath=fbx_file_path)  # Import FBX
        print("FBX imported successfully!")

        report_import_progress(progress, "Detecting imported objects and materials")
        with timing_report.phase("post-import object/material detection"):
            # Set metallic to zero for any materials created by this import.
            new_materials = [
                mat for mat in bpy.data.materials
                if mat.as_pointer() not in pre_import_material_ids
            ]
            set_new_materials_metallic_zero(new_materials)

            # Determine which objects were added by the import
            post_import_objects = list(bpy.context.scene.objects)
            imported_objects = [obj for obj in post_import_objects if obj.as_pointer() not in pre_import_ids]

        with timing_report.phase("post-import tracking"):
            imported_objects = [obj for obj in imported_objects if is_valid_blender_object(obj)]
            imported_pointer_set = {obj.as_pointer() for obj in imported_objects}
            imported_names = [obj.name for obj in imported_objects]

        report_import_progress(progress, "Scanning animation and updating timeline")
        with timing_report.phase("scan animation and update timeline"):
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
                            max_frame = max(max_frame, int(keyframe.co.x))

                    if not fcurve_found:
                        frame_end = int(action.frame_range[1])
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

        report_import_progress(progress, "Renaming imported HVE objects")
        with timing_report.phase("rename imported HVE objects"):
            # Loop through selected objects and apply replacements
            for obj in imported_objects:
                for old_part, new_part in name_replacements.items():
                    if old_part in obj.name:  # Check if the old_part exists in the name
                        obj.name = obj.name.replace(old_part, new_part)  # Replace the text

        with timing_report.phase("offset imported animation keyframes"):
            processed_offset_actions = set()
            # Loop through imported objects and offset each shared action only once.
            for obj in imported_objects:
                action = getattr(getattr(obj, "animation_data", None), "action", None)
                if action is None:
                    continue
                action_key = action.as_pointer() if hasattr(action, "as_pointer") else id(action)
                if action_key in processed_offset_actions:
                    continue
                processed_offset_actions.add(action_key)
                offset_selected_animation(obj, frame_offset=None, target_start_frame=0)

        report_import_progress(progress, "Adjusting imported animation orientation")
        with timing_report.phase("adjust imported animation orientation"):
            # List of keywords to exclude from selection
            exclude_keywords = ["Wheel:", "shapenode"]  # Modify as needed

            # Loop through imported objects
            for obj in imported_objects:
                # Check if none of the exclude keywords are in the object name
                if not any(keyword in obj.name for keyword in exclude_keywords):
                    obj.select_set(True)  # Select the object

                    # Run function to adjust X rotation and scale for selected objects
                    adjust_animation(obj)


        report_import_progress(progress, "Copying wheel helper rotation animation")
        with timing_report.phase("copy wheel helper rotation animation"):
            # Derive keywords used for rotation helpers so they aren't processed as wheels
            exclude_keywords = [
                kw.lower() for kws in ROTATION_AXIS_KEYWORDS.values() for kw in kws
            ]
            exclude_keywords += ["objects", "geometry"]
            include_keywords = ["wheel"]

            # Loop through a snapshot because copy_animated_rotation removes
            # consumed helper sources from imported_objects.
            for obj in list(imported_objects):
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
                    # Run the function against the imported objects directly instead of
                    # repeatedly scanning Blender's selection state.
                    copy_animated_rotation(obj, debug=False, candidate_objects=imported_objects)

                    # Rename the object by adding "_FBX" to the end of its name
                    if not name.endswith(": FBX"):
                        obj.name = f"{name}: FBX"

        report_import_progress(progress, "Detecting vehicles and setting preroll pose")
        with timing_report.phase("detect vehicles and force preroll pose"):
            # Determine root vehicle names after any renaming or cleanup
            vehicle_names = get_root_vehicle_names(imported_objects)

            # Force vehicle root empties to be zeroed at frame -1
            for obj in imported_objects:
                if obj.type == "EMPTY" and obj.parent is None:
                    # Only apply to the top-level vehicle empties we detected
                    root = normalize_root_name(obj.name)
                    if root in [re.sub(r'\.\d+$', '', vn) for vn in vehicle_names]:
                        force_zero_preroll_pose(obj, frame=-1)

        report_import_progress(progress, "Replacing previous matching FBX imports")
        with timing_report.phase("overwrite previous matching FBX import"):
            overwrite_existing_fbx_objects(filename, imported_objects)

        report_import_progress(progress, "Organizing imported objects into HVE collections")
        collection_phase = timing_report.start_phase("organize imported objects into HVE collections")

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


            new_name = f"CG: {vehicle_name} {filename}: FBX"
            for o in imported_objects:
                if o.type == "EMPTY" and o.parent is None:
                    print("TOP EMPTY:", o.name, "root:", normalize_root_name(o.name))
            # Rename the top-level empty for this vehicle (robust across Blender versions)
            renamed = False
            for obj in imported_objects:
                if obj.type == "EMPTY" and obj.parent is None:
                    if normalize_root_name(obj.name) == clean_vehicle_name:
                        old = obj.name
                        obj.name = new_name
                        print(f"Renamed root empty: {old} → {new_name}")
                        renamed = True

                        break

            if not renamed:

                print(f"WARNING: Could not find root empty for vehicle '{vehicle_name}' to rename to '{new_name}'")

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

        timing_report.finish_phase(collection_phase)

        # Ensure frame_start is 0 before any shape-key baking or sampling.
        context.scene.frame_start = 0

        with timing_report.phase("merge duplicate imported materials"):
            # Replace duplicate materials
            merge_duplicate_materials_per_vehicle(vehicle_names)

        report_import_progress(progress, "Restoring scene settings")
        with timing_report.phase("restore scene settings"):
            # Restore the original frame rate settings
            context.scene.render.fps = original_fps
            context.scene.render.fps_base = original_fps_base
            print(f"🔄 Frame rate restored to {original_fps}/{original_fps_base}")

        timing_report.print_summary()
        progress.finish("HVE FBX import finished")


    else:
        error_message = f"Error: File not found: {fbx_file_path}"
        print(error_message)
        if operator:
            operator.report({'ERROR'}, error_message)
        timing_report.print_summary()
        progress.finish("HVE FBX import failed: file not found")



def add_merge_by_distance_modifier(obj):
    """Add a Weld (merge by distance) modifier to a mesh object if not already present."""
    for mod in obj.modifiers:
        if mod.type == 'WELD':
            return
    mod = obj.modifiers.new(name="Merge by Distance", type='WELD')
    mod.merge_threshold = 0.0001


def add_smooth_by_angle_modifier(obj):
    """Add an Edge Split (smooth by angle) modifier to a mesh object if not already present."""
    for mod in obj.modifiers:
        if mod.type == 'EDGE_SPLIT':
            return
    mod = obj.modifiers.new(name="Smooth by Angle", type='EDGE_SPLIT')
    mod.split_angle = 0.523599  # 30 degrees in radians
    mod.use_edge_angle = True
    mod.use_edge_sharp = True


def fix_boundary_normals_for_vehicles(vehicle_names, imported_objects=None, imported_pointer_set=None):
    """Smooth normals across body mesh part boundaries without joining.

    For each vehicle, builds a hidden joined reference mesh by combining the
    base geometry of all body mesh parts using bmesh (no operator, no selection
    required), then adds a Data Transfer modifier to each original part that
    copies face-corner normals from that reference.  Shading is continuous
    across part seams while shape keys, animation, and object separation are
    all preserved.
    """
    import bmesh as _bmesh

    scene = bpy.context.scene
    all_objects = imported_objects if imported_objects is not None else list(scene.objects)
    pointer_set = imported_pointer_set if imported_pointer_set is not None else {
        obj.as_pointer() for obj in scene.objects
    }

    # Find or create a hidden collection for reference meshes.
    ref_collection_name = "_HVE Normals References"
    ref_collection = bpy.data.collections.get(ref_collection_name)
    if ref_collection is None:
        ref_collection = bpy.data.collections.new(ref_collection_name)
        scene.collection.children.link(ref_collection)
        ref_collection.hide_viewport = True
        ref_collection.hide_render = True

    for vehicle_name in vehicle_names:
        mesh_objects = get_body_mesh_objects_for_vehicle(vehicle_name, all_objects, pointer_set)
        if not mesh_objects:
            print(f"⚠️ No body mesh objects found for {vehicle_name}, skipping normals fix.")
            continue

        # Remove any existing reference mesh for this vehicle so re-running is safe.
        ref_name = f"_NormRef: {vehicle_name}"
        existing = bpy.data.objects.get(ref_name)
        if existing:
            bpy.data.meshes.remove(existing.data, do_unlink=True)

        # Build the combined reference mesh with bmesh — no operator, no selection needed.
        combined_bm = _bmesh.new()
        for obj in mesh_objects:
            part_bm = _bmesh.new()
            # Use the Basis shape key geometry (index 0) which is the rest pose.
            part_bm.from_mesh(obj.data)
            # Transform vertices into world space so parts line up correctly.
            mat = obj.matrix_world
            for v in part_bm.verts:
                v.co = mat @ v.co
            # Append into the combined mesh.
            src_mesh = bpy.data.meshes.new("_tmp")
            part_bm.to_mesh(src_mesh)
            part_bm.free()
            combined_bm.from_mesh(src_mesh)
            bpy.data.meshes.remove(src_mesh)

        ref_mesh = bpy.data.meshes.new(ref_name)
        combined_bm.to_mesh(ref_mesh)
        combined_bm.free()

        # Shade smooth on every face of the reference.
        for poly in ref_mesh.polygons:
            poly.use_smooth = True
        ref_mesh.update()

        reference = bpy.data.objects.new(ref_name, ref_mesh)
        ref_collection.objects.link(reference)

        # Add Data Transfer modifier to each original part.
        for obj in mesh_objects:
            # Shade smooth the part itself.
            for poly in obj.data.polygons:
                poly.use_smooth = True
            obj.data.update()

            # Skip if already has a normals transfer modifier targeting this reference.
            if any(m.type == 'DATA_TRANSFER' and m.object == reference for m in obj.modifiers):
                continue

            mod = obj.modifiers.new(name="HVE Boundary Normals", type='DATA_TRANSFER')
            mod.object = reference
            mod.use_loop_data = True
            mod.data_types_loops = {'CUSTOM_NORMAL'}
            mod.loop_mapping = 'POLYINTERP_NEAREST'

        print(f"✅ Boundary normals fixed for {vehicle_name} ({len(mesh_objects)} parts → '{ref_name}').")



def load(context, filepath):

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')

    dirname = os.path.dirname(filepath)

    import_fbx(context, filepath)

    return {'FINISHED'}
