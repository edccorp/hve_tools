import os
import bpy
from bpy.types import Panel


def preferences():
    return bpy.context.preferences.addons[__package__].preferences


def sync_fps_with_scene(scene, depsgraph=None):
    """Syncs UI FPS field when scene FPS is changed externally"""
    scene = getattr(scene, "scene", scene)  # depsgraph handlers may pass a Depsgraph
    if not hasattr(scene, "anim_settings"):
        return
    if scene.render.fps != scene.anim_settings.anim_fps:
        scene.anim_settings.anim_fps = scene.render.fps


def update_panel_bl_category(self, context):
    main_panels = (MOTION_PT_tools, MOTION_PT_documentation)
    sub_panels = (
        MOTION_PT_edr_importer,
        MOTION_PT_xyzrpy_importer,
        MOTION_PT_point_importer,
        MOTION_PT_motion_paths,
        MOTION_PT_timed_location_markers,
        MOTION_PT_scale_objects,
        MOTION_PT_speed_acceleration,
    )

    try:
        for p in main_panels:
            bpy.utils.unregister_class(p)
        for sp in sub_panels:
            bpy.utils.unregister_class(sp)
        n = preferences().category.strip() or "Motion Data"
        for p in main_panels:
            p.bl_category = n
            bpy.utils.register_class(p)
        for sp in sub_panels:
            bpy.utils.register_class(sp)
    except Exception as e:
        print('Motion Data Tools setting tab name failed ({})'.format(str(e)))


class MOTION_PT_base(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Motion Data"


class MOTION_PT_tools(MOTION_PT_base):
    bl_label = "Motion Data Tools"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        l = self.layout
        col = l.column(align=True)
        col.label(text="Data-driven animation and analysis.", icon='TOOL_SETTINGS')
        col.label(text="Select a tool panel below.")


class MOTION_PT_edr_importer(MOTION_PT_base):
    bl_label = "EDR Data Importer / Entry"
    bl_parent_id = "MOTION_PT_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene        
        anim_settings = scene.anim_settings  # Access property group
        anim_settings.sync_edr_settings_from_target()
        target_obj = anim_settings.edr_anim_object
        edr_mode = anim_settings.edr_input_mode

        l = self.layout
        c = l.column()

        # Mode-specific CSV format hint
        if edr_mode == 'STEERING_WHEEL_ANGLE':
            c.label(text="CSV Format: Time,Speed,SteeringWheelAngle")
        elif edr_mode == 'PATH_FOLLOW':
            c.label(text="CSV Format: Time,Speed (path sets heading)")
        else:
            c.label(text="CSV Format: Time,Speed,YawRate")

        c.label(text="Select EDR Object:")
        c.prop(anim_settings, "edr_anim_object")
        c.prop(anim_settings, "edr_input_mode")

        # --- Inputs that depend on the selected mode ---
        if edr_mode == 'PATH_FOLLOW':
            path_box = l.box()
            path_box.label(text="Path Follow", icon='CURVE_PATH')
            path_box.label(text="Speed-Time data sets position along the path")
            path_box.prop(anim_settings, "edr_path_object")
            path_box.prop(anim_settings, "edr_path_align_orientation")
            if anim_settings.edr_path_align_orientation:
                path_box.prop(anim_settings, "edr_path_yaw_offset")
        else:
            needs_wheelbase = (edr_mode == 'STEERING_WHEEL_ANGLE') or anim_settings.edr_use_slip_estimate
            if needs_wheelbase:
                c.prop(anim_settings, "edr_wheelbase")

            if edr_mode == 'STEERING_WHEEL_ANGLE':
                c.prop(anim_settings, "edr_steering_gear_ratio")
                c.label(text="yaw_rate = speed / wheelbase * tan(steering_wheel_angle / steering_gear_ratio)")
                c.label(text="Tip: lower steering ratio increases computed yaw rate.", icon='INFO')

            c.prop(anim_settings, "edr_use_slip_estimate")
            if anim_settings.edr_use_slip_estimate:
                c.prop(anim_settings, "edr_slip_gain")
                c.prop(anim_settings, "edr_slip_max_deg")
                c.label(text="beta ≈ gain * atan(wheelbase * yaw_rate / speed)")
                c.label(text="Tip: start with small gain and increase gradually.", icon='INFO')
                if edr_mode == 'STEERING_WHEEL_ANGLE':
                    c.label(text="(yaw_rate is first estimated from steering)")

        c.label(text="Frame Rate:")
        c.prop(anim_settings, "anim_fps")  # Editable FPS field

        c.label(text=f"Unit System: {scene.unit_settings.system}")  # Show unit system
        c.separator()

        # --- Flexible CSV import: load a file, map columns, then import ---
        import_box = l.box()
        import_box.label(text="Import CSV (map columns)", icon='IMPORT')
        import_box.operator("object.load_edr_csv_headers", text="Load CSV File")
        if anim_settings.edr_csv_filepath:
            import_box.label(text=f"File: {os.path.basename(anim_settings.edr_csv_filepath)}")
            if not anim_settings.edr_csv_has_header:
                import_box.label(text="No header row detected - map columns below", icon='INFO')
            # Always expose every column so the mapping is ready if you switch
            # input methods later; unused columns are simply ignored per mode.
            import_box.prop(anim_settings, "edr_col_time")
            import_box.prop(anim_settings, "edr_col_speed")
            import_box.prop(anim_settings, "edr_col_yaw_rate")
            import_box.prop(anim_settings, "edr_col_steering")
            import_box.operator("object.import_edr_mapped_csv", text="Import Mapped Data")

        c.separator()

        # --- Animate using the chosen mode ---
        if edr_mode == 'PATH_FOLLOW':
            c.operator("object.animate_path_from_speed", text="Animate Along Path")
        else:
            c.operator("object.animate_vehicle", text="Animate Object")

        if target_obj:
            c.label(text=f"Entries for: {target_obj.name}")
            entries = target_obj.vehicle_path_entries
        else:
            c.label(text="No target object selected")
            entries = []

        for i, entry in enumerate(entries):
            row = c.row()
            row.prop(entry, "time", text="Time (s)")
            row.prop(entry, "speed", text="Speed")
            if edr_mode == 'STEERING_WHEEL_ANGLE':
                row.prop(entry, "steering_wheel_angle", text="Steering Wheel Angle (°)")
            elif edr_mode == 'YAW_RATE':
                row.prop(entry, "yaw_rate", text="Yaw Rate (°/s)")

        c.operator("object.add_path_entry", text="Add Entry")
        c.operator("object.remove_path_entry", text="Remove Last Entry")
        c.operator("object.remove_all_entries", text="Remove All Entries")


class MOTION_PT_xyzrpy_importer(MOTION_PT_base):
    bl_label = "Motion Data Importer"
    bl_parent_id = "MOTION_PT_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        anim_settings = scene.anim_settings
        target_obj = anim_settings.motion_anim_object
        l = self.layout
        c = l.column()
        c.label(text="CSV Format: Time,X,Y,Z,Roll,Pitch,Yaw")
        c.label(text="Select Motion Object:")
        c.prop(anim_settings, "motion_anim_object")

        c.label(text="Frame Rate:")
        c.prop(anim_settings, "anim_fps")  # Editable FPS field
        c.label(text="Extrapolation Mode:")
        c.prop(anim_settings, "extrapolation_mode")  # 🔹 User selects extrapolation type

        c.label(text=f"Unit System: {scene.unit_settings.system}")  # Show unit system
        if target_obj:
            c.label(text=f"Stored rows for {target_obj.name}: {len(target_obj.motion_data_entries)}")
        else:
            c.label(text="No target object selected")

        # --- Load a CSV, map its columns, then import + animate ---
        c.separator()
        map_box = l.box()
        map_box.label(text="Import CSV (map columns)", icon='IMPORT')
        map_box.operator("import_anim.load_motion_csv_headers", text="Load CSV File")
        if anim_settings.motion_csv_filepath:
            map_box.label(text=f"File: {os.path.basename(anim_settings.motion_csv_filepath)}")
            if not anim_settings.motion_csv_has_header:
                map_box.label(text="No header row detected - map columns below", icon='INFO')
            map_box.prop(anim_settings, "motion_col_time")
            map_box.prop(anim_settings, "motion_col_x")
            map_box.prop(anim_settings, "motion_col_y")
            map_box.prop(anim_settings, "motion_col_z")
            map_box.prop(anim_settings, "motion_col_roll")
            map_box.prop(anim_settings, "motion_col_pitch")
            map_box.prop(anim_settings, "motion_col_yaw")
            map_box.operator("import_anim.import_mapped_motion_csv", text="Import and Animate", icon='IMPORT')


class MOTION_PT_motion_paths(MOTION_PT_base):
    bl_label = "Motion Path Tools"
    bl_parent_id = "MOTION_PT_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()

        c.label(text="Motion Path Tools", icon="ANIM_DATA")  # Section title with an icon

        c.operator("object.generate_motion_path", text="Generate Motion Paths")
        c.operator("object.remove_motion_path", text="Remove Motion Paths")
        c.operator("object.convert_motion_path_selected", text="Convert Motion Paths To Curve")
        c.operator("object.toggle_motion_path_visibility", text="Show/Hide Motion Paths")


class MOTION_PT_timed_location_markers(MOTION_PT_base):
    bl_label = "Timed Location Markers"
    bl_parent_id = "MOTION_PT_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()

        c.label(text="Timed Location Markers", icon="EMPTY_SINGLE_ARROW")
        c.prop(scene, "motion_marker_interval_seconds")
        c.prop(scene, "motion_marker_zero_frame")
        c.prop(scene, "motion_marker_size")
        c.prop(scene, "motion_marker_forward_axis")
        c.prop(scene, "motion_marker_yaw_offset")
        c.prop(scene, "motion_marker_create_time_labels")
        if scene.motion_marker_create_time_labels:
            c.prop(scene, "motion_marker_label_size")
        c.prop(scene, "motion_marker_replace_existing")
        c.operator("object.create_timed_location_markers", text="Create Location Markers")


class MOTION_PT_scale_objects(MOTION_PT_base):
    bl_label = "Scale Objects"
    bl_parent_id = "MOTION_PT_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()
        
        unit_system = context.scene.unit_settings.system
        display_unit = "m" if unit_system == 'METRIC' else "ft" if unit_system == 'IMPERIAL' else "BU"
        
        c.label(text=f"Scene Units: {unit_system}")
        c.prop(context.scene, "scale_target_distance", text=f"Target Distance ({display_unit})")
        c.operator("object.scale_by_two_points", text="Scale Object")


class MOTION_PT_speed_acceleration(MOTION_PT_base):
    bl_label = "Speed + Acceleration"
    bl_parent_id = "MOTION_PT_tools"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()

        c.label(text="Bake animated speed and acceleration", icon="FORCE_FORCE")

        if context.selected_objects:
            active = context.active_object
            source = (
                active
                if active in context.selected_objects
                else context.selected_objects[0]
            )
            c.label(text=f"Source: {source.name} (selected)", icon="OBJECT_DATA")
        else:
            c.label(text="No object selected; choose a source below", icon="INFO")
            c.prop(scene, "speed_accel_target_object")

        c.prop(scene, "speed_accel_forward_axis")
        c.prop(scene, "speed_accel_forward_yaw_offset")
        c.prop(scene, "speed_accel_window_frames")
        c.prop(scene, "speed_accel_unit_mode")
        c.prop(scene, "speed_accel_use_xy_only")
        c.prop(scene, "speed_accel_include_acceleration")
        c.prop(scene, "speed_accel_remove_old_curves")
        c.prop(scene, "speed_accel_parent_helper")
        c.operator("object.calculate_speed_acceleration", text="Calculate Speed + Acceleration")


class MOTION_PT_point_importer(MOTION_PT_base):
    bl_label = "Point Importer"
    bl_parent_id = "MOTION_PT_tools"
    bl_options = {'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls, context):
        return True
       
    def draw(self, context):
        scene = context.scene
        anim_settings = scene.anim_settings
        l = self.layout
        c = l.column()

        c.label(text="Point Importer", icon="TOOL_SETTINGS")  # Section title with an icon
        c.label(text="CSV Format: PointNumber,X,Y,Z,Description")

        # --- Load a CSV, map its columns, then import ---
        map_box = l.box()
        map_box.label(text="Import CSV (map columns)", icon='IMPORT')
        map_box.operator("import_xyz.load_point_csv_headers", text="Load CSV File")
        if anim_settings.point_csv_filepath:
            map_box.label(text=f"File: {os.path.basename(anim_settings.point_csv_filepath)}")
            if not anim_settings.point_csv_has_header:
                map_box.label(text="No header row detected - map columns below", icon='INFO')
            map_box.prop(anim_settings, "point_col_number")
            map_box.prop(anim_settings, "point_col_x")
            map_box.prop(anim_settings, "point_col_y")
            map_box.prop(anim_settings, "point_col_z")
            map_box.prop(anim_settings, "point_col_description")
            map_box.prop(anim_settings, "point_scale_factor")
            map_box.operator("import_xyz.import_mapped_points", text="Import Points")


class MOTION_OT_open_user_guide(bpy.types.Operator):
    """Open the user guide in your web browser"""
    bl_idname = "motion_data.open_user_guide"
    bl_label = "Open User Guide"

    _GITHUB_URL = "https://github.com/edccorp/hve_tools/blob/main/USER_GUIDE.md"

    def execute(self, context):
        import webbrowser
        webbrowser.open(self._GITHUB_URL)
        self.report({'INFO'}, "Opened the user guide.")
        return {'FINISHED'}


class MOTION_PT_documentation(MOTION_PT_base):
    bl_label = "Documentation"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        l = self.layout
        l.operator("motion_data.open_user_guide", text="Open User Guide", icon='HELP')
        l.label(text="Opens the online guide in your browser.", icon='INFO')


classes = (
    MOTION_PT_tools,
    MOTION_PT_edr_importer,
    MOTION_PT_xyzrpy_importer,
    MOTION_PT_point_importer,
    MOTION_PT_motion_paths,
    MOTION_PT_timed_location_markers,
    MOTION_PT_scale_objects,
    MOTION_PT_speed_acceleration,
    MOTION_PT_documentation,
    MOTION_OT_open_user_guide,
)


def register():
    # Sync UI FPS with scene FPS when scene FPS changes
    if sync_fps_with_scene not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(sync_fps_with_scene)

def unregister():
    if sync_fps_with_scene in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(sync_fps_with_scene)
