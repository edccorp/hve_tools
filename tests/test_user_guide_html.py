import importlib.util
import pathlib


REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "build_user_guide_html.py"
HTML = REPO / "docs" / "USER_GUIDE.html"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_user_guide_html", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_user_guide_html_is_in_sync_with_markdown():
    """The committed HTML must match a fresh render of USER_GUIDE.md.

    If this fails, run: python scripts/build_user_guide_html.py
    """
    builder = _load_builder()
    expected = builder.render_html()
    actual = HTML.read_text(encoding="utf-8")
    assert actual == expected, "docs/USER_GUIDE.html is stale; rerun scripts/build_user_guide_html.py"


def test_slug_matches_github_anchor_style():
    builder = _load_builder()
    assert builder.slug("4.1 Prepare objects for HVE export") == "41-prepare-objects-for-hve-export"
    assert builder.slug("Import survey / point data") == "import-survey--point-data"


def test_inline_handles_code_inside_links_and_escaping():
    builder = _load_builder()
    assert builder.inline("[`README.md`](README.md)") == '<a href="README.md"><code>README.md</code></a>'
    assert builder.inline("`SpeedData_<name>`") == "<code>SpeedData_&lt;name&gt;</code>"
    assert builder.inline("**bold**") == "<strong>bold</strong>"
