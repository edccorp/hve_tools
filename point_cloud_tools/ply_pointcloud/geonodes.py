import bpy

__all__ = ["make_geonodes_group", "assign_geonodes_modifier"]


def _set_group_radius_default_4x(ng, radius: float) -> None:
    """Best-effort set the 'Point Radius' default on Blender 4.x interface."""
    iface = getattr(ng, "interface", None)
    if not iface:
        return
    # Try items_tree first (4.x exposes a structured tree in most builds)
    items = []
    try:
        items = list(getattr(iface, "items_tree", []))
    except Exception:
        pass
    # Fallback: some minor builds allow iterating the interface directly
    if not items:
        try:
            items = list(iface)
        except Exception:
            items = []
    for item in items:
        try:
            if getattr(item, "in_out", "") == "INPUT" and getattr(item, "name", "") == "Point Radius":
                # Prefer direct default_value; fall back to nested socket.default_value
                try:
                    item.default_value = radius
                except Exception:
                    try:
                        if hasattr(item, "socket") and hasattr(item.socket, "default_value"):
                            item.socket.default_value = radius
                    except Exception:
                        pass
                break
        except Exception:
            # Be permissive; interface layout can vary across sub-versions.
            pass


def make_geonodes_group(name="PCD_View_Geo", radius=0.01, material=None, subsample_percent=100.0):
    """Create a Geometry Nodes group for displaying point clouds (3.6 & 4.x safe).

    ``subsample_percent`` sets the default of the display-only "Points
    Visible %" input: the percentage of points shown in the viewport. It never
    removes points from the mesh data.
    """
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    is_4 = bpy.app.version >= (4, 0, 0)

    # --- Interface Sockets ---
    if is_4:
        geo_in = ng.interface.new_socket(
            name="Geometry",
            socket_type="NodeSocketGeometry",
            in_out='INPUT',
        )
        rad_in = ng.interface.new_socket(
            name="Point Radius",
            socket_type="NodeSocketFloat",
            in_out='INPUT',
        )
        subsample_in = ng.interface.new_socket(
            name="Points Visible %",
            socket_type="NodeSocketFloat",
            in_out='INPUT',
        )
        try:
            # Set a sane default at the interface level
            if hasattr(rad_in, "default_value"):
                rad_in.default_value = radius
            elif hasattr(rad_in, "socket") and hasattr(rad_in.socket, "default_value"):
                rad_in.socket.default_value = radius
        except Exception:
            pass
        try:
            if hasattr(subsample_in, "default_value"):
                subsample_in.default_value = subsample_percent
            elif hasattr(subsample_in, "socket") and hasattr(subsample_in.socket, "default_value"):
                subsample_in.socket.default_value = subsample_percent
        except Exception:
            pass

        geo_out = ng.interface.new_socket(
            name="Geometry",
            socket_type="NodeSocketGeometry",
            in_out='OUTPUT',
        )
    else:
        # Blender 3.x
        gi_geo = ng.inputs.new('NodeSocketGeometry', 'Geometry')
        gi_rad = ng.inputs.new('NodeSocketFloat', 'Point Radius')
        gi_subsample = ng.inputs.new('NodeSocketFloat', 'Points Visible %')
        gi_rad.default_value = radius
        gi_subsample.default_value = subsample_percent
        go_geo = ng.outputs.new('NodeSocketGeometry', 'Geometry')

    # --- Nodes ---
    nodes = ng.nodes
    links = ng.links

    gi = nodes.new("NodeGroupInput")
    gi.location = (-800, 0)

    go = nodes.new("NodeGroupOutput")
    go.location = (700, 0)

    m2p = nodes.new("GeometryNodeMeshToPoints")
    m2p.mode = 'VERTICES'
    m2p.location = (-520, 0)

    # ✅ Link by NAME (reliable across 3.6/4.x), not by interface identifiers
    try:
        links.new(gi.outputs['Geometry'], m2p.inputs['Mesh'])
    except Exception:
        # Some very old builds use different capitalization; be defensive.
        for out_socket in gi.outputs:
            if out_socket.name.lower() == "geometry":
                links.new(out_socket, m2p.inputs['Mesh'])
                break

    # Point Radius input
    try:
        links.new(gi.outputs['Point Radius'], m2p.inputs['Radius'])
    except Exception:
        for out_socket in gi.outputs:
            if out_socket.name.lower().replace("_", " ") == "point radius":
                links.new(out_socket, m2p.inputs['Radius'])
                break

    random_value = nodes.new("FunctionNodeRandomValue")
    random_value.location = (-770, -220)
    try:
        random_value.data_type = 'FLOAT'
    except Exception:
        pass
    try:
        random_value.inputs['Min'].default_value = 0.0
        random_value.inputs['Max'].default_value = 100.0
    except Exception:
        pass

    less_than = nodes.new("FunctionNodeCompare")
    less_than.location = (-620, -220)
    try:
        less_than.data_type = 'FLOAT'
        less_than.operation = 'LESS_THAN'
    except Exception:
        pass

    try:
        links.new(random_value.outputs['Value'], less_than.inputs['A'])
    except Exception:
        pass
    try:
        links.new(gi.outputs['Points Visible %'], less_than.inputs['B'])
    except Exception:
        for out_socket in gi.outputs:
            if out_socket.name.lower().replace("_", " ") == "points visible %":
                try:
                    links.new(out_socket, less_than.inputs['B'])
                except Exception:
                    pass
                break
    try:
        links.new(less_than.outputs['Result'], m2p.inputs['Selection'])
    except Exception:
        pass

    p2v = nodes.new("GeometryNodePointsToVertices")
    p2v.location = (-520, -150)

    join = nodes.new("GeometryNodeJoinGeometry")
    join.location = (-200, 0)
    links.new(m2p.outputs['Points'], join.inputs['Geometry'])
    links.new(p2v.outputs['Mesh'], join.inputs['Geometry'])

    links.new(m2p.outputs['Points'], p2v.inputs['Points'])

    extrude = nodes.new("GeometryNodeExtrudeMesh")
    extrude.location = (0, 0)
    try:
        extrude.mode = 'VERTICES'
    except Exception:
        pass
    try:
        extrude.inputs['Offset Scale'].default_value = 0.0001
    except Exception:
        pass

    sm = nodes.new("GeometryNodeSetMaterial")
    sm.location = (220, 0)
    if material is not None:
        try:
            sm.inputs['Material'].default_value = material
        except Exception:
            pass

    links.new(join.outputs['Geometry'], extrude.inputs['Mesh'])
    links.new(extrude.outputs['Mesh'], sm.inputs['Geometry'])

    # Output geometry
    try:
        links.new(sm.outputs['Geometry'], go.inputs['Geometry'])
    except Exception:
        # Defensive fallback for name differences
        for out_socket in sm.outputs:
            if out_socket.name.lower() == "geometry":
                for in_socket in go.inputs:
                    if in_socket.name.lower() == "geometry":
                        links.new(out_socket, in_socket)
                        break
                break

    # On 4.x, ensure the interface default matches our desired radius
    if is_4:
        _set_group_radius_default_4x(ng, radius)

    return ng


def assign_geonodes_modifier(obj, ng, radius=0.01):
    """Attach the node group to the object as a Geometry Nodes modifier (3.6 & 4.x safe)."""
    # Remove existing modifier with the same name to avoid stale state
    existing = [m for m in obj.modifiers if m.type == 'NODES' and m.name == "PointCloud_View"]
    for m in existing:
        try:
            obj.modifiers.remove(m)
        except Exception:
            pass

    mod = obj.modifiers.new(name="PointCloud_View", type='NODES')
    mod.node_group = ng

    # Try to set the group input default cleanly
    if bpy.app.version >= (4, 0, 0):
        _set_group_radius_default_4x(ng, radius)
    else:
        # Blender 3.x: group inputs are directly accessible
        try:
            for inp in ng.inputs:
                if inp.name == 'Point Radius':
                    inp.default_value = radius
                    break
        except Exception:
            pass

    # Then set the modifier input value so users see the value on the stack immediately.
    if bpy.app.version >= (4, 0, 0):
        # Common key names for the 1st editable socket are "Input_2" or "Socket_2"
        set_ok = False
        for key in ("Input_2", "Socket_2"):
            try:
                mod[key] = radius
                set_ok = True
                break
            except Exception:
                pass
        if not set_ok:
            # As a last resort, try to find a float property key and set it.
            try:
                for k in getattr(mod, "keys", lambda: [])():
                    if isinstance(mod[k], (int, float)):
                        try:
                            mod[k] = radius
                            break
                        except Exception:
                            pass
            except Exception:
                pass
    else:
        # Blender 3.x modifier input mapping uses Input_{index+1}
        try:
            for i, inp in enumerate(mod.node_group.inputs):
                if inp.name == 'Point Radius':
                    key = f"Input_{i+1}"
                    try:
                        mod[key] = radius
                    except Exception:
                        pass
                    break
        except Exception:
            pass

    mod.show_in_editmode = True
    mod.show_on_cage = True

    # Force depsgraph update so the stack appears immediately
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    return mod
