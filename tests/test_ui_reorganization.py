import pathlib

repo = pathlib.Path(__file__).resolve().parents[1]
ui_source = (repo / "ui.py").read_text()
props_source = (repo / "props.py").read_text()
init_source = (repo / "__init__.py").read_text()
materials_source = (repo / "materials.py").read_text()
racerender_ui_source = (repo / "racerender_exporter_ui.py").read_text()
fbx_ui_source = (repo / "fbx_importer_ui.py").read_text()
fbx_importer_source = (repo / "fbx_importer.py").read_text()


def test_object_type_enum_includes_gatb_surface():
    assert "('ENVIRONMENT', \"Environment\"" in props_source
    assert "('VEHICLE', \"Vehicle\"" in props_source
    assert "('GATB_SURFACE', \"GATB Surface\"" in props_source


def test_export_ui_uses_selected_object_types_and_warns_on_mixed_types():
    assert "get_selected_hve_type_counts(context)" in ui_source
    assert "Mixed HVE object types selected" in ui_source
    assert "hvetools.set_selected_hve_type" in ui_source
    assert "Export to HVE" in ui_source
    assert "Export GATB Surfaces" in ui_source
    assert "GATB Contact Surface Export" not in ui_source


def test_vehicle_lighting_is_hidden_for_mixed_selection():
    assert 'if enum_value == "VEHICLE" and not has_mixed_selection' in ui_source
    assert 'elif enum_value == "ENVIRONMENT" and not has_mixed_selection' in ui_source


def test_advanced_terrain_sections_default_collapsed():
    for prop_name in (
        "hve_setup_show_forces",
        "hve_setup_show_soil",
        "hve_setup_show_water",
    ):
        start = init_source.index(prop_name)
        section = init_source[start : start + 120]
        assert "default=False" in section


def test_material_ui_adds_all_material_sets_with_one_action():
    assert "class HVE_OT_AddAllMaterials" in materials_source
    assert "buildGenericMaterial(context.object, context.scene)" in materials_source
    assert "buildStandardMaterials(context.object, context.scene)" in materials_source
    assert "buildLightMaterials(context.object, context.scene)" in materials_source
    assert 'operator("hve_material.add_all_materials", text="Add Materials"' in ui_source


def test_racerender_ui_uses_converter_language():
    assert "RaceRender Converter" in ui_source
    assert "Convert HVE Output to RaceRender CSV" in racerender_ui_source
    assert "Convert HVE Variable Output to RaceRender CSV" in ui_source


def test_fbx_importer_exposes_body_merge_and_deformation_storage_options():
    assert "merge_body_mesh: BoolProperty" in fbx_ui_source
    assert "deformation_storage: EnumProperty" in fbx_ui_source
    assert '(\'SHAPE_KEYS\', "Shape Keys"' in fbx_ui_source
    assert '(\'MDD\', "External MDD File"' in fbx_ui_source
    assert "merge_body_mesh=merge_body_mesh" in fbx_importer_source
    assert "export_body_shape_key_animations_to_mdd" in fbx_importer_source
