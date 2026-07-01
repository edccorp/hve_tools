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


def test_fbx_importer_exposes_post_process_operators():
    # Import is now a thin step; post-processing is driven by explicit operators.
    assert "class FBX_OT_merge_body_mesh" in fbx_ui_source
    assert "class FBX_OT_reduce_shape_keys" in fbx_ui_source
    assert "class FBX_OT_apply_mesh_cleanup" in fbx_ui_source
    assert "class FBX_OT_process_all" in fbx_ui_source
    assert "import_hve.process_all" in fbx_ui_source
    # The FBX -> USD round-trip and MDD deformation storage have been removed.
    assert "import_via_usd" not in fbx_ui_source
    assert "deformation_storage" not in fbx_ui_source
    assert "roundtrip_imported_objects_through_usd" not in fbx_importer_source
    assert "convert_fbx_to_usd_in_background_blender" not in fbx_importer_source


def test_fbx_importer_file_browser_panel_has_no_inline_options():
    # The file browser draw is intentionally empty; the Include panel only labels the import.
    assert 'def draw(self, context):\n        pass' in fbx_ui_source
    assert 'layout.prop(operator, "import_via_usd")' not in fbx_ui_source
    assert 'layout.prop(operator, "merge_body_mesh")' not in fbx_ui_source
    assert 'layout.prop(operator, "deformation_storage")' not in fbx_ui_source
    assert 'layout.prop(operator, "apply_mesh_cleanup")' not in fbx_ui_source
    assert 'layout.prop(operator, "find_missing_files")' not in fbx_ui_source


def test_other_tools_child_panels_default_closed():
    for panel_name in (
        "HVE_PT_edr_importer",
        "HVE_PT_xyzrpy_importer",
        "HVE_PT_motion_paths",
        "HVE_PT_timed_location_markers",
        "HVE_PT_scale_objects",
        "HVE_PT_speed_acceleration",
        "HVE_PT_point_importer",
    ):
        start = ui_source.index(f"class {panel_name}")
        end = ui_source.find("\nclass ", start + 1)
        section = ui_source[start:end if end != -1 else len(ui_source)]
        assert 'bl_parent_id = "HVE_PT_other_tools"' in section
        assert "bl_options = {'DEFAULT_CLOSED'}" in section


def test_fbx_importer_reports_progress_to_blender_ui():
    assert "class BlenderImportProgress" in fbx_importer_source
    assert "progress_begin" in fbx_importer_source
    assert "progress_update" in fbx_importer_source
    assert "status_text_set" in fbx_importer_source
    assert "operator.report({'INFO'}" in fbx_importer_source
    # ImportFBX passes itself through load() so progress/errors surface in the UI.
    assert "operator=self" in fbx_ui_source
    assert "operator=operator" in fbx_importer_source
