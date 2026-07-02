import bpy
from bpy.types import Panel


def preferences():
    return bpy.context.preferences.addons[__package__].preferences


def update_panel_bl_category(self, context):
    main_panels = (POINTCLOUD_PT_tools, POINTCLOUD_PT_documentation)

    try:
        for p in main_panels:
            bpy.utils.unregister_class(p)
        n = preferences().category.strip() or "Point Cloud"
        for p in main_panels:
            p.bl_category = n
            bpy.utils.register_class(p)
    except Exception as e:
        print('Point Cloud Tools setting tab name failed ({})'.format(str(e)))


class POINTCLOUD_PT_base(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Point Cloud"


# Names the point-cloud display input may carry ("Subsample Percent" is the
# legacy name used by clouds imported before the rename to "Points Visible %").
_POINTS_VISIBLE_NAMES = {"Points Visible %", "Subsample Percent"}


def _geonodes_subsample_input(obj):
    """Return ``(modifier, socket_identifier)`` for a point cloud's GeoNodes
    points-visible display input, or None if the object doesn't have one."""
    if obj is None:
        return None
    for mod in obj.modifiers:
        if mod.type != 'NODES' or not mod.node_group:
            continue
        ng = mod.node_group
        iface = getattr(ng, "interface", None)
        if iface is not None and hasattr(iface, "items_tree"):
            for item in iface.items_tree:
                if (getattr(item, "in_out", "") == 'INPUT'
                        and getattr(item, "name", "") in _POINTS_VISIBLE_NAMES):
                    return mod, item.identifier
        else:  # Blender 3.x
            for inp in getattr(ng, "inputs", []):
                if inp.name in _POINTS_VISIBLE_NAMES:
                    return mod, inp.identifier
    return None


class POINTCLOUD_PT_tools(POINTCLOUD_PT_base):
    bl_label = "Point Cloud Tools"
    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        scene = context.scene
        l = self.layout
        c = l.column()

        # --- Import a point cloud ---
        c.label(text="Import a PLY point cloud", icon='IMPORT')
        c.operator("import_scene.ply_pointcloud_geonodes", text="Import PLY Point Cloud", icon='IMPORT')
        c.separator()

        # --- Build a ground surface ---
        c.label(text="Build a ground surface from a point cloud", icon="MESH_GRID")
        c.label(text="Drapes a grid onto a PLY-style point cloud", icon='INFO')

        pc_obj = scene.roadway_source_object or (
            context.object if context.object and context.object.type == 'MESH' else None
        )
        if not scene.roadway_source_object:
            if pc_obj is not None:
                c.label(text=f"Source: {pc_obj.name} (active)", icon="OBJECT_DATA")
            else:
                c.label(text="Select a mesh point cloud, or set one below", icon='INFO')
        c.prop(scene, "roadway_source_object")

        # Expose the point cloud's GeoNodes display subsample, if it has one.
        sub = _geonodes_subsample_input(pc_obj)
        if sub is not None:
            mod, ident = sub
            try:
                c.prop(mod, '["%s"]' % ident, text="Points Visible %")
            except Exception:
                pass

        # --- Optional pre-filters (applied before surfacing) ---
        filt = c.box()
        filt.label(text="Pre-filter (optional)", icon='FILTER')
        filt.prop(scene, "roadway_subsample")
        if scene.roadway_subsample:
            filt.prop(scene, "roadway_voxel_size")
        filt.prop(scene, "roadway_sor")
        if scene.roadway_sor:
            filt.prop(scene, "roadway_sor_neighbors")
            filt.prop(scene, "roadway_sor_ratio")
        if scene.roadway_subsample or scene.roadway_sor:
            filt.prop(scene, "roadway_filter_in_place")
            filt.operator("object.filter_point_cloud", text="Apply Filters Only", icon='CHECKMARK')
            filt.label(text="Filters also run when creating the surface", icon='INFO')

        c.prop(scene, "roadway_cell_size")
        c.prop(scene, "roadway_ground_percentile")
        c.prop(scene, "roadway_fill_holes")
        if scene.roadway_fill_holes:
            c.prop(scene, "roadway_fill_distance")
        c.prop(scene, "roadway_transfer_color")
        if scene.roadway_transfer_color:
            c.prop(scene, "roadway_color_height_tol")
            c.prop(scene, "roadway_bake_texture")
            if scene.roadway_bake_texture:
                c.prop(scene, "roadway_texture_size")
                c.prop(scene, "roadway_texture_source_object")
                if not bpy.data.filepath:
                    c.label(text="Save the .blend to write the texture JPG", icon='ERROR')
            else:
                c.prop(scene, "roadway_create_material")

        c.operator("object.create_roadway_surface", text="Create Roadway Surface", icon='SURFACE_NSURFACE')
        c.label(text="Result is classified as Environment", icon='WORLD')


class POINTCLOUD_OT_open_user_guide(bpy.types.Operator):
    """Open the user guide in your web browser"""
    bl_idname = "point_cloud.open_user_guide"
    bl_label = "Open User Guide"

    _GITHUB_URL = "https://github.com/edccorp/hve_tools/blob/main/USER_GUIDE.md"

    def execute(self, context):
        import webbrowser
        webbrowser.open(self._GITHUB_URL)
        self.report({'INFO'}, "Opened the user guide.")
        return {'FINISHED'}


class POINTCLOUD_PT_documentation(POINTCLOUD_PT_base):
    bl_label = "Documentation"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        l = self.layout
        l.operator("point_cloud.open_user_guide", text="Open User Guide", icon='HELP')
        l.label(text="Opens the online guide in your browser.", icon='INFO')


classes = (
    POINTCLOUD_PT_tools,
    POINTCLOUD_PT_documentation,
    POINTCLOUD_OT_open_user_guide,
)


def register():
    pass

def unregister():
    pass
