import pathlib


ui_path = pathlib.Path(__file__).resolve().parents[1] / "hve_tools" / "export_environment_ui.py"
source = ui_path.read_text()


def test_environment_export_ui_keeps_transform_controls():
    assert "class H3D_PT_export_environment_transform" in source
    assert 'layout.prop(operator, "global_scale")' in source
    assert 'layout.prop(operator, "axis_forward")' in source
    assert 'layout.prop(operator, "axis_up")' in source


def test_environment_export_ui_bakes_user_scale_into_global_matrix():
    assert "Matrix.Scale(self.global_scale, 4)" in source
    assert "axis_conversion(to_forward=self.axis_forward" in source


def test_environment_export_ui_hides_apply_modifiers_control():
    assert "use_mesh_modifiers: BoolProperty" not in source
    assert 'layout.prop(operator, "use_mesh_modifiers")' not in source
