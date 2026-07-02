import bpy


__all__ = ["make_point_material"]



def make_point_material(name, attr_name):
    """Create a material for displaying points using vertex colors.

    Parameters:
        name: Name for the new material.
        attr_name: Color attribute to read from the mesh.

    Returns:
        The newly created ``bpy.types.Material`` configured to use the
        attribute for both base color and emission.

    Blender:
        Requires Blender 3.6 or newer. Blender 4.0 removed the
        ``ShaderNodeAttribute`` node.  The node used to read the color
        attribute is selected based on the running Blender version.

    Side effects:
        Adds the material to ``bpy.data.materials`` and populates its node
        tree.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)

    version = tuple(getattr(getattr(bpy, "app", object()), "version", (0, 0, 0)))
    if version >= (4, 0, 0):
        # Blender 4.0+ uses dedicated shader nodes for attributes.
        attr = None
        for node_type in ("ShaderNodeVertexColor", "ShaderNodeColorAttribute"):
            try:
                attr = nt.nodes.new(node_type)
                break
            except RuntimeError:
                attr = None
        if attr is None:
            try:
                attr = nt.nodes.new("ShaderNodeAttribute")
                attr.attribute_name = attr_name
            except RuntimeError as exc:
                raise RuntimeError(
                    "Attribute nodes are unavailable; cannot create material"
                ) from exc
        else:
            if hasattr(attr, "layer_name"):
                attr.layer_name = attr_name
            elif "Name" in attr.inputs:
                attr.inputs["Name"].default_value = attr_name
    else:
        attr = nt.nodes.new("ShaderNodeAttribute")
        attr.attribute_name = attr_name

    attr.location = (-100, 0)
    color_out = attr.outputs.get('Color') or attr.outputs[0]
    nt.links.new(color_out, bsdf.inputs['Base Color'])

    # Leave emission unconnected and at zero strength so points show their base
    # colour under normal lighting rather than glowing.
    strength_input = bsdf.inputs.get("Emission Strength")
    if strength_input:
        strength_input.default_value = 0.0

    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat
