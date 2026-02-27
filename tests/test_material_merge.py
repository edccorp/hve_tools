import ast
import math
import pathlib
import types
import re

module_path = pathlib.Path(__file__).resolve().parents[1] / "fbx_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {"math": math, "re": re, "os": __import__("os")}
for node in module_ast.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "MATERIAL_NAME_PREFIXES":
                code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
                exec(code, ns)
    if isinstance(node, ast.FunctionDef) and node.name in {
        "_normalize_image_path",
        "_get_principled_node",
        "_get_linked_image_path",
        "_socket_value_signature",
        "_socket_default_value_signature",
        "_material_node_tree_signature",
        "materials_are_equal",
        "find_duplicate_materials_for_vehicle",
        "deduplicate_material_slots_for_vehicle",
        "replace_materials_for_vehicle",
        "remove_unused_materials",
        "merge_duplicate_materials_per_vehicle",
        "belongs_to_vehicle",
        "set_new_materials_metallic_zero",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

materials_are_equal = ns["materials_are_equal"]
find_duplicate_materials_for_vehicle = ns["find_duplicate_materials_for_vehicle"]
replace_materials_for_vehicle = ns["replace_materials_for_vehicle"]
remove_unused_materials = ns["remove_unused_materials"]
merge_duplicate_materials_per_vehicle = ns["merge_duplicate_materials_per_vehicle"]
belongs_to_vehicle = ns["belongs_to_vehicle"]
set_new_materials_metallic_zero = ns["set_new_materials_metallic_zero"]


class Image:
    def __init__(self, filepath):
        self.filepath = filepath


class Link:
    def __init__(self, to_socket):
        self.to_socket = to_socket


class Output:
    def __init__(self, links=None):
        self.links = links or []


class Node:
    def __init__(self, type_, image=None, inputs=None, outputs=None):
        self.type = type_
        self.image = image
        self.inputs = inputs or {}
        self.outputs = outputs or []


class NodeTree:
    def __init__(self, nodes):
        self.nodes = nodes


class Material:
    def __init__(self, name, diffuse_color, nodes):
        self.name = name
        self.diffuse_color = diffuse_color
        self.node_tree = NodeTree(nodes)
        self.users = 0
        self.use_nodes = True
        self.blend_method = "OPAQUE"
        self.use_backface_culling = False


class MaterialSlot:
    def __init__(self, material):
        self._material = None
        self.material = material

    @property
    def material(self):
        return self._material

    @material.setter
    def material(self, mat):
        if self._material:
            self._material.users -= 1
        self._material = mat
        mat.users += 1


class Obj:
    def __init__(self, name, materials):
        self.name = name
        self.type = "MESH"
        self.material_slots = [MaterialSlot(m) for m in materials]


class Materials(list):
    def remove(self, mat):
        super().remove(mat)


class BpyData:
    def __init__(self):
        self.objects = []
        self.materials = Materials()


class BpyPath:
    @staticmethod
    def abspath(filepath):
        return filepath


class BpyModule:
    def __init__(self):
        self.data = BpyData()
        self.path = BpyPath()


bpy = BpyModule()
ns["bpy"] = bpy


def principled_node(roughness, specular):
    return Node(
        "BSDF_PRINCIPLED",
        inputs={
            "Roughness": types.SimpleNamespace(default_value=roughness),
            "Specular": types.SimpleNamespace(default_value=specular),
        },
    )


def texture_node(path):
    base_socket = types.SimpleNamespace(name="Base Color")
    return Node(
        "TEX_IMAGE",
        image=Image(path),
        outputs=[Output([Link(base_socket)])],
    )


def reset_bpy(materials, objects):
    bpy.data.materials[:] = materials
    bpy.data.objects[:] = objects


def test_merge_by_color_and_properties():
    m1 = Material("meshMaterial0", (1.0, 0.5, 0.0, 1.0), [principled_node(0.5, 0.2)])
    m2 = Material("meshMaterial1", (1.0, 0.5, 0.0, 1.0), [principled_node(0.5, 0.2)])
    obj1 = Obj("Mesh: Car: Body", [m1])
    obj2 = Obj("Mesh: Car: Door", [m2])
    reset_bpy([m1, m2], [obj1, obj2])
    merge_duplicate_materials_per_vehicle(["Car"])
    assert obj1.material_slots[0].material is obj2.material_slots[0].material
    assert len(bpy.data.materials) == 1


def test_merge_by_texture():
    principled1 = principled_node(0.1, 0.9)
    texture1 = Node("TEX_IMAGE", image=Image("tex.png"))
    principled1.inputs["Base Color"] = types.SimpleNamespace(links=[types.SimpleNamespace(from_node=texture1)])

    principled2 = principled_node(0.1, 0.9)
    texture2 = Node("TEX_IMAGE", image=Image("tex.png"))
    principled2.inputs["Base Color"] = types.SimpleNamespace(links=[types.SimpleNamespace(from_node=texture2)])

    m1 = Material("meshMaterial0", (0.0, 0.0, 0.0, 1.0), [principled1, texture1])
    m2 = Material("meshMaterial1", (0.0, 0.0, 0.0, 1.0), [principled2, texture2])
    obj1 = Obj("Mesh: Car: Body", [m1])
    obj2 = Obj("Mesh: Car: Door", [m2])
    reset_bpy([m1, m2], [obj1, obj2])
    merge_duplicate_materials_per_vehicle(["Car"])
    assert obj1.material_slots[0].material is obj2.material_slots[0].material
    assert len(bpy.data.materials) == 1




def test_do_not_merge_when_unchecked_principled_inputs_differ():
    principled1 = principled_node(0.3, 0.5)
    principled1.inputs["Transmission Weight"] = types.SimpleNamespace(default_value=0.0, links=[])

    principled2 = principled_node(0.3, 0.5)
    principled2.inputs["Transmission Weight"] = types.SimpleNamespace(default_value=0.8, links=[])

    m1 = Material("meshMaterial0", (0.2, 0.2, 0.2, 1.0), [principled1])
    m2 = Material("meshMaterial1", (0.2, 0.2, 0.2, 1.0), [principled2])
    obj1 = Obj("Mesh: Car: Body", [m1])
    obj2 = Obj("Mesh: Car: Door", [m2])
    reset_bpy([m1, m2], [obj1, obj2])

    merge_duplicate_materials_per_vehicle(["Car"])

    assert obj1.material_slots[0].material is not obj2.material_slots[0].material
    assert len(bpy.data.materials) == 2



def test_do_not_merge_when_texture_node_settings_differ():
    principled1 = principled_node(0.3, 0.5)
    texture1 = Node("TEX_IMAGE", image=Image("paint.png"))
    texture1.interpolation = "Linear"
    texture1.projection = "FLAT"
    texture1.extension = "REPEAT"
    principled1.inputs["Transmission Weight"] = types.SimpleNamespace(
        links=[types.SimpleNamespace(from_node=texture1, from_socket=types.SimpleNamespace(name="Color"))]
    )

    principled2 = principled_node(0.3, 0.5)
    texture2 = Node("TEX_IMAGE", image=Image("paint.png"))
    texture2.interpolation = "Closest"
    texture2.projection = "FLAT"
    texture2.extension = "REPEAT"
    principled2.inputs["Transmission Weight"] = types.SimpleNamespace(
        links=[types.SimpleNamespace(from_node=texture2, from_socket=types.SimpleNamespace(name="Color"))]
    )

    m1 = Material("meshMaterial0", (0.2, 0.2, 0.2, 1.0), [principled1, texture1])
    m2 = Material("meshMaterial1", (0.2, 0.2, 0.2, 1.0), [principled2, texture2])
    obj1 = Obj("Mesh: Car: Body", [m1])
    obj2 = Obj("Mesh: Car: Door", [m2])
    reset_bpy([m1, m2], [obj1, obj2])

    merge_duplicate_materials_per_vehicle(["Car"])

    assert obj1.material_slots[0].material is not obj2.material_slots[0].material
    assert len(bpy.data.materials) == 2

def test_deduplicate_material_slots_within_object():
    m1 = Material("meshMaterial0", (1.0, 0.0, 0.0, 1.0), [principled_node(0.4, 0.5)])
    m2 = Material("meshMaterial1", (1.0, 0.0, 0.0, 1.0), [principled_node(0.4, 0.5)])
    obj = Obj("Mesh: Car: Body", [m1, m2])
    reset_bpy([m1, m2], [obj])

    merge_duplicate_materials_per_vehicle(["Car"])

    assert len(obj.material_slots) == 1
    assert len(bpy.data.materials) == 1


def test_set_new_materials_metallic_zero_updates_principled_nodes_only():
    metallic_socket = types.SimpleNamespace(default_value=0.73)
    roughness_socket = types.SimpleNamespace(default_value=0.42)
    principled = Node(
        "BSDF_PRINCIPLED",
        inputs={
            "Metallic": metallic_socket,
            "Roughness": roughness_socket,
        },
    )
    non_principled = Node("EMISSION", inputs={"Metallic": types.SimpleNamespace(default_value=0.99)})

    mat_with_principled = Material("meshMaterial0", (1, 1, 1, 1), [principled, non_principled])
    mat_without_tree = types.SimpleNamespace(node_tree=None)

    set_new_materials_metallic_zero([mat_with_principled, mat_without_tree])

    assert metallic_socket.default_value == 0.0
    assert roughness_socket.default_value == 0.42
    assert non_principled.inputs["Metallic"].default_value == 0.99
