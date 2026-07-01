# HVE Tools — User Guide

A hands-on guide to using the HVE Tools Blender add-on. It walks you through
installing the add-on, finding its panels, and completing the most common
tasks step by step. For a terse feature-by-feature reference, see
[`README.md`](README.md).

---

## Contents

1. [What this add-on does](#1-what-this-add-on-does)
2. [Install and find the panels](#2-install-and-find-the-panels)
3. [How the sidebar is organized](#3-how-the-sidebar-is-organized)
4. [Task guides](#4-task-guides)
   - **Pre-Simulation Setup**
     - [4.1 Prepare objects for HVE export](#41-prepare-objects-for-hve-export)
     - [4.2 Export H3D files](#42-export-h3d-files)
   - **Post-Simulation Processing**
     - [4.3 Import post-simulation results](#43-import-post-simulation-results)
   - **Other Tools**
     - [4.4 Understanding the CSV column mapping](#44-understanding-the-csv-column-mapping)
     - [4.5 Animate from EDR data](#45-animate-from-edr-data)
     - [4.6 Animate from XYZ/RPY motion data](#46-animate-from-xyzrpy-motion-data)
     - [4.7 Import survey / point data](#47-import-survey--point-data)
     - [4.8 Motion path tools](#48-motion-path-tools)
     - [4.9 Scale an object to a known distance](#49-scale-an-object-to-a-known-distance)
     - [4.10 Bake speed and acceleration](#410-bake-speed-and-acceleration)
5. [Units and scale](#5-units-and-scale)
6. [Troubleshooting](#6-troubleshooting)
7. [Example files](#7-example-files)

---

## 1. What this add-on does

HVE Tools bridges Blender and **HVE (Human Vehicle Environment)** simulation
workflows. It lets you:

- **Set up and export** scene objects (vehicles, environments, GATB surfaces)
  as HVE `.h3d` files.
- **Import simulation results** back into Blender (variable-output CSV/HVO,
  HVE FBX, RaceRender conversion).
- **Recreate motion** from crash-data sources such as EDR reports, XYZ/RPY
  motion tables, and survey points.
- **Analyze** motion with motion-path tools, two-point scaling, and
  speed/acceleration baking.

Everything lives in one sidebar tab in the 3D View.

---

## 2. Install and find the panels

1. Install **Blender 4.x or later**.
2. Download or clone this repository (or a `.zip` of it).
3. In Blender: **Edit → Preferences → Add-ons → Install…**, then select the
   add-on package (the folder or its `.zip`).
4. Tick **HVE Menu** in the add-ons list to enable it.
5. In the 3D View, press **N** to open the sidebar, then click the **HVE** tab.

> **Tip — rename the tab.** In **Edit → Preferences → Add-ons → HVE Menu**,
> expand the preferences to choose the **HVE** tab, the **Human Vehicle
> Environment** tab, or a **Custom Tab Name**. Useful if you want HVE Tools to
> share an existing sidebar tab.

If you don't see the **HVE** tab, confirm the add-on is enabled and that you
are in the 3D View (not, say, the Shader Editor).

---

## 3. How the sidebar is organized

The **HVE** tab groups everything into three top-level panels:

| Panel | Use it for | Sub-panels |
|-------|-----------|------------|
| **Pre-Simulation Setup** | Getting Blender objects ready for HVE and exporting them | **H3D Setup**, **Export to HVE** |
| **Post-Simulation Processing** | Bringing HVE results back into Blender | **HVE FBX Importer**, **Variable Output Importer**, **RaceRender Converter** |
| **Other Tools** | Data-driven animation and analysis utilities | **EDR Data Importer / Entry**, **Motion Data Importer**, **Point Importer**, **Motion Path Tools**, **Scale Objects**, **Speed + Acceleration** |

Most panels are collapsed by default — click a panel header to expand it. The
task guides below follow this same order: Pre-Simulation Setup, then
Post-Simulation Processing, then Other Tools.

---

## 4. Task guides

Each subsection below is a self-contained task, ordered to match the panels in
the sidebar. If you just want a fast first result, jump to the quick start at
the top of [4.5 Animate from EDR data](#45-animate-from-edr-data); if you'll be
loading CSVs, skim [4.4 Understanding the CSV column mapping](#44-understanding-the-csv-column-mapping)
first.

### Pre-Simulation Setup

### 4.1 Prepare objects for HVE export

Open **Pre-Simulation Setup → H3D Setup**, then:

1. **Add Materials** — expand and click **Add Materials** to create the generic,
   standard, and HVE light material sets.
2. **Object Type** — expand and classify the selected object as **Environment**,
   **Vehicle**, or **GATB Surface**. If you selected several objects of mixed
   types, use the one-click reclassify buttons shown in the warning.
3. **Vehicle Lighting** (vehicles only) — tag light objects (headlights, brake,
   turn, fog, reverse, tail, etc.) so HVE knows their function.
4. **Terrain Properties** (environments only) — set:
   - **Surface**: type (Road / Friction Zone / Curb / Water / Other), overlay
     label, material name, friction multiplier. The **Copy Type + Overlay to
     Selected** button pushes surface type and overlay from the active object to
     the rest of the selection.
   - **Water**: depth and static-water flag.
   - **Soil**: Bekker exponent, frictional/cohesive modifiers, moisture,
     macrotexture.
   - **Forces**: constant, linear, quadratic, cubic, unloading, damping.
5. Optionally **Save Preset** / **Load Preset**, or pick one from **Apply
   Preset**, to reuse terrain settings (presets live in `hve_presets/`).

### 4.2 Export H3D files

1. Select the object(s) to export and confirm their HVE type in **H3D Setup**.
2. Open **Pre-Simulation Setup → Export to HVE**. The button adapts to the
   selected type:
   - **Export Vehicle** → `.h3d`
   - **Export Environment** → `.h3d`
   - **Export GATB Surfaces** → `.csv`
3. If a mixed selection is detected, classify everything as one type first
   (the panel offers buttons to do this).
4. In the file browser, set options (selection-only, hierarchy, normals,
   compression, axis conversion, global scale) and save.

### Post-Simulation Processing

### 4.3 Import post-simulation results

Open **Post-Simulation Processing** and pick the matching importer:

- **HVE FBX Importer** — click **Import FBX** and choose the `.fbx`. On import,
  the HVE hierarchy is renamed into cleaner labels, the scene timeline is
  extended to cover the animation, and objects are organized into HVE
  collections by event, vehicle, wheels, and body. Then set **Max Shape Key
  Samples** (the cap on shape keys kept per mesh; 0 = no cap) and click
  **Process Imported FBX** to run the **Reduce Keys → Merge Meshes → Smooth**
  cleanup pipeline.
- **Variable Output Importer** — import an HVE `.hvo`/`.csv` of time plus
  variable-output columns. Choose **feet or meters**, optionally override the
  **scale factor**, and optionally **save separate vehicle CSV files**.
- **RaceRender Converter** — convert HVE variable output into RaceRender-ready
  `.csv` files.

### Other Tools

### 4.4 Understanding the CSV column mapping

The **EDR Data Importer**, **Motion Data Importer**, and **Point Importer** all
share the same "load a file, map its columns, import" pattern. Learn it once and
it works everywhere:

1. Click **Load CSV File** and choose your `.csv`.
2. The add-on inspects the first row:
   - **Has a text header?** Columns are auto-matched by name (case-, spacing-,
     and unit-insensitive — `Yaw Rate (deg/s)`, `yaw_rate`, and `YAW` all
     match). Common abbreviations are understood too (e.g. `t`, `x`/`y`/`z`,
     and `r`/`p`/`y` for roll/pitch/yaw).
   - **No header (all numbers)?** Columns are labelled `Column 1`, `Column 2`,
     … and mapped by position. You assign them with the dropdowns.
3. Review each dropdown and fix any that guessed wrong. Set a column to
   **(None)** when your file doesn't contain that field.
4. Click the import button.

Notes:

- **Required vs optional** varies per importer (called out in each task below).
  Optional fields fall back to sensible defaults when set to **(None)**.
- The mapping is remembered, so you can re-import or switch modes without
  reloading the file.
- Reordered columns and extra unrelated columns are fine — only the mapped
  columns are read.

### 4.5 Animate from EDR data

Open **Other Tools → EDR Data Importer / Entry** to turn speed with yaw-rate,
steering-angle, or path data into motion.

**First run (quick start).** For a fast result using the bundled
`EDR_YawRate_Example.csv`:

1. Add or select an object to drive (e.g. **Add → Mesh → Cube**).
2. Set **Select EDR Object** to that object and leave **EDR Input Mode** on
   **Yaw Rate**.
3. Set **Frame Rate** (the example is 0.1 s samples, so 10 fps reproduces it
   exactly; any frame rate is resampled).
4. Under **Import CSV (map columns)**, click **Load CSV File**, pick the example,
   then click **Import Mapped Data**.
5. Click **Animate Object** and scrub the timeline.

**Input modes.** The panel shows only the inputs relevant to the selected mode:

- **Yaw Rate** — data is `Time, Speed, Yaw Rate` (deg/s). Optionally enable
  **Use Slip Estimate** and tune **Slip Gain** / **Slip Max** to add an apparent
  body-slip angle to the motion.
- **Steering Wheel Angle** — data is `Time, Speed, Steering Wheel Angle` (deg).
  Set **Wheelbase** and **Steering Gear Ratio**; yaw rate is derived with a
  bicycle model: `yaw_rate = speed / wheelbase * tan(swa / gear_ratio)`. Slip
  estimate is available here too.
- **Path Follow** — data is just `Time, Speed`; an existing curve/mesh supplies
  the heading. Pick a **Path Object** (curve or polyline mesh, different from the
  animated object), and optionally **Align to Path** with a **Path Yaw Offset**
  so the object faces its direction of travel.

**Common steps for every mode:**

1. Set **Select EDR Object** and **Frame Rate**.
2. **Import CSV (map columns)**: click **Load CSV File**, then **Import Mapped
   Data** (see [4.4](#44-understanding-the-csv-column-mapping)). All four column
   dropdowns (Time / Speed / Yaw Rate / Steering Wheel Angle) stay available
   regardless of mode, so both yaw-rate and steering values are stored — you can
   switch modes and re-animate without reloading. You can also add/edit/remove
   rows by hand in the table.
3. Click **Animate Object** (or **Animate Along Path** in Path Follow mode).

> Speeds are read as **mph** in Imperial scenes and **m/s** in Metric scenes.
> A negative first timestamp is shifted so motion starts at frame 0.

Try the examples: `EDR_YawRate_Example.csv`, `EDR_SteeringAngle_Example.csv`,
or `EDR_Combined_Example.csv` (which carries all four columns at once).

### 4.6 Animate from XYZ/RPY motion data

Open **Other Tools → Motion Data Importer** for data that already contains full
pose per timestamp.

1. Set the **Motion Object** and **Frame Rate**.
2. Choose **Extrapolation Mode** (Linear or Constant) for frames beyond the data.
3. Under **Import CSV (map columns)**, **Load CSV File** and review the
   **Time / X / Y / Z / Roll / Pitch / Yaw** dropdowns
   (see [4.4](#44-understanding-the-csv-column-mapping)). Headers may be in any
   order or abbreviated (`t`, `x`, `y`, `z`, `r`, `p`, `y`).
4. Click **Import and Animate**.

**Only Time is required.** X, Y, Z, Roll, Pitch, and Yaw each default to 0 when
their column is set to **(None)** or absent. Position values are converted from
feet to meters in Imperial scenes. Sample file: `XYZRPY_Example.csv`.

### 4.7 Import survey / point data

Open **Other Tools → Point Importer** to place markers from a coordinate list.

1. Under **Import CSV (map columns)**, **Load CSV File** and review the
   **Point Number / X / Y / Z / Description** dropdowns
   (see [4.4](#44-understanding-the-csv-column-mapping)).
2. Set the **Scale Factor** (default `0.3048` converts feet to meters).
3. Click **Import Points**.

**Every field is optional.** X, Y, and Z each default to 0 when their column is
**(None)**; Point Number falls back to a running counter and Description to
"No Description". The importer creates a circle, a number label, and a
description label at each point in an **Imported Points** collection, and
connects points that share a description into a polyline. Sample file:
`XYZ_Points_Example.csv`.

### 4.8 Motion path tools

Open **Other Tools → Motion Path Tools** with animated object(s) selected:

- **Generate Motion Paths** / **Remove Motion Paths** — add or clear Blender
  motion paths.
- **Convert Motion Paths To Curve** — bake the path into an editable 3D curve in
  a **Motion Paths** collection (handy as a Path Follow target back in the EDR
  tool).
- **Show/Hide Motion Paths** — toggle the viewport overlay.
- **Timed Location Markers** — drop triangle markers at a fixed time interval
  along the motion, with optional time-value text labels. Configure the
  interval, zero frame, size, forward axis, and yaw offset, then click
  **Create Location Markers**.

### 4.9 Scale an object to a known distance

Open **Other Tools → Scale Objects**:

1. Select a mesh object and enter **Edit Mode**.
2. Select **exactly two vertices** spanning a known real-world distance.
3. Enter the **Target Distance** (in scene units).
4. Click **Scale Object**. The object is uniformly scaled so the two vertices
   match the target distance.

### 4.10 Bake speed and acceleration

Open **Other Tools → Speed + Acceleration** with an animated object selected (or
assign a **Source Object**):

1. Set the **Forward Direction** axis and optional **Forward Yaw Offset**.
2. Set the **Average Window (Frames)** — the centered sample count used to
   compute velocity (e.g. 3 compares the previous and next frames).
3. Choose **Distance Units** (Auto / Meters / Feet) and toggles: **Use XY Only**,
   **Include Acceleration**, **Replace Existing Curves**, **Parent Helper to
   Source**.
4. Click **Calculate Speed + Acceleration**.

Results are baked as animated custom properties (average speed, forward speed,
forward/lateral/vertical acceleration) on a helper empty named
`SpeedData_<object name>`.

---

## 5. Units and scale

- The panels display the current **Unit System** (Metric / Imperial) so you know
  how values are interpreted.
- **EDR speeds**: mph in Imperial scenes, m/s in Metric scenes.
- **Motion / point positions**: treated as feet and converted to meters in
  Imperial scenes; used as-is in Metric scenes. The Point Importer exposes an
  explicit **Scale Factor** for finer control.
- Set the scene unit system in Blender's **Scene Properties → Units** before
  importing so conversions match your data.

---

## 6. Troubleshooting

**The HVE tab is missing.** Make sure **HVE Menu** is enabled in Preferences,
you're in the 3D View, and the sidebar is open (**N**). Check the tab name in
the add-on preferences.

**"No target object selected."** EDR/motion tools animate the object chosen in
that panel's object field — set it before importing or animating.

**Import found no rows.** The required columns weren't mapped or the data didn't
parse. Re-open **Load CSV File**, verify the dropdowns point at the right
columns (Time/Speed for EDR; Time/X/Y/Z for motion; X/Y/Z for points), and make
sure numeric columns actually contain numbers.

**Auto-mapping guessed wrong.** Just override the dropdown. For header-less
files, columns are positional (`Column 1`, `Column 2`, …) and you map them by
hand.

**The vehicle faces or turns the wrong way.** For Path Follow and speed/accel
baking, set the correct **forward axis** / **yaw offset**. For yaw-rate data,
confirm the sign convention and scene unit system.

**Motion stops partway along a path.** In Path Follow mode, the speed profile
travelled farther than the path is long, so the object stops at the path end (a
warning is shown). Use a longer path or lower speeds.

**Nothing animates after import.** Confirm the frame range covers the data
(timeline start is set to 0 on import; the end is extended to the last frame)
and that you clicked the animate/import-and-animate button, not just load.

---

## 7. Example files

Bundled at the repository root for trying each importer:

| File | Use with |
|------|----------|
| `EDR_YawRate_Example.csv` | EDR importer, Yaw Rate mode |
| `EDR_SteeringAngle_Example.csv` | EDR importer, Steering Wheel Angle mode |
| `EDR_Combined_Example.csv` | EDR importer, column mapping (all four columns) |
| `XYZRPY_Example.csv` | Motion Data Importer |
| `XYZ_Points_Example.csv` | Point Importer |
| `hve_presets/*.json` | Environment terrain presets |

For a compact feature list and developer notes, see [`README.md`](README.md).
