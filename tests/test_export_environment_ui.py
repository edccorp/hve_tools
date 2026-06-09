import pathlib


ui_path = pathlib.Path(__file__).resolve().parents[1] / "export_environment_ui.py"
source = ui_path.read_text()


def test_environment_export_ui_hides_transform_controls():
    assert "class H3D_PT_export_environment_transform" not in source
    assert 'layout.prop(operator, "global_scale")' not in source
    assert 'layout.prop(operator, "axis_forward")' not in source
    assert 'layout.prop(operator, "axis_up")' not in source


def test_environment_export_ui_hides_apply_modifiers_control():
    assert "use_mesh_modifiers: BoolProperty" not in source
    assert 'layout.prop(operator, "use_mesh_modifiers")' not in source
