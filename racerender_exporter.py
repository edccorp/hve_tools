import bpy
from bpy.props import (
        BoolProperty,
        EnumProperty,
        FloatProperty,
        StringProperty,
        )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper,
        axis_conversion,
        path_reference_mode,
        )
import os
import csv

def export_racerender(context, filepath, scale_factor=1.0):

    """Do something with the selected file(s)."""
    filename = bpy.path.basename(filepath).split('.')[0] 
    # Format: {vehicle_name_0:{object_name_0: {variable_0:[data],variable_1:[data]...},objectname_1: {variable_0[data]...}},vehicle_name_1...
    vehicles = {}
    name_mapping = {}  # Dictionary to map object_name to object_name_trans
    with open(filepath) as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        data = []
        time = []
        # strip all the white space
        for row in reader:
            row = [x.strip(' ') for x in row]
            
            try:
                time.append(float(row[0]))
            except ValueError:
                # Handle non-numeric timestamps (e.g., header rows)
                time.append(row[0])
            data.append(row[1:])
    #Set the frame rate
    time_step = time[5]-time[4]
    bpy.context.scene.render.fps = int(1.0/time_step)
    # Setup timeline
    numframes = len(time[4:])
    context.scene.frame_start = 0
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
        object_name = object_name_variable[:object_name_variable.rfind(":")]  # Everything before the last colon
        variable = object_name_variable.split(":")[-1]               # Everything after the last colon
        object_name_trans = object_name_translated[:object_name_translated.rfind(":")]  # Everything before the last colon
        variable_name_trans = object_name_translated.split(":")[-1].lstrip()               # Everything after the last colon
        name_mapping[object_name] = object_name_trans
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
        ##Export data to separate CSV files
        dirname = os.path.dirname(filepath)
        csv_path = os.path.join(dirname, filename + "_" +vehicle_name + '_RaceRender.csv')
        time_decimals=3
        # Extract relevant translated headers for the current vehicle
        translated_headers = []
        for j, vehicle_col in enumerate(data[0]):
            if vehicle_col == vehicle_name:
                translated_name = data[2][j]  # Object name translated (Row 3)
                unit = data[3][j] if j < len(data[3]) else ""  # Units (Row 4)
                full_header = f"{translated_name} {unit}" if unit else translated_name
                translated_headers.append(full_header)
                
        
        
        
        # Define strings that should NOT be included in export
        EXCLUDE_KEYWORDS = ["WheelsOut", "TiresOut", "Axle"]  # Add any keywords you want to filter out

        # Extract relevant translated headers for the current vehicle
        translated_headers = []
        column_indices = []  # To track which columns to include

        for j, vehicle_col in enumerate(data[0]):
            if vehicle_col == vehicle_name:
                # Check if column should be excluded
                if any(keyword in data[2][j] for keyword in EXCLUDE_KEYWORDS):
                    continue  # Skip this column    
                    
                translated_name = data[2][j] if len(data) > 2 else "Unknown"
                unit = data[3][j] if len(data) > 3 and j < len(data[3]) else ""
                full_header = f"{translated_name} {unit}".strip()



                translated_headers.append(full_header)
                column_indices.append(j)  # Store valid column index

        # Open the CSV file for writing
        with open(csv_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)

            # Write header row (Time + filtered headers)
            writer.writerow(["Time (sec)"] + translated_headers)

            # Write data rows
            num_rows = len(data) - 4  # Excluding header and metadata rows
            for i in range(num_rows):
                row_values = [round(i * time_step, 3)]  # Time column
                for j in column_indices:  # Only process allowed columns
                    object_name_variable = data[1][j]
                    object_name = object_name_variable.rsplit(":", 1)[0]
                    variable = object_name_variable.split(":")[-1]

                    try:
                        value = float(vehicles[vehicle_name][object_name][variable][i])
                    except (KeyError, ValueError, IndexError):
                        value = 0.0  # Default to 0.0 if conversion fails

                    row_values.append(value)

                writer.writerow(row_values)

    
    return {'FINISHED'}
    
def save(context, filepath, scale_factor):
    bpy.path.ensure_ext(filepath, '.csv')

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT') 

    return export_racerender(context, filepath, scale_factor)

