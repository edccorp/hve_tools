import pathlib


repo = pathlib.Path(__file__).resolve().parents[1]
fbx_ui_source = (repo / "fbx_importer_ui.py").read_text()
fbx_importer_source = (repo / "fbx_importer.py").read_text()


def test_fbx_deformation_storage_defaults_to_mdd_cache():
    assert "default='MDD'" in fbx_ui_source
    assert 'deformation_storage="MDD"' in fbx_importer_source


def test_fbx_mdd_conversion_runs_without_requiring_body_merge():
    mdd_branch = fbx_importer_source[fbx_importer_source.index('if deformation_storage == "MDD"') :]
    shape_key_branch = fbx_importer_source[fbx_importer_source.index('elif deformation_storage == "SHAPE_KEYS"') :]

    assert "export_body_shape_key_animations_to_mdd" in mdd_branch[:300]
    assert 'and merge_body_mesh' not in mdd_branch[:120]
    assert 'and merge_body_mesh' in shape_key_branch[:120]
