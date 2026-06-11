import ast
import pathlib
from contextlib import contextmanager


module_path = pathlib.Path(__file__).resolve().parents[1] / "variableoutput_importer.py"
source = module_path.read_text()
module_ast = ast.parse(source)


def load_timing_namespace(fake_time):
    ns = {"contextmanager": contextmanager, "time": fake_time}
    for node in module_ast.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in {
            "ImportTimingReport",
            "timed_phase",
        }:
            code = compile(ast.Module([node], []), filename="<ast>", mode="exec")
            exec(code, ns)
    return ns


class FakeTime:
    def __init__(self, values):
        self.values = iter(values)

    def perf_counter(self):
        return next(self.values)


def test_variableoutput_timing_summary_uses_non_nested_phases(capsys):
    ns = load_timing_namespace(FakeTime([0.0, 1.0, 3.0, 3.0]))
    report = ns["ImportTimingReport"]()

    with report.phase("first phase"):
        pass

    report.print_summary()

    output = capsys.readouterr().out
    assert "first phase: 2.00s" in output
    assert "2.00s ( 66.7%)  first phase" in output
    assert "3.00s          total" in output


def test_variableoutput_load_does_not_wrap_child_import_timings():
    assert "read VariableOutput CSV and build import data" not in source
    assert 'timed_phase(timing_report, "read VariableOutput CSV")' in source
    assert 'timed_phase(timing_report, "build VariableOutput data arrays")' in source
