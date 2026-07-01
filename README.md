# HVE Tools

HVE Tools is a Blender add-on package for Human Vehicle Environment (HVE) workflows. It adds an **HVE** sidebar tab in the 3D View with pre-simulation setup tools, H3D exporters, post-simulation importers, animation utilities, data analysis helpers, and CSV conversion tools.

The add-on targets Blender 4.x and uses Blender's bundled Python modules plus standard Python libraries. No separate Python package installation is required for normal Blender use.

> **New to the add-on?** See the step-by-step [User Guide](USER_GUIDE.md) for a hands-on walkthrough of every tool. This README is a compact feature reference. Inside Blender you can open the guide any time from the **Documentation** panel at the bottom of the HVE tab — its **Open User Guide** button opens a bundled offline copy (`docs/USER_GUIDE.html`) in your browser, falling back to the online guide if the file is missing.

## Capabilities

### Pre-simulation setup

- **Configurable HVE sidebar**: choose the default **HVE** tab, **Human Vehicle Environment** tab, or a custom tab name in add-on preferences.
- **Object type assignment**: mark selected objects as **Environment**, **Vehicle**, or **GATB Surface** before export, with mixed-selection warnings and one-click reclassification.
- **Material creation**: add generic, standard, and HVE light materials together with one **Add Materials** action.
- **Vehicle lighting metadata**: tag vehicle objects as HVE light components, including headlights, reverse lights, fog lights, amber/turn lights, tail lights, brake/turn lights, brake lights, and center brake lights.
- **Environment terrain metadata**:
  - Surface type: Road, Friction Zone, Curb, Water, or Other.
  - Overlay label, material name, and friction multiplier.
  - Water depth and static-water flag.
  - Soil parameters including Bekker exponent, frictional/cohesive soil modifiers, moisture content, and macrotexture.
  - Force parameters including constant, linear, quadratic, cubic, unloading, and damping values.
- **Surface-property copy helper**: copy surface type and overlay label from the active environment object to the other selected environment objects.
- **Environment presets**: save, load, and apply terrain-property presets. Included presets are stored in `hve_presets/`.

### H3D export

- **Vehicle H3D export** (`.h3d`): export selected vehicle geometry for HVE with options for selection-only export, hierarchy export, name decorations, modifier application, normals, compression, axis conversion, and global scale.
- **Environment H3D export** (`.h3d`): export selected environment geometry with options for selection-only export, name decorations, normals, compression, axis conversion, and global scale.
- **Context-aware export button**: the **H3D Export** panel chooses the vehicle, environment, or GATB contact-surface exporter based on the selected objects' assigned HVE types and warns before exporting mixed selections.

### Contact and surface-point export

- **GATB surface/contact point export** (`.csv`): classify selected meshes as **GATB Surface** and export contact-surface point data with a global scale setting.

### Post-simulation import and conversion

- **HVE variable output importer** (`.hvo` / `.csv`): import HVE variable-output files containing time plus variable output columns.
  - Choose feet or meters as the scale unit.
  - Override the scale factor.
  - Optionally save separate vehicle CSV files.
- **HVE FBX importer** (`.fbx`): import HVE FBX motion and geometry data.
  - Updates the scene timeline to include imported animation.
  - Renames imported HVE hierarchy components into cleaner labels.
  - Organizes imported data into HVE collections by event, vehicle, wheels, and body mesh.
  - Provides a post-import **Process Imported FBX** step that reduces shape keys (capped by **Max Shape Key Samples**), merges body meshes, and smooths geometry.
- **RaceRender converter** (`.csv`): convert HVE variable-output data into RaceRender-ready CSV files.

### EDR and motion animation tools

- **EDR data importer / entry**:
  - Import a single CSV that contains any of `Time, Speed, Yaw Rate, Steering Wheel Angle` columns in any order. Columns are auto-matched by header name, and a column dropdown lets you reassign each field when the headers don't match (or when the file has no header row).
  - Import or manually enter rows of `Time, Speed, YawRate`.
  - Import or manually enter rows of `Time, Speed, SteeringWheelAngle`.
  - Select a target object to animate.
  - Set frame rate from the panel.
  - Configure wheelbase and steering gear ratio when steering-wheel-angle input is used.
  - Optionally enable a slip-angle estimate with gain and maximum slip clamp.
  - Animate the target object by integrating speed and yaw-rate / steering-derived yaw-rate over time.
  - Add, remove, or clear table entries directly in Blender.
  - **Animate along an existing path**: instead of generating the trajectory from yaw-rate, follow a selected curve or polyline mesh and use the imported `Speed, Time` data to determine how far along the path the object travels at each frame (position = integral of speed). Optionally align the object to the path heading with a yaw offset.
- **Motion data importer** (`.csv`): import `Time,X,Y,Z,Roll,Pitch,Yaw` rows and animate a selected object.
  - Choose a target object.
  - Set the frame rate.
  - Choose linear or constant extrapolation.
  - Automatically stores imported motion rows on the animated object.
  - Converts position units based on the Blender scene unit system.
- **Example data files**: example CSV files are included for XYZ points, XYZ/RPY motion, steering-angle EDR data, and yaw-rate EDR data.

### Point, path, scale, and analysis utilities

- **XYZ point importer** (`.csv`): import `PointNumber,X,Y,Z,Description` rows.
  - Creates circles at point locations.
  - Adds point-number and description text.
  - Places imported objects in an **Imported Points** collection.
  - Uses a configurable scale factor.
  - Creates a polyline when more than one point is imported.
- **Motion path tools**:
  - Generate motion paths for selected objects.
  - Remove motion paths from selected objects.
  - Convert selected motion paths to 3D curve objects in a **Motion Paths** collection.
  - Toggle the motion-path overlay in the active 3D View.
- **Timed location markers** (own panel): drop triangle markers at a fixed time interval along an animated object's motion, with optional time-value labels, configurable interval, zero frame, size, forward axis, and yaw offset.
- **Roadway surface from point cloud**: build a draped ground surface mesh from a point-cloud object (e.g. an imported PLY) for vehicle simulations. Numpy-vectorized, so it stays fast on million-point clouds.
  - Set the grid **resolution** (cell size), shown in the scene's length units.
  - Sample ground height per cell using a low **percentile** ("from below") that rejects overhead noise and stray below-ground points.
  - Optionally fill sparse holes from neighbours, bounded by a **max fill distance**.
  - Optionally transfer the point cloud's per-point colour onto the surface as a color attribute.
  - Classifies the result as an **Environment** object for H3D environment export.
- **Scale objects by two points**:
  - In Edit Mode, select exactly two vertices on a mesh.
  - Enter a target distance in scene units.
  - Scale the object so the selected vertex distance matches the target.
- **Speed + acceleration baking**:
  - Calculate speed and acceleration from an animated object.
  - Bake results to a helper empty named `SpeedData_<object name>`.
  - Outputs custom animated properties for average speed, forward speed, forward acceleration, lateral acceleration, and vertical acceleration.
  - Choose the local forward axis and yaw offset.
  - Choose the averaging window in frames.
  - Use scene units automatically, or force meters or feet.
  - Optionally ignore vertical displacement, include acceleration outputs (off by default), replace prior curves, and parent the helper to the source object.

## Installation

1. Install **Blender 4.x or later**.
2. Download or clone this repository.
3. In Blender, open **Edit → Preferences → Add-ons**.
4. Click **Install…**.
5. Select this add-on package. If you downloaded the repository as a folder, install the folder or a `.zip` of the folder, depending on your Blender version and add-on installation workflow.
6. Enable **HVE Menu** in the add-ons list.
7. Open the 3D View sidebar with **N**, then select the **HVE** tab.

## Basic workflow

### 1. Prepare objects for HVE export

1. Select the object to configure.
2. Open **3D View → Sidebar → HVE → Pre-Simulation Setup → H3D Setup**.
3. Expand **Add Materials** and click **Add Materials** to create the generic, standard, and light material sets.
4. Expand **Object Type** and choose **Environment**, **Vehicle**, or **GATB Surface**.
5. For vehicles, expand **Vehicle Lighting** and tag light objects as needed.
6. For environments, expand **Terrain Properties** and set surface, water, soil, and force properties.
7. Optionally save an environment preset or apply one from the preset dropdown.

### 2. Export H3D files

1. Select the vehicle or environment object(s) you want to export.
2. Make sure the selected object(s) have the correct HVE type in **H3D Setup**. If mixed types are selected, use the warning controls to classify all selected objects as one type.
3. Open **Pre-Simulation Setup → H3D Export**.
4. Click **Export Vehicle**, **Export Environment**, or **Export GATB Contact Surfaces** based on the selected object type.
5. In the file browser, review export options such as selection-only, hierarchy, normals, compression, axis conversion, and scale.
6. Save the `.h3d` file.

### 3. Export contact surfaces

1. Select the surface/contact objects to export.
2. Classify those objects as **GATB Surface** in **Pre-Simulation Setup → H3D Setup**.
3. Open **Pre-Simulation Setup → H3D Export** and click **Export GATB Contact Surfaces**.
4. Choose a destination `.csv` and global scale.

### 4. Import HVE post-simulation files

- For variable-output files, open **Post-Simulation Processing → Variable Output Importer**, choose the `.hvo` or `.csv`, set scale options, and import.
- For HVE FBX files, open **Post-Simulation Processing → HVE FBX Importer**, click **Import FBX** and choose the `.fbx` (the hierarchy is renamed and sorted into HVE collections on import), then set **Max Shape Key Samples** and click **Process Imported FBX** to reduce shape keys, merge body meshes, and smooth the result.
- For RaceRender conversion, open **Post-Simulation Processing → RaceRender Converter** and convert the HVE variable output into RaceRender-ready `.csv` files.

### 5. Animate from EDR data

1. Open **Other Tools → EDR Data Importer / Entry**.
2. Select the target object.
3. Choose the input mode — **Yaw Rate**, **Steering Wheel Angle**, or **Path Follow**. The inputs shown below the selector change to match the chosen mode.
4. If using **Steering Wheel Angle**, set wheelbase and steering gear ratio. For **Yaw Rate** or **Steering Wheel Angle** you can also enable slip estimate and tune slip gain / maximum slip. For **Path Follow**, pick the **Path Object** (a curve or polyline mesh) and optionally enable **Align to Path** with a **Path Yaw Offset**.
5. Set the frame rate.
6. Under **Import CSV (map columns)**, click **Load CSV File**, review the auto-detected **Time / Speed** column dropdowns (plus **Yaw Rate** or **Steering** for those modes), then click **Import Mapped Data**. You can also enter rows manually.
7. Click **Animate Object** (or **Animate Along Path** in Path Follow mode).

CSV formats:

```csv
Time,Speed,YawRate
```

or:

```csv
Time,Speed,SteeringWheelAngle
```

You can also load a single CSV that holds several of these columns at once (for example `Time, Speed, Yaw Rate, Steering Wheel Angle`) in any order. When the file has a header row, the columns are matched automatically by name; otherwise generic `Column N` labels are shown and you map them yourself with the dropdowns. Both the yaw-rate and steering columns are stored when present, so you can switch the input mode and re-animate without re-importing.

In Imperial scenes, speeds are treated as mph and converted internally. In Metric scenes, speeds are treated as m/s.

To drive the object along a path you already have (an imported point polyline, a drawn curve, etc.) rather than a yaw-rate-generated trajectory, set the input mode to **Path Follow**:

1. Import or enter the `Time, Speed` data as above (no yaw-rate / steering column is needed for this mode).
2. In the **Path Follow** sub-panel, pick the **Path Object** (a curve or polyline mesh).
3. Optionally enable **Align to Path** and set a **Path Yaw Offset** so the object faces its direction of travel.
4. Click **Animate Along Path**. The cumulative distance from the speed profile is mapped onto the path arc length, so the object speeds up, slows down, and stops exactly where the speed data says — while staying on the path geometry. If the speed profile would travel farther than the path is long, the object stops at the end of the path and a warning is shown.

### 6. Animate from XYZ/RPY motion data

1. Open **Other Tools → Motion Data Importer**.
2. Select the motion target object.
3. Set frame rate and extrapolation mode.
4. Under **Import CSV (map columns)**, click **Load CSV File** and choose a CSV. A typical file has this row format:

```csv
Time,X,Y,Z,Roll,Pitch,Yaw
```

5. Review the auto-detected **Time / X / Y / Z / Roll / Pitch / Yaw** column dropdowns (fields may be in any order or under different header names; short `R` / `P` / `Y` headers are recognized as Roll / Pitch / Yaw, and generic `Column N` labels appear when the file has no header row), then click **Import and Animate**. Only Time is required; X, Y, Z, Roll, Pitch and Yaw each default to 0 when their column is set to **(None)**.

### 7. Import XYZ points

1. Open **Other Tools → Point Importer**.
2. Under **Import CSV (map columns)**, click **Load CSV File** and choose a CSV. A typical file has this row format:

```csv
PointNumber,X,Y,Z,Description
```

3. Review the auto-detected **Point Number / X / Y / Z / Description** column dropdowns (fields may be in any order or under different header names; generic `Column N` labels appear when the file has no header row), set the **Scale Factor**, then click **Import Points**. Every field is optional: X, Y and Z each default to 0 when their column is set to **(None)**, Point Number falls back to a running counter, and Description to "No Description".

The importer creates point markers, labels, descriptions, and a polyline in the **Imported Points** collection.

### 8. Create and convert motion paths

1. Select animated objects.
2. Open **Other Tools → Motion Path Tools**.
3. Use **Generate Motion Paths** to create Blender motion paths.
4. Use **Convert Motion Paths To Curve** to create editable curve objects.
5. Use **Show/Hide Motion Paths** to toggle viewport display.
6. To place time markers along the motion, use the separate **Other Tools → Timed Location Markers** panel: set the interval, zero frame, size, forward axis, and yaw offset, then click **Create Location Markers**.

### 9. Scale an object from two selected vertices

1. Select a mesh object.
2. Enter **Edit Mode**.
3. Select exactly two vertices that represent a known distance.
4. Open **Other Tools → Scale Objects**.
5. Enter the target distance in scene units.
6. Click **Scale Object**.

### 10. Bake speed and acceleration data

1. Select an animated object or assign one in **Other Tools → Speed + Acceleration**.
2. Choose the object's forward axis and optional yaw offset.
3. Set the averaging window and unit mode. The averaging window is a sampled frame count; for example, a 3-frame window compares the previous and next sampled positions.
4. Choose whether to use XY-only displacement, include acceleration outputs, and replace existing output curves.
5. Click **Calculate Speed + Acceleration**.
6. Read the animated custom properties on the generated `SpeedData_<object name>` helper empty.

### 11. Build a roadway surface from a point cloud

1. Import a roadway point cloud as a mesh object (a PLY imports as mesh vertices).
2. Open **Other Tools → Roadway Surface** and select the cloud (or set it as the **Point Cloud**).
3. Set the **Resolution (Cell Size)** (in scene units) and **Ground Percentile** (low = "from below"; rejects overhead noise), leave **Fill Holes** on (with a **Max Fill Distance**) for sparse clouds, and leave **Transfer Point Color** on to carry PLY colours onto the surface.
4. Click **Create Roadway Surface**. The draped surface mesh is created and classified as an **Environment** object for H3D environment export.

## Included examples

- `XYZ_Points_Example.csv` — sample point-import data.
- `XYZRPY_Example.csv` — sample `Time,X,Y,Z,Roll,Pitch,Yaw` motion data.
- `EDR_YawRate_Example.csv` — sample EDR yaw-rate data.
- `EDR_SteeringAngle_Example.csv` — sample EDR steering-angle data.
- `EDR_Combined_Example.csv` — sample EDR data with `Time, Speed, Yaw Rate, Steering Wheel Angle` columns for the column-mapping import.
- `hve_presets/Asphalt_Normal.json` — environment preset.
- `hve_presets/Asphalt_New.json` — environment preset.
- `hve_presets/Asphalt_Well_Traveled.json` — environment preset.

## Development and tests

The repository includes pytest-based tests for core importer/exporter and utility behavior. From the repository root, run:

```bash
pytest
```

Useful development notes:

- Keep Blender-specific imports (`bpy`, `mathutils`) at module scope where the add-on expects them; do not wrap imports in `try` / `except` blocks.
- Many tests use Blender API stubs and can run outside Blender, but full add-on workflows should still be validated in Blender.
- Prefer `rg` for repository searches.
- `USER_GUIDE.md` is the single source of truth for the guide. After editing it, regenerate the bundled HTML (used by the in-Blender **Open User Guide** button) with `python scripts/build_user_guide_html.py`. A test (`tests/test_user_guide_html.py`) fails if `docs/USER_GUIDE.html` is out of sync.

## License

These tools are distributed under the terms of the GNU General Public License, version 2 or later, as noted in the source headers.
