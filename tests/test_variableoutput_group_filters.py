import pathlib

repo = pathlib.Path(__file__).resolve().parents[1]
importer_source = (repo / "variableoutput_importer.py").read_text()
ui_source = (repo / "variableoutput_importer_ui.py").read_text()


def test_variableoutput_inspector_exposes_vehicle_and_group_ids():
    assert "def make_variable_group_id" in importer_source
    assert "def make_vehicle_id" in importer_source
    assert '"group_id": make_variable_group_id(vehicle_name, group_name)' in importer_source


def test_variableoutput_importer_filters_disabled_groups_and_vehicles():
    assert "disabled_group_ids = parse_newline_delimited_ids(disabled_groups)" in importer_source
    assert "disabled_vehicle_ids = parse_newline_delimited_ids(disabled_vehicles)" in importer_source
    assert "make_vehicle_id(vehicle_name) in disabled_vehicle_ids" in importer_source
    assert "group_id in disabled_group_ids" in importer_source
    assert "disabled_groups=disabled_groups" in importer_source
    assert "disabled_vehicles=disabled_vehicles" in importer_source


def test_variableoutput_ui_has_group_and_vehicle_toggles():
    assert "class VariableOutputGroupItem" in ui_source
    assert "class VariableOutputVehicleItem" in ui_source
    assert "group_items: CollectionProperty(type=VariableOutputGroupItem)" in ui_source
    assert "vehicle_items: CollectionProperty(type=VariableOutputVehicleItem)" in ui_source
    assert 'vehicle_box.label(text="Vehicles")' in ui_source
    assert 'group_box.label(text="Groups (optional variables only)")' in ui_source
    assert "disabled_vehicles" in ui_source
    assert "disabled_groups" in ui_source
