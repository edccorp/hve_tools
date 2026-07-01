import bpy
import csv
import os
import math
import mathutils  # Blender's math utilities library
from bpy.props import (
        BoolProperty,
        EnumProperty,
        FloatProperty,
        StringProperty,
        )

# Reuse the bpy-free CSV helpers from the EDR importer so header detection and
# normalisation behave the same across every column-mapping importer.
from .edr_importer import normalize_header, detect_header_row, read_csv_headers

bl_info = {
    "name": "Import XYZ Points",
    "author": "EDC",
    "version": (1, 0, 3),
    "blender": (2, 93, 0),
    "location": "View3D > Sidebar > Import XYZ Points",
    "description": "Imports XYZ points from a CSV file, creates circles, text, and optionally connects points.",
    "category": "Import-Export",
}


# Function to read points from a CSV file
def read_points(filepath):
    points = []
    try:
        with open(filepath, 'r', newline='', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            header_skipped = False
            for row in csv_reader:
                if not header_skipped:
                    header_skipped = True
                    continue  # Skip the header line
                try:
                    point_number = int(row[0])
                    x, y, z = map(float, row[1:4])
                    description = row[4] if len(row) > 4 else "No Description"
                    points.append((point_number, (x, y, z), description))
                except (ValueError, IndexError):
                    print(f"Skipping invalid row: {row}")
    except Exception as e:
        print(f"Error reading file: {e}")
    return points


# ---------------------------------------------------------------------------
# Flexible CSV column mapping
#
# Lets a points CSV (with or without a header row) provide Point Number, X, Y,
# Z and Description columns in any order. Columns are auto-matched by header
# name when possible, and the user can override the mapping in the panel. The
# helpers below are plain-Python and unit tested.
# ---------------------------------------------------------------------------

POINT_COLUMN_FIELDS = ("point_number", "x", "y", "z", "description")

POINT_COLUMN_KEYWORDS = {
    "point_number": ["point number", "point", "number", "num", "index", "id", "pt"],
    "x": ["x position", "position x", "pos x", "easting", "x"],
    "y": ["y position", "position y", "pos y", "northing", "y"],
    "z": ["z position", "position z", "pos z", "elevation", "height", "z"],
    "description": ["description", "desc", "label", "name", "comment", "note"],
}


def auto_map_point_columns(headers):
    """Best-effort map of point fields to column indices using header names.

    Returns a dict ``{field: index}`` where ``index`` is -1 when no column
    matched. Point Number is resolved before the single-letter x/y/z fields so a
    "Point" column is not claimed by a generic keyword.
    """
    normalized = [normalize_header(h) for h in headers]
    mapping = {field: -1 for field in POINT_COLUMN_FIELDS}
    used = set()

    def find(keywords):
        for kw in keywords:
            for i, header in enumerate(normalized):
                if i in used or not header:
                    continue
                tokens = header.split()
                # Short keywords must match a whole token (avoids "x" hitting
                # "max"); longer ones may match as a substring.
                if kw in tokens or (len(kw) > 2 and kw in header):
                    return i
        return -1

    for field in ("point_number", "description", "x", "y", "z"):
        idx = find(POINT_COLUMN_KEYWORDS[field])
        mapping[field] = idx
        if idx >= 0:
            used.add(idx)
    return mapping


def default_point_positional_mapping(num_columns):
    """Fallback mapping for header-less CSVs: PointNumber, X, Y, Z, Description."""
    order = ("point_number", "x", "y", "z", "description")
    mapping = {field: -1 for field in POINT_COLUMN_FIELDS}
    for i, field in enumerate(order):
        if num_columns > i:
            mapping[field] = i
    return mapping


def read_points_mapped(filepath, mapping, has_header):
    """Read points from ``filepath`` using a column ``mapping``.

    ``mapping`` maps each point field to a 0-based column index (or -1 to skip).
    X, Y and Z are required; Point Number falls back to a running counter and
    Description to "No Description" when their column is absent. Returns
    ``(points, error_message)``; ``error_message`` is None on success.
    """
    x_idx = mapping.get("x", -1)
    y_idx = mapping.get("y", -1)
    z_idx = mapping.get("z", -1)
    if min(x_idx, y_idx, z_idx) < 0:
        return None, "Assign X, Y and Z columns before importing."

    num_idx = mapping.get("point_number", -1)
    desc_idx = mapping.get("description", -1)
    max_core = max(x_idx, y_idx, z_idx)

    with open(filepath, 'r', newline='', encoding='utf-8') as file:
        rows = list(csv.reader(file))
    if has_header and rows:
        rows = rows[1:]

    points = []
    auto_number = 0
    for row in rows:
        if len(row) <= max_core:
            continue
        try:
            x = float(row[x_idx])
            y = float(row[y_idx])
            z = float(row[z_idx])
        except (ValueError, IndexError):
            continue

        auto_number += 1
        point_number = auto_number
        if 0 <= num_idx < len(row):
            try:
                point_number = int(float(row[num_idx]))
            except (ValueError, TypeError):
                point_number = auto_number

        description = "No Description"
        if 0 <= desc_idx < len(row) and row[desc_idx].strip():
            description = row[desc_idx].strip()

        points.append((point_number, (x, y, z), description))

    if not points:
        return None, "No valid numerical rows found with the selected columns."
    return points, None


# Function to create a circle at a given location
def create_circle(location, radius=0.5, vertices=32, collection=None):
    bpy.ops.mesh.primitive_circle_add(
        radius=radius,
        vertices=vertices,
        location=location
    )
    obj = bpy.context.object
    if collection:
        collection.objects.link(obj)
        bpy.context.collection.objects.unlink(obj)


# Function to add text at a given location
def create_text(location, text, scale_factor, collection=None):
    bpy.ops.object.text_add(location=location)
    obj = bpy.context.object
    obj.data.body = text
    obj.scale = (scale_factor , scale_factor , scale_factor )  # Scale text
    if collection:
        collection.objects.link(obj)
        bpy.context.collection.objects.unlink(obj)


# Function to create a polyline from points
def create_polyline(points, collection=None):
    if len(points) < 2:
        return  # Skip creating a polyline with a single point

    mesh = bpy.data.meshes.new("Polyline")
    obj = bpy.data.objects.new("Polyline", mesh)
    mesh.from_pydata(points, [(i, i + 1) for i in range(len(points) - 1)], [])
    mesh.update()

    if collection:
        collection.objects.link(obj)
    else:
        bpy.context.collection.objects.link(obj)


# Function to import points and create objects
def import_points_and_create_circles(context, filepath, scale_factor=0.3048):
    points = read_points(filepath)

    if not points:
        print("No valid points found in the file.")
        return {'CANCELLED'}

    return create_point_objects(context, points, scale_factor)


# Function to build circle/text/polyline geometry from a list of points
def create_point_objects(context, points, scale_factor=0.3048):
    circle_vertices = 32

    if not points:
        print("No valid points found.")
        return {'CANCELLED'}

    circle_radius = 0.5 * scale_factor  # Scale circle radius


    # Ensure the collection exists
    collection_name = "Imported Points"
    if collection_name not in bpy.data.collections:
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)
    else:
        collection = bpy.data.collections[collection_name]

    grouped_points = {}
    for point_number, location, description in points:
        scaled_location = tuple(coord * scale_factor for coord in location)

        create_circle(location=scaled_location, radius=circle_radius, vertices=circle_vertices, collection=collection)

        text_location_number = (scaled_location[0], scaled_location[1] + 0.25, scaled_location[2])
        create_text(location=text_location_number, text=str(point_number), scale_factor=scale_factor, collection=collection)

        text_location_description = (scaled_location[0], scaled_location[1] - 0.75, scaled_location[2])
        create_text(location=text_location_description, text=description, scale_factor=scale_factor, collection=collection)

        if description not in grouped_points:
            grouped_points[description] = []
        grouped_points[description].append(scaled_location)

    for description, locations in grouped_points.items():
        if len(locations) > 1:
            create_polyline(locations, collection=collection)

    print(f"Created {len(points)} points with circles and text annotations.")
    return {'FINISHED'}

def load(context,
         filepath,
         scale_factor,
         ):


    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT') 
        
    dirname = os.path.dirname(filepath)        

    import_points_and_create_circles(context, 
            filepath, 
            scale_factor,
            )

    return {'FINISHED'}


