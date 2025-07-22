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
    circle_radius=0.5
    circle_vertices=32
    
    if not points:
        print("No valid points found in the file.")
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


