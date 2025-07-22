import bpy
import csv
import os
import math
import mathutils  # Blender's math utilities library
bl_info = {
    "name": "HVE Motion Import",
    "category": "Import-Export",
    "author": "EDC",
    "blender": (3, 1, 0),
}
def remove_from_all_collections(obj):
    """ Remove an object from all Blender collections before reassigning it. """
    if obj and obj.name in bpy.data.objects:
        for collection in bpy.data.collections:
            if obj.name in collection.objects:
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

def parent_keep_transform(child,parent):

       
    if child and parent:
        
        parent_inverse_world_matrix =  parent.matrix_world.inverted()
        
        matrix_world = child.matrix_world.copy()
        #Set parent
        child.parent = parent
        child.parent_type = 'OBJECT'
        child.matrix_parent_inverse = parent_inverse_world_matrix @ matrix_world
        
        #Restore child matrix
        #child.matrix_world = matrix_world
    
    
def read_some_data(context, filepath, scale_factor, save_separate_csv):

    """Do something with the selected file(s)."""
    filename = bpy.path.basename(filepath).split('.')[0] 
    # Format: {vehicle_name_0:{object_name_0: {variable_0:[data],variable_1:[data]...},objectname_1: {variable_0[data]...}},vehicle_name_1...
    vehicles = {}
    name_mapping = {}  # Dictionary to map object_name to object_name_trans
    group_name_mapping = {}  # Dictionary to map object_name to object_name_trans
    with open(filepath) as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        data = []
        time = []
        # strip all the white space
        for row in reader:
            row = [x.strip(' ') for x in row]
            
            try:
                time.append(float(row[0]))
            except:
                time.append(row[0])
            data.append(row[1:])
   
   #Set the frame rate
    time_step = time[5]-time[4]
    bpy.context.scene.render.fps = int(1.0/time_step)
    # Setup timeline
    numframes = len(time[4:])
    context.scene.frame_start = 0
    

    # Get the current frame end in Blender's timeline
    current_max_frame = context.scene.frame_end   
    if numframes - 1 > current_max_frame:
        context.scene.frame_end = numframes-1
        
    # Line 0: Vehicle names
    # Line 1: Variable names
    # Line 2: Translated Object:Variable
    # Line 3: Units
    # Line 4: Start of data
    
    # Column 1 is time in seconds

    # Scan the first row for vehicles
    for j, vehicle_name in enumerate(data[0]):
        # Add the vehicle name if not in the dictionary
        if vehicle_name not in vehicles.keys(): vehicles.update({vehicle_name:{}})
        object_name_variable = data[1][j]
        object_name_translated = data[2][j]
        
        # Ensure object_name_variable contains ":"
        if ":" in object_name_variable:
            object_name = object_name_variable[:object_name_variable.rfind(":")]  # Everything before the last colon
            group_name = object_name_variable.split(":")[0]  # Everything before the first colon
            variable = object_name_variable.split(":")[-1]  # Everything after the last colon
        else:
            object_name = object_name_variable   
            group_name =  object_name_variable
            variable = object_name_variable  # Use the entire string as the variable

        # Ensure object_name_translated contains ":"
        if ":" in object_name_translated:
            object_name_trans = object_name_translated[:object_name_translated.rfind(":")]
            variable_name_trans = object_name_translated.split(":")[-1].lstrip()
        else:
            object_name_trans = None  # Indicate that there is no object name
            variable_name_trans = object_name_translated  # Use the entire string as the variable name

        # Update name mapping
        if object_name_trans is not None:
            name_mapping[object_name] = object_name_trans  # Only map object names if they exist
        name_mapping[f"group_name {object_name}"] = group_name  # Only map object names if they exist
        name_mapping[variable] = variable_name_trans

        # Add the Object name if not in dictionary 
        if object_name not in vehicles[vehicle_name].keys():
            vehicles[vehicle_name].update({object_name:{}})
        vehicles[vehicle_name][object_name].update({variable:[]})
        for row in (data[4:]):
            vehicles[vehicle_name][object_name][variable].append(float(row[j]))
            
            
    if "KinematicOut" not in vehicles[vehicle_name].keys():
        print("Not a valid HVE motion file.")
        return  # Stops execution without closing Blender
    for vehicle_name in vehicles.keys():
        if vehicle_name != '':
            add_vehicle(context, vehicle_name, vehicles, scale_factor, numframes, name_mapping, filename)
        
        if save_separate_csv == True:
            ##Export data to separate CSV files
            dirname = os.path.dirname(filepath)
            csv_path = os.path.join(dirname, filename + "_" +vehicle_name + '.csv')
            time_decimals=3
            # Extract relevant translated headers for the current vehicle
            translated_headers = []
            for j, vehicle_col in enumerate(data[0]):
                if vehicle_col == vehicle_name:
                    translated_name = data[2][j]  # Object name translated (Row 3)
                    unit = data[3][j] if j < len(data[3]) else ""  # Units (Row 4)
                    full_header = f"{translated_name} {unit}" if unit else translated_name
                    translated_headers.append(full_header)
                    
            # Open the CSV file for writing
            with open(csv_path, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)

                # Write header row (Frame, Time + translated headers for the specific vehicle)
                header_row = ['Time (sec)'] + translated_headers  
                writer.writerow(header_row)

                # Write data rows
                num_rows = len(data) - 4  # Excluding header and metadata rows
                for i in range(num_rows):
                    row_values = [round(i * time_step,time_decimals)]   # Removing frame, keeping only time
                    for j, vehicle_col in enumerate(data[0]):
                        if vehicle_col == vehicle_name:
                            object_name_variable = data[1][j]
                            object_name = object_name_variable[:object_name_variable.rfind(":")]  
                            variable = object_name_variable.split(":")[-1]  
                            try:
                                value = float(vehicles[vehicle_name][object_name][variable][i])
                            except (ValueError, TypeError):  # Handle non-numeric values
                                value = 0.0  # Default to 0.0 if conversion fails

                            row_values.append(value)
                            
                    writer.writerow(row_values)
    return {'FINISHED'}

# Calculate the unit vector and magnitude of a force
def calculate_total_properties(x, y, z):
    # Magnitude of the force vector
    magnitude = math.sqrt(x**2 + y**2 + z**2)
    
    # Normalize the force vector (unit vector)
    if magnitude != 0:
        unit_vector = (x / magnitude, y / magnitude, z / magnitude)
    else:
        unit_vector = (0, 0, 0)  # Zero vector
    
    return magnitude, unit_vector

def safe_name(name, max_length=63):
    """Ensure object name fits within Blender's limit of 63 characters."""
    return name[:max_length]

def add_vehicle(context, vehicle_name, vehicles, scale_factor, numframes, name_mapping, filename):
   
   #Setup converions         
    deg2rad = math.pi/180
    if scale_factor == 1:
        scale_factor_sub = scale_factor/100
    else: 
        scale_factor_sub = scale_factor/12
        
    wheelposX = [0,0]
    track = 0

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


    # Create t    
    # Create the overall  collections (Global for all vehicles)
    overall_skids_collection_name = f"HVE: {filename}: Skids"
    overall_skids_collection = ensure_collection_exists(overall_skids_collection_name, event_collection, hide = False, dont_render=True)
   
    overall_tire_paths_collection_name = f"HVE: {filename}: Tire Paths"
    overall_tire_paths_collection = ensure_collection_exists(overall_tire_paths_collection_name, event_collection, hide = False, dont_render=True)

    overall_paths_collection_name = f"HVE: {filename}: Paths"
    overall_paths_collection = ensure_collection_exists(overall_paths_collection_name, event_collection, hide = False, dont_render=True)

    overall_velocity_collection_name = f"HVE: {filename}: Velocities"
    overall_velocity_collection = ensure_collection_exists(overall_velocity_collection_name, event_collection, hide = False, dont_render=True)
        
    overall_cameras_collection_name = f"HVE: {filename}: Cameras"
    overall_cameras_collection = ensure_collection_exists(overall_cameras_collection_name, event_collection, hide = False, dont_render=True)

    overall_vehicles_collection_name = f"HVE: {filename}: Vehicles"
    overall_vehicles_collection = ensure_collection_exists(overall_vehicles_collection_name, event_collection, hide = False, dont_render=True)
    
    overall_acceleration_collection_name = f"HVE: {filename}: Accelerations"
    overall_acceleration_collection = ensure_collection_exists(overall_acceleration_collection_name, event_collection, hide = False, dont_render=True)
        
    overall_force_collection_name = f"HVE: {filename}: Forces"
    overall_force_collection = ensure_collection_exists(overall_force_collection_name, event_collection, hide = False, dont_render=True)

    overall_vehicle_data_collection_name = f"HVE: {filename}: Data"
    overall_vehicle_data_collection = ensure_collection_exists(overall_vehicle_data_collection_name, event_collection, hide = False, dont_render=True)


    # Ensure the layer collection exists before setting it as active
    layer_collection = None
    for lc in bpy.context.view_layer.layer_collection.children:
        if lc.name == overall_skids_collection.name:
            layer_collection = lc
            break

    if layer_collection:
        bpy.context.view_layer.active_layer_collection = layer_collection


    # Create the main vehicle collection
    vehicle_collection_name = f"HVE: {filename}: {vehicle_name}"
    vehicle_collection = ensure_collection_exists(vehicle_collection_name, event_collection, hide = False, dont_render=False)
    
    # Ensure the layer collection exists before setting it as active
    layer_collection = None
    for lc in bpy.context.view_layer.layer_collection.children:
        if lc.name == vehicle_collection.name:
            layer_collection = lc
            break

    if layer_collection:
        bpy.context.view_layer.active_layer_collection = layer_collection



    # Create subcollections 
    wheels_collection_name = f"Wheels: {vehicle_name}: {filename}"
    ensure_collection_exists(wheels_collection_name, vehicle_collection, hide = False, dont_render=True)
        
    tires_collection_name = f"Tires: {vehicle_name}: {filename}"
    ensure_collection_exists(tires_collection_name, vehicle_collection, hide = False, dont_render=True)
        
   
    extras_collection_name =f"Extras: {vehicle_name}: {filename}"
    ensure_collection_exists(extras_collection_name, vehicle_collection, hide = False, dont_render=True)
 
    paths_collection_name =f"Paths: {vehicle_name}: {filename}"
    ensure_collection_exists(paths_collection_name, vehicle_collection, hide = False, dont_render=True)
        
    tire_paths_collection_name =f"Tire Paths: {vehicle_name}: {filename}"
    ensure_collection_exists(tire_paths_collection_name, vehicle_collection, hide = False, dont_render=True)
    
    skids_collection_name =f"Skids: {vehicle_name}: {filename}"
    ensure_collection_exists(skids_collection_name, vehicle_collection, hide = False, dont_render=False)
    
    
    # Used to create objects, if they already exist, clear the animation data
    def create_obj(name):
        name = safe_name(name)
        obj = bpy.context.scene.objects.get(name)
        exists = True
        if not obj:
            obj = bpy.data.objects.new(name, None )
            context.collection.objects.link(obj)
            exists = False
        obj.animation_data_clear()
        return obj, exists  

    def create_cube_obj(name):
        name = safe_name(name)
        # Create or retrieve the cube object
        obj = bpy.context.scene.objects.get(name)
        if not obj:
            bpy.ops.mesh.primitive_cube_add(
                size=scale_factor, 
                calc_uvs=True, 
                enter_editmode=False, 
                align='WORLD', 
                location=(0, 0, 0), 
                rotation=(0, 0, 0), 
                scale=(2, 2, 2)
                )
            obj = bpy.context.active_object
            obj.name = name
            
            # Set properties
            obj.hide_render = True  # Optional: Hide from render
            obj.display_type = 'WIRE'  # Display as wireframe in the viewport
            
            
            
        obj.animation_data_clear()     

        # Return the cylinder object
        return obj    
                
    def create_cylinder_obj(name, location=(0, 0, 0), radius=1, depth=1):
        name = safe_name(name)
        # Create or retrieve the cylinder object
        obj = bpy.context.scene.objects.get(name)
        exists = True
        if not obj:
            exists = False
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=32,    # Number of sides
                radius=radius,  # Radius of the base
                depth=depth,    # Height of the cylinder
                location=location
            )
            obj = bpy.context.active_object
            obj.name = name
            # Rotate the cylinder 90 degrees about the X-axis
            obj.rotation_euler = (math.radians(90), 0, 0)  # Rotate 90 degrees on X

            
            # Apply the rotation to make it permanent (reset rotation)
            bpy.context.view_layer.objects.active = obj  # Ensure the object is active
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

            # Set properties
            obj.display_type = 'WIRE'  # Display as wireframe in the viewport
            
            
            
        obj.animation_data_clear()     

        # Return the cylinder object
        return obj , exists   
  
       
    # Used to create curve objects, if they already exist, clear the animation data
    def create_curve_obj(
        name: str,
        points: list[tuple[float, float, float]],
        custom_properties: dict[str, str | float | int | bool] = None,
    ) -> bpy.types.Object:
        """
        Create or update a curve object in Blender, optionally adding custom properties.

        Parameters:
            name (str): Name of the curve object.
            points (list[tuple[float, float, float]]): List of (x, y, z) coordinates for the curve points.
            bevel_depth (float): Thickness of the curve (default: 0.0).
            resolution (int): Resolution of the curve (default: 2).
            spline_type (str): Type of the curve ('POLY' or 'BEZIER', default: 'POLY').
            dimensions (str): Dimension of the curve ('2D' or '3D', default: '3D').
            custom_properties (dict[str, str | float | int | bool]): Custom properties to assign to the curve (optional).

        Returns:
            bpy.types.Object: The created or updated curve object.
        """
        
        name = safe_name(name)
        if not points:
            raise ValueError("Points list cannot be empty.")
            
        bevel_depth: float = 0.1*scale_factor      
        resolution: int = 2
        spline_type: str = 'POLY'
        dimensions: str = '3D'
        
        if spline_type not in {'POLY', 'BEZIER'}:
            raise ValueError(f"Invalid spline type '{spline_type}'. Must be 'POLY' or 'BEZIER'.")

        curve_object = bpy.context.scene.objects.get(name)

        if not curve_object:
            curve_data = bpy.data.curves.new(name=name, type='CURVE')
            curve_data.dimensions = dimensions
            curve_object = bpy.data.objects.new(name, curve_data)
            bpy.context.collection.objects.link(curve_object)
        else:
            curve_object.data.dimensions = dimensions

        curve_data = curve_object.data
        curve_data.splines.clear()
        spline = curve_data.splines.new(type=spline_type)

        if spline_type == 'POLY':
            spline.points.add(len(points) - 1)
            for i, (x, y, z) in enumerate(points):
                spline.points[i].co = (x, y, z, 1)
        elif spline_type == 'BEZIER':
            spline.bezier_points.add(len(points) - 1)
            for i, (x, y, z) in enumerate(points):
                bez_point = spline.bezier_points[i]
                bez_point.co = (x, y, z)
                bez_point.handle_left = (x - 0.5, y, z)
                bez_point.handle_right = (x + 0.5, y, z)

        curve_data.bevel_depth = bevel_depth
        curve_data.resolution_u = resolution

        # Add custom properties to the curve object
        if custom_properties:
            frame = -1
            while frame < numframes-1:
                frame = frame + 1
                for prop_name, prop_value in custom_properties.items():
                    curve_object[prop_name] = prop_value[frame]
                    curve_object.keyframe_insert(data_path=f'["{prop_name}"]', frame=frame)
                    
        return curve_object

    def create_mesh_obj(
        name: str,
        points: list[tuple[float, float, float]],
        custom_properties: dict[str, list] = None,    
    ) -> bpy.types.Object:
        """
        Create or update a mesh object in Blender, connecting successive points with edges.

        Parameters:
            name (str): Name of the mesh object.
            points (list[tuple[float, float, float]]): List of (x, y, z) coordinates for the vertices.
            custom_properties (dict[str, list]): Custom properties to assign to the mesh (optional).
            numframes (int): Number of frames for animation (default: 1).

        Returns:
            bpy.types.Object: The created or updated mesh object.
        """
        name = safe_name(name)
        if not points:
            raise ValueError("Points list cannot be empty.")

        # Generate edges by connecting successive points
        edges = [(i, i + 1) for i in range(len(points) - 1)]

        # Create or get the mesh object
        mesh_data = bpy.data.meshes.get(name)
        if not mesh_data:
            mesh_data = bpy.data.meshes.new(name)
        mesh_data.clear_geometry()

        mesh_object = bpy.data.objects.get(name)
        if not mesh_object:
            mesh_object = bpy.data.objects.new(name, mesh_data)
            bpy.context.collection.objects.link(mesh_object)

        # Set vertices and edges
        mesh_data.from_pydata(points, edges, [])
        mesh_data.update()

        # Add custom properties and animate them
        if custom_properties:
            frame = -1
            while frame < numframes-1:
                frame = frame + 1
                for prop_name, prop_value in custom_properties.items():
                    mesh_object[prop_name] = prop_value[frame]
                    mesh_object.keyframe_insert(data_path=f'["{prop_name}"]', frame=frame)
            
            for prop_name, prop_values in custom_properties.items():
                if len(prop_values) != len(points):
                    raise ValueError(f"The number of values for '{prop_name}' must match the number of points.")

                # Add the attribute if it doesn't exist
                if prop_name not in mesh_data.attributes:
                    attr = mesh_data.attributes.new(prop_name, 'FLOAT', 'POINT')
                else:
                    attr = mesh_data.attributes[prop_name]

                # Assign values to the attribute
                for i, value in enumerate(prop_values):
                    attr.data[i].value = value
            

        return mesh_object
        


    def create_arrowhead(name, scale):
        """Creates a scaled cone and cylinder, then joins them into one object.
           If an object with the given name already exists, it returns that object instead of recreating it.
        """
        exists = True 
        name = safe_name(name)
        # Check if object already exists
        if name in bpy.data.objects:
            print(f"Object '{name}' already exists.")
            return bpy.data.objects[name], exists
        print(exists)
        exists = False
        print(exists)
        # Create a cone (Arrowhead)
        bpy.ops.mesh.primitive_cone_add(radius1=1, depth=2, location=(0, 0, 0.875 * scale_factor))
        cone = bpy.context.object
        cone.name = "Scaled_Cone"
        cone.scale = (0.010287, 0.010287, 0.0381)

        # Create a cylinder (Arrow Shaft)
        bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=2, location=(0, 0, 0.442913   * scale_factor))
        cylinder = bpy.context.object
        cylinder.name = "Cylinder"
        cylinder.scale = (0.001524, 0.001524, 0.135)

        # Select both objects and join them
        bpy.ops.object.select_all(action='DESELECT')
        cone.select_set(True)
        cylinder.select_set(True)
        bpy.context.view_layer.objects.active = cone
        bpy.ops.object.join()

        # Rename the merged object
        arrowhead = bpy.context.object
        arrowhead.name = name

        # Move the 3D cursor to (0,0,0)
        bpy.context.scene.cursor.location = (0, 0, 0)

        # Set the object's origin to the 3D cursor
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
            
        bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
     
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        # Change pivot point to 3D Cursor
        bpy.context.tool_settings.transform_pivot_point = 'CURSOR'


        bpy.ops.transform.resize(value=(1.0, 1.0, scale))        
        bpy.ops.object.mode_set(mode='OBJECT')   
        
        bpy.ops.object.transform_apply(scale=True)
        
        return bpy.context.object, exists    # Return the final merged object
  
        
    #Create Camera
    def create_camera_obj(name):
    #Create Camera
        name = safe_name(name)
        cam_object = bpy.context.scene.objects.get(name)
        if not cam_object:
            cam = bpy.ops.object.camera_add(align='WORLD', enter_editmode=False, location=(0, 0, 0), rotation=(math.pi/2-.2, -0, math.pi/2))
            bpy.context.object.data.clip_end = 500
            cam_object = bpy.context.active_object
            cam_object.location = (20,0,3)
            cam_object.name = name
            cam_object.data.name = name
            cam_object.parent = blender_CG_obj
            # Return the camera
        return cam_object


    def add_or_get_geometry_nodes_modifier(blender_obj, node_group_name="NewGN", base_color=(1, 0, 0, 1)):
        """
        Ensures the given Blender object has a Geometry Nodes modifier
        with the specified node group and material.
        
        Parameters:
        - blender_obj: The Blender object to modify.
        - node_group_name: The name of the Geometry Node Group (default: "NewGN").
        - base_color: The RGBA color for the material (default: Red (1, 0, 0, 1)).
        
        Returns:
        - The Geometry Nodes modifier.
        """

        # Check for existing Geometry Nodes modifier
        existing_modifier = None
        for mod in blender_obj.modifiers:
            if mod.type == 'NODES' and mod.name == "GeometryNodes":
                existing_modifier = mod
                break

        # If no modifier exists, create a new one
        if existing_modifier is None:
            geo_modifier = blender_obj.modifiers.new(name="GeometryNodes", type='NODES')

            # Check if the node group already exists
            node_group = bpy.data.node_groups.get(node_group_name)

            if node_group is None:
                node_group = bpy.data.node_groups.new(name=node_group_name, type='GeometryNodeTree')
                node_group.use_fake_user = True  # Prevent Blender from deleting it
                node_group.is_modifier = True

                # Add input and output nodes
                input_node = node_group.nodes.new(type='NodeGroupInput')
                output_node = node_group.nodes.new(type='NodeGroupOutput')

                node_group.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
                node_group.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

                # Position nodes
                input_node.location = (-200, 0)
                output_node.location = (200, 0)

                # Create a Set Material Node
                set_material_node = node_group.nodes.new(type='GeometryNodeSetMaterial')
                set_material_node.location = (200, -400)

                # Create or get the material
                material_name = node_group_name  # Use node group name as material name
                material = bpy.data.materials.get(material_name)
                if material is None:
                    material = bpy.data.materials.new(name=material_name)
                    material.use_nodes = True
                    material_tree = material.node_tree

                    # Clear any existing nodes
                    material_tree.nodes.clear()

                    # Create a Principled BSDF Node
                    principled_bsdf_node = material_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
                    principled_bsdf_node.location = (-200, -400)
                    principled_bsdf_node.inputs["Base Color"].default_value = base_color  # Set color

                    # Create a Material Output Node
                    material_output_node = material_tree.nodes.new(type='ShaderNodeOutputMaterial')
                    material_output_node.location = (0, -400)

                    # Connect shader nodes in the material node tree
                    material_tree.links.new(principled_bsdf_node.outputs["BSDF"], material_output_node.inputs["Surface"])

                # Assign the material to Set Material node
                set_material_node.inputs["Material"].default_value = material

                # Connect nodes
                node_group.links.new(input_node.outputs["Geometry"], set_material_node.inputs["Geometry"])
                node_group.links.new(set_material_node.outputs["Geometry"], output_node.inputs["Geometry"])

            geo_modifier.node_group = node_group
            print(f"Added new Geometry Nodes modifier with node group '{node_group_name}'.")
        else:
            geo_modifier = existing_modifier
            print(f"Using existing Geometry Nodes modifier with node group '{existing_modifier.node_group.name}'.")

        return geo_modifier
    
    
    # Function to check for a custom property on an object
    def has_custom_property(obj, property_name):
        if obj is None:
            print("Object is None.")
            return False
        
        return property_name in obj.keys()
    # Create CG object - will be the parent object
    blender_CG_obj, exists = create_obj(f"CG: {vehicle_name}: {filename}")
    blender_CG_obj.empty_display_type = 'SPHERE'    
    blender_CG_obj.empty_display_size =  scale_factor * .3
    blender_body_obj = create_cube_obj(f"Body: {vehicle_name}: {filename}")
    blender_body_obj.parent = blender_CG_obj
    assign_objects_to_subcollection(vehicle_collection_name, event_collection, blender_CG_obj)
    assign_objects_to_collection(overall_vehicles_collection_name, blender_CG_obj)  
    assign_objects_to_subcollection(extras_collection_name, vehicle_collection, blender_body_obj)
    
    def create_custom_properties(blender_obj,veh_obj_data,custprops_exclude):
        for obj_variable in veh_obj_data.keys():
            if obj_variable in name_mapping:
                obj_variable_trans = name_mapping[obj_variable]
            else:
                obj_variable_trans = obj_variable           
            if obj_variable_trans not in custprops_exclude:
                if obj_variable_trans not in blender_obj:
                    blender_obj[obj_variable_trans] = 1.0

                    # get or create the UI object for the property
                    ui = blender_obj.id_properties_ui(obj_variable_trans)
                    ui.update(description = obj_variable_trans)
                    ui.update(default = 1.0)
                    ui.update(min=-1000000.0, soft_min=-1000000.0)
                    ui.update(max=1000000.0, soft_max=1000000.0)
                #create_custom_property(blender_obj,obj_variable)
                frame = -1
                while frame < numframes-1:
                    frame = frame + 1
                    blender_obj[obj_variable_trans] = veh_obj_data[obj_variable][frame]
                    blender_obj.keyframe_insert(data_path=f'["{obj_variable_trans}"]', frame=frame)
                    
    def create_full_vehicle_data(
        name: str,
        vehicle_data: dict,
        name_mapping: dict,
        numframes: int
    ) -> bpy.types.Object:
        """
        Create a mesh object in Blender, connecting successive points with edges.
        Stores all vehicle-related data as attributes using translated names.

        Parameters:
            name (str): Name of the mesh object.
            vehicle_data (dict): Dictionary containing all vehicle motion data.
            name_mapping (dict): Dictionary mapping original names to translated names.
            numframes (int): Number of frames.

        Returns:
            bpy.types.Object: The created or updated mesh object.
        """
        if not vehicle_data:
            print("No vehicle data provided.")
            return None

        # Prepare lists for points and attributes
        points = []
        attributes = {}  # Dictionary to store translated attributes
        for frame in range(numframes):
            x = 0
            y = 0
            z = 0
            points.append((x, y, z))

            # Store attribute values with translated names
            for section_name, section_data in vehicle_data.items():
                for key, values in section_data.items():
                    translated_key = name_mapping.get(key, key)  # Use translated name if available
                    translated_section_name = name_mapping.get(section_name, section_name)  # Use translated name if available
                    group_name = name_mapping.get(f"group_name {section_name}", f"group_name {section_name}")  # Use translated name if available
                    
                    full_key = f"{group_name}: {translated_section_name}: {translated_key}"
                    if group_name == translated_section_name:
                        full_key = f"{translated_section_name}: {translated_key}"         


                    if full_key not in attributes:
                        attributes[full_key] = []
                    # Ensure only numframes values are stored
                    attributes[full_key] = values[:numframes]  # Direct assignment prevents extra appends


        # Generate edges connecting successive points
        edges = [(i, i + 1) for i in range(len(points) - 1)]

        # Create or get the mesh data
        mesh_data = bpy.data.meshes.get(name)
        if not mesh_data:
            mesh_data = bpy.data.meshes.new(name=name)
        mesh_data.clear_geometry()

        # Create or get the mesh object
        mesh_object = bpy.data.objects.get(name)
        if not mesh_object:
            mesh_object = bpy.data.objects.new(name, mesh_data)
            bpy.context.collection.objects.link(mesh_object)

        # Set vertices and edges
        mesh_data.from_pydata(points, edges, [])
        mesh_data.update()

        # Add translated attributes to the mesh
        for attr_name, attr_values in attributes.items():
            if len(attr_values) != len(points):
                print(f"Skipping {attr_name} (mismatched data length)")
               
                continue

            # Create or get the attribute
            if attr_name not in mesh_data.attributes:
                attr = mesh_data.attributes.new(attr_name, 'FLOAT', 'POINT')
            else:
                attr = mesh_data.attributes[attr_name]

            # Assign attribute values
            for i, value in enumerate(attr_values):
                attr.data[i].value = value

        return mesh_object
    
    
    
    # Function to remove an object from all collections before reassigning
    def remove_from_all_collections(obj):
        """ Remove an object from all Blender collections before reassigning it. """
        for collection in obj.users_collection:
            collection.objects.unlink(obj)

    # Get all vehicle data (not just kinematic)
    vehicle_data = vehicles[vehicle_name]  # Now includes everything
    numframes = len(vehicle_data["KinematicOut"]["VehKinematicX"])  # Get frame count

    # Create the mesh with translated attributes
    vehicle_data = create_full_vehicle_data(
        f"Data: {vehicle_name}: {filename}", 
        vehicle_data, 
        name_mapping,  # Pass name mapping dictionary
        numframes
    )
    
    assign_objects_to_subcollection(extras_collection_name, vehicle_collection, vehicle_data)  
    assign_objects_to_collection(overall_vehicle_data_collection_name, vehicle_data) 
    
    # Process each object in the vehicle dictionary:
    for veh_obj_name in vehicles[vehicle_name].keys():
        veh_obj_data = vehicles[vehicle_name][veh_obj_name]
        if veh_obj_name in name_mapping:
            obj_name = name_mapping[veh_obj_name]
        else:
            obj_name = veh_obj_name
        frame = -1
        if veh_obj_name=='KinematicOut':
            blender_obj = blender_CG_obj
            custprops_exclude = [''] #['X','Y','Z','Roll','Pitch','Yaw']
            blender_CG_obj.location = (0,0,0)
            blender_CG_obj.rotation_euler = (0,0,0)
            blender_CG_obj.keyframe_insert(data_path ='location', frame = frame)
            blender_CG_obj.keyframe_insert(data_path = 'rotation_euler', frame = frame)

            while frame < numframes-1:
                frame = frame + 1
                locationx=veh_obj_data['VehKinematicX'][frame]*scale_factor
                locationy=veh_obj_data['VehKinematicY'][frame]*-1*scale_factor
                locationz=veh_obj_data['VehKinematicZ'][frame]*-1*scale_factor
                blender_CG_obj.location = (locationx, locationy, locationz)
                blender_CG_obj.rotation_euler = (veh_obj_data['VehKinematicRoll'][frame]*deg2rad, veh_obj_data['VehKinematicPitch'][frame]*-1*deg2rad, veh_obj_data['VehKinematicYaw'][frame]*-1*deg2rad)
                blender_CG_obj.keyframe_insert(data_path="location", frame=frame)
                blender_CG_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
            create_custom_properties(blender_obj,veh_obj_data,custprops_exclude)
            
            # Define the points of the spline
            points = []
            # Custom  properties                       
            custom_properties = {
                "X": [],
                "Y": [],
                "Z": [],
                "Roll": [],
                "Pitch": [],
                "Yaw": [],
            }
            frame = -1
            while frame < numframes-1:
                frame = frame+1
                locationx=veh_obj_data['VehKinematicX'][frame]*scale_factor
                locationy=veh_obj_data['VehKinematicY'][frame]*-1*scale_factor
                locationz=veh_obj_data['VehKinematicZ'][frame]*-1*scale_factor
                points.append((locationx, locationy, locationz))
                # Adding data to the dictionary
                custom_properties["X"].append(locationx)   
                custom_properties["Y"].append(locationy)             
                custom_properties["Z"].append(locationz)
                custom_properties["Roll"].append(veh_obj_data['VehKinematicRoll'][frame]*deg2rad)   
                custom_properties["Pitch"].append(veh_obj_data['VehKinematicPitch'][frame]*deg2rad)             
                custom_properties["Yaw"].append(veh_obj_data['VehKinematicYaw'][frame]*deg2rad)                
            # Create a new object with the curve data
            
            cg_curve_object = create_curve_obj(f"CG Path: {vehicle_name}: {filename}",points, custom_properties)   

            assign_objects_to_subcollection(paths_collection_name, vehicle_collection, cg_curve_object)    
            assign_objects_to_collection(overall_paths_collection_name, cg_curve_object) 
       
            existing_modifier = None
            for mod in cg_curve_object.modifiers:
                if mod.type == 'NODES' and mod.name == "GeometryNodes":
                    existing_modifier = mod
                    break

            # If no modifier exists, create a new one
            if existing_modifier is None:
                # Add a Geometry Nodes modifier
                geo_modifier = cg_curve_object.modifiers.new(name="GeometryNodes", type='NODES')
              
                # Check if the node group already exists
                node_group = bpy.data.node_groups.get("CGPaths")
                              
                if node_group is None:
                    node_group = bpy.data.node_groups.new(name="CGPaths", type='GeometryNodeTree')
                    node_group.use_fake_user = True  # Prevent Blender from deleting it
                    node_group.is_modifier = True
                    # Add input and output nodes
                    input_node = node_group.nodes.new(type='NodeGroupInput')
                    output_node = node_group.nodes.new(type='NodeGroupOutput')
                    
                    node_group.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
                    node_group.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
                    
                    # Position nodes
                    input_node.location = (-200, 0)
                    output_node.location = (200, 0)                              
                   
                    
                    # Create a Set Material Node
                    set_material_node = node_group.nodes.new(type='GeometryNodeSetMaterial')
                    set_material_node.location = (200, -400)

                    # Create or get the material
                    material_name = "CGPaths"
                    material = bpy.data.materials.get(material_name)
                    if material is None:
                        material = bpy.data.materials.new(name=material_name)
                       # Ensure the material uses nodes
                        material.use_nodes = True
                        material_tree = material.node_tree

                        # Clear any existing nodes
                        material_tree.nodes.clear()

                        # Create a Principled BSDF Node
                        principled_bsdf_node = material_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
                        principled_bsdf_node.location = (-200, -400)
                        principled_bsdf_node.inputs["Base Color"].default_value = (1,1,0,1)

                        # Create a Material Output Node
                        material_output_node = material_tree.nodes.new(type='ShaderNodeOutputMaterial')
                        material_output_node.location = (0, -400)

                        # Connect shader nodes in the material node tree
                        material_tree.links.new(principled_bsdf_node.outputs["BSDF"], material_output_node.inputs["Surface"])

                    # Assign the material to Set Material node
                    set_material_node.inputs["Material"].default_value = material
                     
                    
                    # Connect nodes
                    node_group.links.new(input_node.outputs["Geometry"], set_material_node.inputs["Geometry"])
                    node_group.links.new(set_material_node.outputs["Geometry"], output_node.inputs["Geometry"])
                
                geo_modifier.node_group = node_group 
            else:
                geo_modifier = existing_modifier
                print("Using existing Geometry Nodes modifier.")              
      
        if veh_obj_name=='KineticOut':
            blender_obj = blender_CG_obj
            custprops_exclude = [''] #['X','Y','Z','Roll','Pitch','Yaw']
            create_custom_properties(blender_obj,veh_obj_data,custprops_exclude)        
        if veh_obj_name=='DriverOut':
            blender_obj = blender_CG_obj
            custprops_exclude = [''] #['X','Y','Z','Roll','Pitch','Yaw']
            create_custom_properties(blender_obj,veh_obj_data,custprops_exclude)        
        if veh_obj_name=='DrivetrainOut':
            blender_obj = blender_CG_obj
            custprops_exclude = [''] #['X','Y','Z','Roll','Pitch','Yaw']
            create_custom_properties(blender_obj,veh_obj_data,custprops_exclude)                   

        #Force Vector
        if 'VehKineticFxImpact' in veh_obj_data.keys() and 'VehKineticFyImpact' in veh_obj_data.keys() and 'VehKineticFzImpact' in veh_obj_data.keys():
            blender_obj, exists = create_arrowhead(f"Force: Impact: {vehicle_name}: {filename}", .001)
            #blender_obj.location = (0, 0, 0)
            frame = -1            
            while frame < numframes-1:
                frame = frame+1
                # Extract x, y, z components from veh_obj_data
                x = veh_obj_data["VehKineticFxImpact"][frame]
                y = veh_obj_data["VehKineticFyImpact"][frame] * -1
                z = veh_obj_data["VehKineticFzImpact"][frame] * -1
                
                # Calculate force properties
                magnitude, unit_vector = calculate_total_properties(x, y, z)
                
                # Use unit vector to define rotation direction
                direction = mathutils.Vector(unit_vector)
                
                # Align the object to the force direction
                rotation_quaternion = direction.to_track_quat('Z', 'Y')  # Align Z-axis to force
                
                # Apply properties to Blender object
                blender_obj.rotation_mode = 'QUATERNION'
                blender_obj.rotation_quaternion = rotation_quaternion
                blender_obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)
                
                blender_obj.scale = (1, 1, magnitude)
                blender_obj.keyframe_insert(data_path="scale",index=2, frame=frame)
            blender_obj.parent = blender_CG_obj
            blender_obj.rotation_euler = (0,-math.pi/2,0)
            blender_obj.keyframe_insert(data_path="rotation_euler", frame=-1)
            blender_obj.scale = (20,20, 1)
            blender_obj.keyframe_insert(data_path="scale",index=2, frame=-1)            
            assign_objects_to_subcollection(extras_collection_name, vehicle_collection, blender_obj)      
            assign_objects_to_collection(overall_force_collection_name, blender_obj)     

            add_or_get_geometry_nodes_modifier(blender_obj, node_group_name="ForceVectors", base_color=(0 , 0, 1, 1))

        #Velocity Vectors
        if 'VehKinematicVTotal' in veh_obj_data.keys()  :
            blender_obj, exists = create_arrowhead(f"Velocity: {vehicle_name}: {filename}", 1)
            frame = -1
            while frame < numframes-1:
                frame = frame+1
                # Order needs to be YXZ
                blender_obj.rotation_mode = 'YXZ'
                # Extract velocity components
                if 'VehKinematicVLong' in veh_obj_data.keys():
                    v_long = veh_obj_data['VehKinematicVLong'][frame]
                else: 
                    v_long = 0
                if  'VehKinematicVSide' in veh_obj_data.keys():
                    v_side = veh_obj_data['VehKinematicVSide'][frame]
                else:
                    v_side = 0
                if  'VehKinematicVNormal' in veh_obj_data.keys():
                    v_normal = veh_obj_data['VehKinematicVNormal'][frame]
                else:
                    v_normal = 0
                
                if  'VehKinematicSideslip' in veh_obj_data.keys():
                    sideslip = veh_obj_data['VehKinematicSideslip'][frame]*deg2rad 

                elif v_long == 0:
                    sideslip = 0
                else:    
                    sideslip = math.atan2(v_side , v_long) 
                    
                
                # Compute the denominator safely
                denominator = math.sqrt(v_long**2 + v_side**2)

                # Prevent division by zero
                if denominator == 0:
                    angle = 0  # Default angle when denominator is zero
                else:
                    angle = math.atan2(v_normal , denominator)

                # Apply rotation
                blender_obj.rotation_euler = (0, math.pi/2 + angle, sideslip * -1)
                blender_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
                blender_obj.scale = (1,1,veh_obj_data['VehKinematicVTotal'][frame])
                blender_obj.keyframe_insert(data_path="scale",index=2, frame=frame)
            blender_obj.parent = blender_CG_obj
            blender_obj.rotation_euler = (0,0,0)
            blender_obj.keyframe_insert(data_path="rotation_euler", frame=-1)
            blender_obj.scale = (20, 20, 1)
            blender_obj.keyframe_insert(data_path="scale", index=2,frame=-1)
            assign_objects_to_subcollection(extras_collection_name, vehicle_collection, blender_obj)  
            assign_objects_to_collection(overall_velocity_collection_name, blender_obj)     

            add_or_get_geometry_nodes_modifier(blender_obj, node_group_name="VelocityVectors", base_color=(1 , 0, 0, 1))



            blender_obj, exists = create_obj(f"Velocity Components: {vehicle_name}: {filename}")
            blender_obj.empty_display_type = 'ARROWS'    
            blender_obj.empty_display_size = scale_factor
            frame = -1
            while frame < numframes-1:
                frame = frame+1
                # Order needs to be YXZ
                blender_obj.rotation_mode = 'YXZ'
                # Extract velocity components
                if 'VehKinematicVLong' in veh_obj_data.keys():
                    v_long = veh_obj_data['VehKinematicVLong'][frame]
                else: 
                    v_long = 0
                if  'VehKinematicVSide' in veh_obj_data.keys():
                    v_side = veh_obj_data['VehKinematicVSide'][frame]
                else:
                    v_side = 0
                if  'VehKinematicVNormal' in veh_obj_data.keys():
                    v_normal = veh_obj_data['VehKinematicVNormal'][frame]
                else:
                    v_normal = 0
                blender_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
                blender_obj.scale = (v_long,-1*v_side,-1*v_normal)
                blender_obj.keyframe_insert(data_path="scale", frame=frame)
            blender_obj.parent = blender_CG_obj

            blender_obj.rotation_euler = (0,0,0)
            blender_obj.keyframe_insert(data_path="rotation_euler", frame=-1)
            blender_obj.scale = (1, 1, 1)
            blender_obj.keyframe_insert(data_path="scale", frame=-1)
            assign_objects_to_subcollection(extras_collection_name, vehicle_collection, blender_obj)
            assign_objects_to_collection(overall_velocity_collection_name, blender_obj)

        #Acceleration Vectors
        if 'VehKinematicAccTotal' in veh_obj_data.keys()  :
            blender_obj, exists = create_arrowhead(f"Acceleration: {vehicle_name}: {filename}", 7)
            frame = -1
            while frame < numframes-1:
                frame = frame+1
                # Order needs to be YXZ
                blender_obj.rotation_mode = 'YXZ'
                # Extract acceleration components
                if 'VehKinematicAccFwd' in veh_obj_data.keys():
                    acc_long = veh_obj_data['VehKinematicAccFwd'][frame]
                else: 
                    acc_long = 0
                if  'VehKinematicAccLat' in veh_obj_data.keys():
                    acc_side = veh_obj_data['VehKinematicAccLat'][frame]*-1
                else:
                    acc_side = 0
                if  'VehKinematicAccTangent' in veh_obj_data.keys():
                    acc_normal = veh_obj_data['VehKinematicAccTangent'][frame]*-1
                else:
                    acc_normal = 0
                
                if  acc_long == 0:
                    sideslip = 0
                else:    
                    sideslip = math.atan2(acc_side , acc_long) 
                    
                # Calculate acc properties
                magnitude, unit_vector = calculate_total_properties(acc_long, acc_side, acc_normal)
                # Use unit vector to define rotation direction
                direction = mathutils.Vector(unit_vector)
                # Align the object to the force direction
                rotation_quaternion = direction.to_track_quat('Z', 'Y')  # Align Z-axis to acc
                
                
                # Apply properties to Blender object
                blender_obj.rotation_mode = 'QUATERNION'
                blender_obj.rotation_quaternion = rotation_quaternion
                blender_obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)
                
                blender_obj.scale = (1, 1, magnitude)
                blender_obj.keyframe_insert(data_path="scale",index=2, frame=frame)
            
            blender_obj.parent = blender_CG_obj
            blender_obj.rotation_euler = (0,-math.pi/2,0)
            blender_obj.keyframe_insert(data_path="rotation_euler", frame=-1)
            blender_obj.scale = (20, 20, 1)
            blender_obj.keyframe_insert(data_path="scale", index=2,frame=-1)
            assign_objects_to_subcollection(extras_collection_name, vehicle_collection, blender_obj) 
            assign_objects_to_collection(overall_acceleration_collection_name, blender_obj)     

            add_or_get_geometry_nodes_modifier(blender_obj, node_group_name="AccelerationVectors", base_color=(.2 , 0, 1, 1))



            blender_obj, exists = create_obj(f"Acceleration Components: {vehicle_name}: {filename}")
            blender_obj.empty_display_type = 'ARROWS'    
            blender_obj.empty_display_size = scale_factor*1
            frame = -1
            while frame < numframes-1:
                frame = frame+1
                # Order needs to be YXZ
                blender_obj.rotation_mode = 'YXZ'
                # Extract acceleration components
                if 'VehKinematicAccFwd' in veh_obj_data.keys():
                    acc_long = veh_obj_data['VehKinematicAccFwd'][frame]
                else: 
                    acc_long = 0
                if  'VehKinematicAccLat' in veh_obj_data.keys():
                    acc_side = veh_obj_data['VehKinematicAccLat'][frame]
                else:
                    acc_side = 0
                if  'VehKinematicAccTangent' in veh_obj_data.keys():
                    acc_normal = veh_obj_data['VehKinematicAccTangent'][frame]
                else:
                    acc_normal = 0
                blender_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
                blender_obj.scale = (acc_long,-1*acc_side,-1*acc_normal)
                blender_obj.keyframe_insert(data_path="scale", frame=frame)
            blender_obj.parent = blender_CG_obj

            blender_obj.rotation_euler = (0,0,0)
            blender_obj.keyframe_insert(data_path="rotation_euler", frame=-1)
            blender_obj.scale = (1, 1, 1)
            blender_obj.keyframe_insert(data_path="scale", frame=-1)
            assign_objects_to_subcollection(extras_collection_name, vehicle_collection, blender_obj)        
            assign_objects_to_collection(overall_acceleration_collection_name, blender_obj)
            
        # 'VehWheelx' indicates that it is a wheel and a child object
        if 'VehWheelx' in veh_obj_data.keys():
            #print(veh_obj_data.keys())
            custprops_exclude = [''] # ['x','y','z','X','Y','Z','Roll','Pitch','Yaw','Gamma','Spin','Delta','Steer','Camber']
            blender_obj, exists = create_cylinder_obj(f"Wheel: {obj_name}: {vehicle_name}: {filename}")
            blender_obj.scale[1] = scale_factor * .65
            blender_obj.scale[0] = blender_obj.scale[2] = scale_factor    
            # Get the object
            target_obj = bpy.data.objects.get(f"Tire: {obj_name}: Outer: {vehicle_name}: {filename}")

            if target_obj:                
                custom_property_name = 'Radius'                 
                # Check for the custom property
                if has_custom_property(target_obj, custom_property_name):
                    # Access the value of the custom property
                    blender_obj.scale[0] = blender_obj.scale[2] = target_obj[custom_property_name] * scale_factor_sub 
                else:
                    blender_obj.scale[0] = blender_obj.scale[2] = scale_factor
            # Get the object
            target_obj = bpy.data.objects.get(f"Tire: {obj_name}: Inner: {vehicle_name}: {filename}")
            if target_obj and exists == False:                
                #blender_obj.scale[1] = .4064
                if blender_obj and blender_obj.type == 'MESH':
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.duplicate()
                    # Duplicate the selected geometry
                    bpy.ops.mesh.duplicate()
                    # Move the duplicated geometry
                    bpy.ops.transform.translate(value=(0,scale_factor, 0))
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.transform.translate(value=(0,-scale_factor/2, 0))
                    bpy.ops.object.mode_set(mode='OBJECT')

                
            camber = [0] * (numframes)
            spin = [0] * (numframes)
            steer = [0] * (numframes)
            if 'VehWheelGamma' in veh_obj_data.keys(): camber = veh_obj_data['VehWheelGamma'] 
            if 'VehWheelSpin' in veh_obj_data.keys(): spin = veh_obj_data['VehWheelSpin'] 
            if 'VehWheelSteerDelta' in veh_obj_data.keys(): steer = veh_obj_data['VehWheelSteerDelta']
            while frame < numframes-1:
                frame = frame+1
                blender_obj.location = (veh_obj_data['VehWheelx'][frame]*scale_factor_sub,veh_obj_data['VehWheely'][frame]*scale_factor_sub*-1,veh_obj_data['VehWheelz'][frame]*scale_factor_sub*-1)
                # Order needs to be YXZ
                blender_obj.rotation_mode = 'YXZ'
                blender_obj.rotation_euler = (camber[frame]*deg2rad,spin[frame]*deg2rad,steer[frame]*-1*deg2rad)
                blender_obj.keyframe_insert(data_path="location", frame=frame)
                blender_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
            blender_obj.parent = blender_CG_obj
            blender_obj.rotation_euler = (0,0,0)
            blender_obj.keyframe_insert(data_path="rotation_euler", frame=-1)
            create_custom_properties(blender_obj,veh_obj_data,custprops_exclude)
            assign_objects_to_subcollection(wheels_collection_name, vehicle_collection, blender_obj)  
            
            
        # 'VehTirex' indicates that it is a tire and a child object
        if 'VehTirex' in veh_obj_data.keys() and 'VehTirey' in veh_obj_data.keys() and 'VehTirez' in veh_obj_data.keys():
            #print(veh_obj_data.keys())
            custprops_exclude = [''] # ['x','y','z','X','Y','Z','Roll','Pitch','Yaw','Gamma','Spin','Delta','Steer','Camber']
            blender_tire_obj, exists = create_obj(f"Tire: {obj_name}: {vehicle_name}: {filename}")
            blender_tire_obj.empty_display_type = 'ARROWS'    
            blender_tire_obj.empty_display_size = scale_factor*.002
            while frame < numframes-1:
                frame = frame+1
                blender_tire_obj.location = (veh_obj_data['VehTirex'][frame]*scale_factor_sub,veh_obj_data['VehTirey'][frame]*scale_factor_sub*-1,veh_obj_data['VehTirez'][frame]*scale_factor_sub*-1)
                blender_tire_obj.keyframe_insert(data_path="location", frame=frame)
                if "VehTireFLong" in veh_obj_data.keys():     
                    blender_tire_obj.scale.x = veh_obj_data["VehTireFLong"][frame]
                    blender_tire_obj.keyframe_insert(data_path="scale", frame=frame)
                if "VehTireFLat" in veh_obj_data.keys():     
                    blender_tire_obj.scale.y = veh_obj_data["VehTireFLat"][frame] *-1 
                    blender_tire_obj.keyframe_insert(data_path="scale", frame=frame)
                if "VehTireFNorm" in veh_obj_data.keys():     
                    blender_tire_obj.scale.z =  veh_obj_data["VehTireFNorm"][frame]
                    blender_tire_obj.keyframe_insert(data_path="scale", frame=frame) 
                if 'VehWheelSteerDelta' in veh_obj_data.keys(): 
                    steer = veh_obj_data['VehWheelSteerDelta']
                    blender_tire_obj.rotation_euler = (0,0,steer[frame]*-1*deg2rad)
                    blender_tire_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
            blender_tire_obj.parent = blender_CG_obj
            blender_tire_obj.rotation_euler = (0,0,0)
            blender_tire_obj.keyframe_insert(data_path="rotation_euler", frame=-1)
            create_custom_properties(blender_tire_obj,veh_obj_data,custprops_exclude)
            assign_objects_to_subcollection(tires_collection_name, vehicle_collection, blender_tire_obj)
        elif 'VehTireX' in veh_obj_data.keys() and  'VehTireY' in veh_obj_data.keys() and  'VehTireZ' in veh_obj_data.keys():     
            custprops_exclude = [''] # ['x','y','z','X','Y','Z','Roll','Pitch','Yaw','Gamma','Spin','Delta','Steer','Camber']
            blender_tire_obj, tire_exists = create_obj(f"Tire: {obj_name}: {vehicle_name}: {filename}")
            if tire_exists == True:
                bpy.data.objects.remove(blender_tire_obj, do_unlink=True)
                blender_tire_obj, tire_exists = create_obj(f"Tire: {obj_name}: {vehicle_name}: {filename}")  
            
           
            blender_tire_obj.empty_display_type = 'ARROWS'    
            blender_tire_obj.empty_display_size = scale_factor*.002
            bpy.context.scene.frame_set(0)
            frame = 0
            blender_tire_obj.location = (veh_obj_data['VehTireX'][frame]*scale_factor,veh_obj_data['VehTireY'][frame]*scale_factor*-1,veh_obj_data['VehTireZ'][frame]*scale_factor*-1)
            print(blender_CG_obj.location)
            parent_keep_transform(blender_tire_obj, blender_CG_obj)
            blender_tire_obj.rotation_euler = (0,0,0)
            blender_tire_obj.keyframe_insert(data_path="rotation_euler", frame=-1)          
            while frame < numframes-1:
                frame = frame+1              
                if "VehTireFLong" in veh_obj_data.keys():     
                    blender_tire_obj.scale.x = veh_obj_data["VehTireFLong"][frame]
                    blender_tire_obj.keyframe_insert(data_path="scale", frame=frame)
                if "VehTireFLat" in veh_obj_data.keys():     
                    blender_tire_obj.scale.y = veh_obj_data["VehTireFLat"][frame] *-1
                    blender_tire_obj.keyframe_insert(data_path="scale", frame=frame)
                if "VehTireFNorm" in veh_obj_data.keys():     
                    blender_tire_obj.scale.z =  veh_obj_data["VehTireFNorm"][frame]
                    blender_tire_obj.keyframe_insert(data_path="scale", frame=frame) 
            create_custom_properties(blender_tire_obj,veh_obj_data,custprops_exclude) 
            assign_objects_to_subcollection(tires_collection_name, vehicle_collection, blender_tire_obj)    

        
        # 'VehTireX' indicates that it is a tire and a child object
        if 'VehTireX' in veh_obj_data.keys() and  'VehTireY' in veh_obj_data.keys() and  'VehTireZ' in veh_obj_data.keys():         
            # Define the points of the spline
            points = []
            # Custom  properties                       
            custom_properties = {
                "Skid": []
            }
            frame = -1
            while frame < numframes-1:
                frame = frame+1
                points.append((veh_obj_data['VehTireX'][frame]*scale_factor, veh_obj_data['VehTireY'][frame]*-1*scale_factor, veh_obj_data['VehTireZ'][frame]*-1*scale_factor))
                # Adding data to the dictionary
                if "VehTireSkidFlag" in veh_obj_data.keys():
                    custom_properties["Skid"].append(veh_obj_data['VehTireSkidFlag'][frame])   
                

            # Create a new object with the curve data            
            tire_curve_object = create_curve_obj(f"Tire Path: {obj_name}: {vehicle_name}: {filename}",points, custom_properties)   
            assign_objects_to_subcollection(tire_paths_collection_name, vehicle_collection, tire_curve_object)         
            assign_objects_to_collection(overall_tire_paths_collection_name, tire_curve_object)     

            add_or_get_geometry_nodes_modifier(tire_curve_object, node_group_name="TirePaths", base_color=(0 , 1, 0, 1))
            
            # Create a new object with the curve data 
            skid_curve_object = create_mesh_obj(f"Skids: {obj_name}: Skids: {vehicle_name}: {filename}",points, custom_properties) 
            assign_objects_to_subcollection(skids_collection_name, vehicle_collection, skid_curve_object)                      
            assign_objects_to_collection(overall_skids_collection_name, skid_curve_object) 
       
            existing_modifier = None
            for mod in skid_curve_object.modifiers:
                if mod.type == 'NODES' and mod.name == "GeometryNodes":
                    existing_modifier = mod
                    break

            # If no modifier exists, create a new one
            if existing_modifier is None:
                # Add a Geometry Nodes modifier
                geo_modifier = skid_curve_object.modifiers.new(name="GeometryNodes", type='NODES')
              
                # Check if the node group already exists
                node_group = bpy.data.node_groups.get("TireSkids")
                              
                if node_group is None:
                    node_group = bpy.data.node_groups.new(name="TireSkids", type='GeometryNodeTree')
                    node_group.use_fake_user = True  # Prevent Blender from deleting it
                    node_group.is_modifier = True
                    # Add input and output nodes
                    input_node = node_group.nodes.new(type='NodeGroupInput')
                    output_node = node_group.nodes.new(type='NodeGroupOutput')
                    
                    node_group.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
                    node_group.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
                    
                    # Position nodes
                    input_node.location = (-200, 0)
                    output_node.location = (200, 0)
                                
                    # Create a Mesh to Curve Node
                    mesh_to_curve_node = node_group.nodes.new(type='GeometryNodeMeshToCurve')
                    mesh_to_curve_node.location = (0, -200)
                    
                    # Create a Curve to Mesh Node
                    curve_to_mesh_node = node_group.nodes.new(type='GeometryNodeCurveToMesh')
                    curve_to_mesh_node.location = (200, -200)
                    
                    # Create a Curve Bezier Segment Node
                    bezier_segment_node = node_group.nodes.new(type='GeometryNodeCurvePrimitiveBezierSegment')
                    bezier_segment_node.location = (-200, -200)
                    bezier_segment_node.inputs["Start"].default_value = (0.25*scale_factor, 0.0, 0.0)
                    bezier_segment_node.inputs["End"].default_value = (-0.25*scale_factor, 0.0, 0.0)
                    bezier_segment_node.inputs["Start Handle"].default_value = (0.0, 0.0, 0.0)
                    bezier_segment_node.inputs["End Handle"].default_value = (0.0, 0.0, 0.0)           
                    bezier_segment_node.inputs["Resolution"].default_value = 1    
                    
                    # Create a Separate Geometry Node
                    separate_geometry_node = node_group.nodes.new(type='GeometryNodeSeparateGeometry')
                    separate_geometry_node.location = (0, -400)
                    separate_geometry_node.domain = 'FACE'
                    
                    # Create a Set Material Node
                    set_material_node = node_group.nodes.new(type='GeometryNodeSetMaterial')
                    set_material_node.location = (200, -400)

                    # Create or get the material
                    material_name = "TireSkids"
                    material = bpy.data.materials.get(material_name)
                    if material is None:
                        material = bpy.data.materials.new(name=material_name)
                       # Ensure the material uses nodes
                        material.use_nodes = True
                        material_tree = material.node_tree

                        # Clear any existing nodes
                        material_tree.nodes.clear()

                        # Create an Attribute Node
                        attribute_node = material_tree.nodes.new(type='ShaderNodeAttribute')
                        attribute_node.location = (-600, -400)
                        attribute_node.attribute_name = "Skid"

                        # Create a Gamma Node
                        gamma_node = material_tree.nodes.new(type='ShaderNodeGamma')
                        gamma_node.location = (-400, -400)
                        gamma_node.inputs["Gamma"].default_value = 1

                        # Create a Principled BSDF Node
                        principled_bsdf_node = material_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
                        principled_bsdf_node.location = (-200, -400)
                        principled_bsdf_node.inputs["Base Color"].default_value = (0,0,0,1)

                        # Create a Material Output Node
                        material_output_node = material_tree.nodes.new(type='ShaderNodeOutputMaterial')
                        material_output_node.location = (0, -400)

                        # Connect shader nodes in the material node tree
                        material_tree.links.new(attribute_node.outputs["Color"], gamma_node.inputs["Color"])
                        material_tree.links.new(gamma_node.outputs["Color"], principled_bsdf_node.inputs["Alpha"])
                        material_tree.links.new(principled_bsdf_node.outputs["BSDF"], material_output_node.inputs["Surface"])

                    # Assign the material to Set Material node
                    set_material_node.inputs["Material"].default_value = material
                     
                    # Create an Index Node
                    index_node = node_group.nodes.new(type='GeometryNodeInputIndex')
                    index_node.location = (-400, -400)
                    
                    # Create a Scene Time Node
                    scene_time_node = node_group.nodes.new(type='GeometryNodeInputSceneTime')
                    scene_time_node.location = (-400, -600)
                    
                    # Create a Less Than Node
                    less_than_node = node_group.nodes.new(type='FunctionNodeCompare')
                    less_than_node.operation = 'LESS_THAN'
                    less_than_node.location = (-200, -600)
                    
                    # Create a Set Position node
                    set_position_node = node_group.nodes.new(type='GeometryNodeSetPosition')
                    set_position_node.location = (0, 0)

                    # Create a Combine XYZ node to define the offset vector (0, 0, 0.001)
                    combine_xyz_node = node_group.nodes.new(type='ShaderNodeCombineXYZ')
                    combine_xyz_node.location = (-200, 0)
                    
                    # Set the Z value to 0.001 (X and Y remain 0)
                    combine_xyz_node.inputs[0].default_value = 0  # X
                    combine_xyz_node.inputs[1].default_value = 0  # Y
                    combine_xyz_node.inputs[2].default_value = 0.001  # Z           
                    
                    # Connect nodes
                    node_group.links.new(input_node.outputs["Geometry"], mesh_to_curve_node.inputs["Mesh"])
                    node_group.links.new(mesh_to_curve_node.outputs["Curve"], curve_to_mesh_node.inputs["Curve"])
                    node_group.links.new(bezier_segment_node.outputs["Curve"], curve_to_mesh_node.inputs["Profile Curve"])
                    node_group.links.new(curve_to_mesh_node.outputs["Mesh"], separate_geometry_node.inputs["Geometry"])
                    node_group.links.new(separate_geometry_node.outputs["Selection"], set_material_node.inputs["Geometry"])
                    node_group.links.new(index_node.outputs["Index"], less_than_node.inputs[0])
                    node_group.links.new(scene_time_node.outputs["Frame"], less_than_node.inputs[1])
                    node_group.links.new(less_than_node.outputs["Result"],separate_geometry_node.inputs["Selection"])
                    node_group.links.new(set_material_node.outputs["Geometry"], set_position_node.inputs["Geometry"])
                    node_group.links.new(combine_xyz_node.outputs[0], set_position_node.inputs["Offset"])
                    node_group.links.new(set_position_node.outputs["Geometry"], output_node.inputs["Geometry"])
                geo_modifier.node_group = node_group 
            else:
                geo_modifier = existing_modifier
                print("Using existing Geometry Nodes modifier.")                    

            
        # large VehAccelX is an accelerometer
        if 'VehAccelX' in veh_obj_data.keys() and 'VehAccelY' in veh_obj_data.keys(): 
            custprops_exclude = ['']
            blender_accel_obj, loc_exists = create_obj(f"Accelerometer: {obj_name}: {vehicle_name}: {filename}")
            if loc_exists == True:
                bpy.data.objects.remove(blender_accel_obj, do_unlink=True)
                blender_accel_obj, loc_exists = create_obj(f"Accelerometer: {obj_name}: {vehicle_name}: {filename}")  
            
           
            blender_accel_obj.empty_display_type = 'SPHERE'    
            blender_accel_obj.empty_display_size = scale_factor * .15
            bpy.context.scene.frame_set(0)
            frame = 0
            locationx = veh_obj_data['VehAccelX'][frame]*scale_factor
            locationy = veh_obj_data['VehAccelY'][frame]*scale_factor*-1
            if 'VehAccelZ' in veh_obj_data.keys():
                locationz = veh_obj_data['VehAccelZ'][frame]*scale_factor*-1
            else:
                locationz = blender_CG_obj.location[2]

            blender_accel_obj.location = (locationx,locationy,locationz)

            parent_keep_transform(blender_accel_obj, blender_CG_obj)
 
            #blender_accel_obj.keyframe_insert(data_path="rotation_euler", frame=-1)
            create_custom_properties(blender_accel_obj,veh_obj_data,custprops_exclude) 
            assign_objects_to_subcollection(extras_collection_name, vehicle_collection, blender_accel_obj)    

            # Define the points of the spline
            points = []
            # Custom  properties                       
            custom_properties = {
                "X": [],
                "Y": [],
                "Z": [],
                "Roll": [],
                "Pitch": [],
                "Yaw": [],
            }
            frame = -1           
            while frame < numframes-1:
                frame = frame+1
                locationx = veh_obj_data['VehAccelX'][frame]*scale_factor
                locationy = veh_obj_data['VehAccelY'][frame]*scale_factor*-1
                if 'VehAccelZ' in veh_obj_data.keys():
                    locationz = veh_obj_data['VehAccelZ'][frame]*scale_factor*-1
                else:
                    locationz = blender_CG_obj.location[2]
                points.append((locationx, locationy, locationz))
                # Adding data to the dictionary
                custom_properties["X"].append(locationx)   
                custom_properties["Y"].append(locationy)             
                custom_properties["Z"].append(locationz)
                custom_properties["Roll"].append(blender_CG_obj.rotation_euler[0])   
                custom_properties["Pitch"].append(blender_CG_obj.rotation_euler[1])             
                custom_properties["Yaw"].append(blender_CG_obj.rotation_euler[2])                
            # Create a new object with the curve data
            
            curve_object = create_curve_obj(f"Accelerometer Path: {obj_name}: {vehicle_name}: {filename}",points, custom_properties)   
            
            assign_objects_to_subcollection(paths_collection_name, vehicle_collection, curve_object)   
            assign_objects_to_collection(overall_paths_collection_name, curve_object) 
            
            add_or_get_geometry_nodes_modifier(curve_object, node_group_name="AccelerometerPaths", base_color=(1 , .25, 0, 1))
            
            #Velocity Vectors
            if 'VehAccelVTotal' in veh_obj_data.keys()  :
                blender_accel_vel_obj, velocity_exists = create_arrowhead(f"Accelerometer Velocity: {obj_name}: {vehicle_name}: {filename}", 1)
                if velocity_exists == True:
                    bpy.data.objects.remove(blender_accel_vel_obj, do_unlink=True)
                    blender_accel_vel_obj, velocity_exists = create_arrowhead(f"Accelerometer Velocity: {obj_name}: {vehicle_name}: {filename}", 1)
                
               
                frame = -1
                while frame < numframes-1:
                    frame = frame+1
                    # Order needs to be YXZ
                    blender_accel_vel_obj.rotation_mode = 'YXZ'
                    # Extract velocity components
                    if 'VehAccelVLong' in veh_obj_data.keys():
                        v_long = veh_obj_data['VehAccelVLong'][frame]
                    else:
                        v_long = 0
                    if 'VehAccelVSide' in veh_obj_data.keys(): 
                        v_side = veh_obj_data['VehAccelVSide'][frame]            
                    else:
                        v_side = 0 
                    if 'VehAccelVNormal' in veh_obj_data.keys():
                        v_normal = veh_obj_data['VehAccelVNormal'][frame]
                    else: 
                        v_normal = 0                  
                    if v_long == 0:
                        sideslip = 0
                    else:    
                        sideslip = math.atan2(v_side, v_long)

                    # Compute the denominator safely
                    denominator = math.sqrt(v_long**2 + v_side**2)

                    # Prevent division by zero
                    if denominator == 0:
                        angle = 0  # Default angle when denominator is zero
                    else:
                        angle = math.atan2(v_normal, denominator)

                    # Apply rotation
                    blender_accel_vel_obj.rotation_euler = (0, math.pi/2 + angle, sideslip * -1 )
                    blender_accel_vel_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
                    blender_accel_vel_obj.scale = (1,1,veh_obj_data['VehAccelVTotal'][frame])
                    blender_accel_vel_obj.keyframe_insert(data_path="scale",index=2, frame=frame)
                
                frame = 0
                locationx = veh_obj_data['VehAccelX'][frame]*scale_factor
                locationy = veh_obj_data['VehAccelY'][frame]*scale_factor*-1
                if 'VehAccelZ' in veh_obj_data.keys():
                    locationz = veh_obj_data['VehAccelZ'][frame]*scale_factor*-1
                else:
                    locationz = blender_CG_obj.location[2]
                
                
                blender_accel_vel_obj.location = (locationx,locationy,locationz)

                parent_keep_transform(blender_accel_vel_obj, blender_accel_obj)
     
                blender_accel_vel_obj.rotation_euler = (0,0,0)
                blender_accel_vel_obj.keyframe_insert(data_path="rotation_euler", frame=-1)
                blender_accel_vel_obj.scale = (20, 20, 1)
                blender_accel_vel_obj.keyframe_insert(data_path="scale", index=2,frame=-1)
                assign_objects_to_subcollection(extras_collection_name, vehicle_collection, blender_accel_vel_obj)  
                assign_objects_to_collection(overall_velocity_collection_name, blender_accel_vel_obj)     

                add_or_get_geometry_nodes_modifier(blender_accel_vel_obj, node_group_name="VelocityVectors", base_color=(1 , 0, 0, 1))


            blender_accel_obj.rotation_euler = (blender_CG_obj.rotation_euler[0],blender_CG_obj.rotation_euler[1],blender_CG_obj.rotation_euler[2])
           
                
                
        else:
            continue
            
    ### CREATE OTHER OBJECTS ###
    #Create Camera
    cam_object = create_camera_obj(f"Camera: {vehicle_name}: {filename}")
    assign_objects_to_subcollection(extras_collection_name, vehicle_collection, cam_object)
    assign_objects_to_collection(overall_cameras_collection_name, cam_object)

    if 'DriverOut' in vehicles[vehicle_name]:
        #Steering Wheel
        if 'VehDriverSteerAngle' in vehicles[vehicle_name]['DriverOut'].keys():
            obj, exists = create_obj(f"Steering: {vehicle_name}: {filename}")
            obj.empty_display_type = 'SPHERE'    
            obj.empty_display_size = scale_factor * .6
            obj.scale.y = 0
            obj.location = (.75,.25,.25)
            frame = -1
            while frame < numframes-1:
                frame = frame + 1
                obj.rotation_euler = (0, -1*vehicles[vehicle_name]['DriverOut']['VehDriverSteerAngle'][frame]*deg2rad,  math.pi/2)
                obj.keyframe_insert(data_path="rotation_euler", frame=frame)
            obj.parent = blender_CG_obj
            obj.rotation_euler = (0,0, math.pi/2)
            obj.keyframe_insert(data_path="rotation_euler", frame=-1)
            assign_objects_to_subcollection(extras_collection_name, vehicle_collection, obj)
    
        #Brake Pedal
        if 'VehDriverBrakePdlForce' in vehicles[vehicle_name]['DriverOut'].keys():
            obj, exists = create_obj(f"Brake: {vehicle_name}: {filename}")
            obj.empty_display_type = 'SINGLE_ARROW'    
            obj.empty_display_size = scale_factor * 1.5
            obj.location = (.75,.25,-.5)
            frame = -1
            while frame < numframes-1:
                frame = frame + 1
                obj.scale = (1,1,vehicles[vehicle_name]['DriverOut']['VehDriverBrakePdlForce'][frame]/100)
                obj.keyframe_insert(data_path="scale", frame=frame)
            obj.parent = blender_CG_obj
            obj.scale = (1,1,1)
            obj.keyframe_insert(data_path="scale", frame=-1)
            assign_objects_to_subcollection(extras_collection_name, vehicle_collection, obj)
            
        #Throttle DriverOut
        if 'VehDriverThrottlePos' in vehicles[vehicle_name]['DriverOut'].keys():
            obj, exists = create_obj(f"Throttle Posn: {vehicle_name}: {filename}")
            obj.empty_display_type = 'SINGLE_ARROW'    
            obj.empty_display_size = scale_factor * 1.5
            obj.location = (.75,.3,-.5)
            frame = -1
            while frame < numframes-1:
                frame = frame + 1
                obj.scale = (1,1,vehicles[vehicle_name]['DriverOut']['VehDriverThrottlePos'][frame])
                obj.keyframe_insert(data_path="scale", frame=frame)
            obj.parent = blender_CG_obj
            obj.scale = (1,1,1)
            obj.keyframe_insert(data_path="scale", frame=-1)
            assign_objects_to_subcollection(extras_collection_name, vehicle_collection, obj)
    
def load(context,
         filepath,
         scale_unit,
         scale_factor,
         save_separate_csv
         ):


    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT') 
        
    dirname = os.path.dirname(filepath)        

    read_some_data(context, 
            filepath, 
            scale_factor,
            save_separate_csv
            )

    return {'FINISHED'}


