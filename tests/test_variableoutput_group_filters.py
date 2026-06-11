import pathlib

repo = pathlib.Path(__file__).resolve().parents[1]
importer_source = (repo / "variableoutput_importer.py").read_text()
ui_source = (repo / "variableoutput_importer_ui.py").read_text()


def test_variableoutput_inspector_exposes_vehicle_and_group_ids():
    assert "def make_variable_group_id" in importer_source
    assert "def make_vehicle_id" in importer_source
    assert '"group_id": make_variable_group_id(vehicle_name, group_name)' in importer_source


def test_variableoutput_wheel_motion_variables_are_required():
    assert "REQUIRED_WHEEL_VARIABLES" in importer_source
    for variable in (
        "VehWheelx",
        "VehWheely",
        "VehWheelz",
        "VehWheelSpin",
        "VehWheelGamma",
        "VehWheelSteerDelta",
        "VehWheelDelta",
    ):
        assert f'"{variable}"' in importer_source
    assert "or variable in REQUIRED_WHEEL_VARIABLES" in importer_source


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


def test_variableoutput_disable_optional_also_disables_groups():
    assert "class IMPORT_VARIABLES_OT_disable_optional_variables" in ui_source
    assert "for item in operator.group_items:" in ui_source
    assert "item.enabled = False" in ui_source


def test_variableoutput_creation_toggles_are_exposed_and_passed_to_importer():
    for prop in (
        "create_tire_paths",
        "create_paths",
        "create_velocities",
        "create_accelerations",
        "create_forces",
    ):
        assert f"{prop}: BoolProperty" in ui_source
        assert f'creation_box.prop(operator, "{prop}")' in ui_source
        assert f"{prop}=True" in importer_source
        assert f"{prop}={prop}" in importer_source

    assert "if create_tire_paths:" in importer_source
    assert "if create_paths:" in importer_source
    assert "if create_velocities and 'VehKinematicVTotal'" in importer_source
    assert "if create_accelerations and 'VehKinematicAccTotal'" in importer_source
    assert "if create_forces and 'VehKineticFxImpact'" in importer_source


def test_add_vehicle_creation_toggle_defaults_are_import_safe():
    add_vehicle_signature = importer_source[
        importer_source.index("def add_vehicle(") : importer_source.index(
            "):", importer_source.index("def add_vehicle(")
        )
    ]

    assert "create_tire_paths=create_tire_paths" not in add_vehicle_signature
    assert "create_tire_paths=True" in add_vehicle_signature
    assert "create_paths=True" in add_vehicle_signature
    assert "create_velocities=True" in add_vehicle_signature
    assert "create_accelerations=True" in add_vehicle_signature
    assert "create_forces=True" in add_vehicle_signature


def test_variableoutput_group_toggle_cascades_to_variables():
    assert "update=_set_group_variables_enabled" in ui_source
    assert "def _set_group_variables_enabled" in ui_source
    assert "if variable_item.group_id != group_item.group_id" in ui_source
    assert "variable_item.enabled = True if variable_item.required else group_item.enabled" in ui_source


def test_variableoutput_scan_requires_selected_file():
    assert "def _variable_scan_path" in ui_source
    assert "os.path.isfile(filepath)" in ui_source
    assert "Select a VariableOutput .hvo or .csv file before scanning variables." in ui_source
    assert "self.clear_variable_list()" in ui_source
    assert "not os.path.isfile(filepath)" in importer_source
