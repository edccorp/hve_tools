# HVE Tools

## Project Overview and Goals
HVE Tools is a collection of Blender add-ons and scripts aimed at importing and exporting data related to Human Vehicle Environment (HVE) simulations. The tools help streamline workflows such as converting motion data, preparing vehicles or environments, and exchanging results with other applications.

## Installation and Dependencies
1. Install [Blender](https://www.blender.org/) 2.8x or later with its bundled Python interpreter.
2. Clone or download this repository.
3. In Blender, open **Edit → Preferences → Add-ons**, click **Install…**, and select this folder. Enable the desired tools from the add-on list.

These scripts rely on Blender's built‑in `bpy` module and standard Python libraries; no additional dependencies are required.

## Usage Examples
Below are minimal examples for running the main scripts from Blender's Python console after enabling the add-ons.

### Import CSV Motion Data (`import_xyzrpy.py`)
```python
import bpy
# Import XYZ position and RPY rotation data from a CSV file
bpy.ops.import_anim.csv(filepath="/path/to/XYZRPY_Example.csv")
```

### Export Environment to H3D (`export_environment.py`)
```python
import export_environment
# Export the current scene or selection to an H3D file
export_environment.save(bpy.context, filepath="/path/to/environment.h3d", use_selection=True)
```

### Export Vehicle to H3D (`export_vehicle.py`)
```python
import export_vehicle
# Write vehicle geometry and materials to an H3D file
export_vehicle.save(bpy.context, filepath="/path/to/vehicle.h3d", use_selection=True)
```

### Import Variable Output (`variableoutput_importer.py`)
```python
import variableoutput_importer
# Load variable output CSV data and create animation curves
variableoutput_importer.import_file("/path/to/output.csv")
```

### Import XYZ Points (`xyz_importer.py`)
```python
import xyz_importer
# Import point-cloud coordinates from a CSV file
xyz_importer.import_file("/path/to/XYZ_Points_Example.csv")
```

### Export Contacts (`contacts_exporter.py`)
```python
import contacts_exporter
# Export contact data for the selected objects
contacts_exporter.export_file("/path/to/contacts.csv")
```

### Export RaceRender Data (`racerender_exporter.py`)
```python
import racerender_exporter
# Generate RaceRender-compatible CSV output
racerender_exporter.export_file("/path/to/racerender.csv")
```

### Import Event Data Recorder (`edr_importer.py`)
```python
import edr_importer
# Import EDR data into the current scene
edr_importer.import_file("/path/to/EDR_Example.csv")
```

### Import FBX Models (`fbx_importer.py`)
```python
import fbx_importer
# Import an FBX model prepared for HVE workflows
fbx_importer.import_file("/path/to/model.fbx")
```

### Naming scheme for rotation sources

`copy_animated_rotation` looks for helper objects whose names indicate which
Euler axis they drive. The default mapping is:

- **X axis** – names containing "Camber" or "Cam"
- **Y axis** – names containing "Rotation" or "Pitch"
- **Z axis** – names containing "Steering" or "Yaw"

Names are matched case-insensitively. You can customize the expected keywords
by editing `ROTATION_AXIS_KEYWORDS` in `fbx_importer.py` or by passing your own
mapping when calling `copy_animated_rotation`. Any missing axes are skipped
during import, so the helper objects are optional.

## Contribution Guidelines
Contributions are welcome! To propose changes:
1. Fork the repository and create a feature branch.
2. Make your changes and ensure they are well documented.
3. Submit a pull request with a clear description of the improvements.

## License
These tools are distributed under the terms of the GNU General Public License, version 2 or later, as noted in the source headers.
