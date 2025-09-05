import ast
import math
import pathlib
import types
import re

module_path = pathlib.Path(__file__).resolve().parents[1] / "fbx_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)
ns = {"math": math, "re": re}
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name in {
        "materials_are_equal",
        "find_duplicate_materials_for_vehicle",
        "replace_materials_for_vehicle",
        "remove_unused_materials",
        "merge_duplicate_materials_per_vehicle",
        "belongs_to_vehicle",
    }:
        code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
        exec(code, ns)

materials_are_equal = ns["materials_are_equal"]
find_duplicate_materials_for_vehicle = ns["find_duplicate_materials_for_vehicle"]
replace_materials_for_vehicle = ns["replace_materials_for_vehicle"]
remove_unused_materials = ns["remove_unused_materials"]
merge_duplicate_materials_per_vehicle = ns["merge_duplicate_materials_per_vehicle"]
belongs_to_vehicle = ns["belongs_to_vehicle"]


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


class BpyModule:
    def __init__(self):
        self.data = BpyData()


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
    nodes1 = [principled_node(0.1, 0.9), texture_node("tex.png")]
    nodes2 = [principled_node(0.1, 0.9), texture_node("tex.png")]
    m1 = Material("meshMaterial0", (0.0, 0.0, 0.0, 1.0), nodes1)
    m2 = Material("meshMaterial1", (1.0, 1.0, 1.0, 1.0), nodes2)
    obj1 = Obj("Mesh: Car: Body", [m1])
    obj2 = Obj("Mesh: Car: Door", [m2])
    reset_bpy([m1, m2], [obj1, obj2])
    merge_duplicate_materials_per_vehicle(["Car"])
    assert obj1.material_slots[0].material is obj2.material_slots[0].material
    assert len(bpy.data.materials) == 1
