#!/usr/bin/env python3
"""Generate ``hve_tools/docs/USER_GUIDE.html`` from ``USER_GUIDE.md``.

The add-on ships a pre-built HTML copy of the user guide so the in-Blender
**Open User Guide** button can display it in a browser with proper formatting
(Blender has no Markdown viewer). ``USER_GUIDE.md`` is the single source of
truth; run this script after editing it:

    python scripts/build_user_guide_html.py

The converter is intentionally dependency-free and supports only the Markdown
subset used by the guide: headings, bold, inline code, links, tables,
blockquotes, ordered/unordered (and nested) lists, horizontal rules, and
paragraphs.
"""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(REPO_ROOT, "USER_GUIDE.md")
OUTPUT = os.path.join(REPO_ROOT, "hve_tools", "docs", "USER_GUIDE.html")


def slug(text):
    """Replicate GitHub's heading-anchor slug so in-page TOC links resolve."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return text.replace(" ", "-")


def inline(text):
    """Convert inline Markdown (escaping first, then code/bold/links)."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", text)
    text = re.sub(r"\*\*([^*]+?)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
        text,
    )
    return text


_LIST_RE = re.compile(r"^(\s*)(\d+\.|[-*])\s+(.*)$")


def _parse_list_items(block_lines):
    """Turn raw list lines into ``[indent, ordered, content]`` records."""
    items = []
    for line in block_lines:
        m = _LIST_RE.match(line)
        if m:
            indent = len(m.group(1))
            ordered = m.group(2).endswith(".")
            items.append([indent, ordered, m.group(3).strip()])
        elif items:
            # Continuation line for the previous item.
            items[-1][2] += " " + line.strip()
    return items


def _render_list(items, index, base_indent):
    ordered = items[index][1]
    tag = "ol" if ordered else "ul"
    parts = [f"<{tag}>"]
    while index < len(items):
        indent = items[index][0]
        if indent < base_indent:
            break
        if indent > base_indent:  # safety; nesting is consumed below
            break
        li = f"<li>{inline(items[index][2])}"
        index += 1
        if index < len(items) and items[index][0] > base_indent:
            child, index = _render_list(items, index, items[index][0])
            li += child
        parts.append(li + "</li>")
    parts.append(f"</{tag}>")
    return "\n".join(parts), index


def _render_table(lines):
    def cells(row):
        row = row.strip().strip("|")
        return [c.strip() for c in row.split("|")]

    header = cells(lines[0])
    out = ["<table>", "<thead><tr>"]
    out += [f"<th>{inline(c)}</th>" for c in header]
    out.append("</tr></thead>")
    out.append("<tbody>")
    for line in lines[2:]:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells(line)) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def render_blocks(md_text):
    lines = md_text.split("\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if re.match(r"^-{3,}$", stripped):
            out.append("<hr>")
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            out.append(f'<h{level} id="{slug(text)}">{inline(text)}</h{level}>')
            i += 1
            continue

        # Table: a "|" row followed by a separator row.
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\s*\|[-:\s|]+\|\s*$", lines[i + 1]):
            table = []
            while i < n and lines[i].strip().startswith("|"):
                table.append(lines[i])
                i += 1
            out.append(_render_table(table))
            continue

        if stripped.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>\n" + render_blocks("\n".join(quote)) + "\n</blockquote>")
            continue

        if _LIST_RE.match(line):
            block = []
            while i < n and lines[i].strip() != "":
                block.append(lines[i])
                i += 1
            items = _parse_list_items(block)
            html, _ = _render_list(items, 0, items[0][0])
            out.append(html)
            continue

        # Paragraph: consecutive plain lines.
        para = []
        while i < n and lines[i].strip() != "" and not re.match(r"^\s*(#{1,6}\s|>|-{3,}$|[-*]\s|\d+\.\s|\|)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
        else:
            i += 1

    return "\n".join(out)


CSS = """
:root { color-scheme: light dark; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6; max-width: 820px; margin: 0 auto; padding: 2rem 1.25rem 4rem;
  color: #1b1b1b; background: #ffffff;
}
h1, h2, h3, h4 { line-height: 1.25; margin-top: 2rem; }
h1 { font-size: 2rem; border-bottom: 2px solid #e2731b; padding-bottom: .3rem; }
h2 { font-size: 1.5rem; border-bottom: 1px solid #ddd; padding-bottom: .25rem; }
h3 { font-size: 1.2rem; }
a { color: #b85c00; text-decoration: none; }
a:hover { text-decoration: underline; }
code { background: #f2f2f2; padding: .12em .35em; border-radius: 4px; font-size: .9em;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; }
blockquote { border-left: 4px solid #e2731b; margin: 1rem 0; padding: .4rem 1rem;
  background: #fff7ef; color: #444; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #ddd; padding: .5rem .6rem; text-align: left; vertical-align: top; }
th { background: #f6f6f6; }
hr { border: none; border-top: 1px solid #e5e5e5; margin: 2rem 0; }
ul, ol { padding-left: 1.5rem; }
li { margin: .2rem 0; }
@media (prefers-color-scheme: dark) {
  body { color: #ddd; background: #1e1e1e; }
  th { background: #2a2a2a; } code { background: #2a2a2a; }
  th, td { border-color: #3a3a3a; } h2 { border-color: #333; }
  blockquote { background: #2a2117; color: #ccc; }
}
""".strip()


def render_html(md_text=None):
    """Return the full HTML document for the guide (reads USER_GUIDE.md by default)."""
    if md_text is None:
        with open(SOURCE, encoding="utf-8") as fh:
            md_text = fh.read()

    body = render_blocks(md_text)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>HVE Tools — User Guide</title>\n"
        f"<style>\n{CSS}\n</style>\n</head>\n<body>\n"
        "<!-- Generated from USER_GUIDE.md by scripts/build_user_guide_html.py. Do not edit directly. -->\n"
        f"{body}\n</body>\n</html>\n"
    )


def build():
    html = render_html()
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Wrote {OUTPUT} ({len(html)} bytes)")


if __name__ == "__main__":
    build()
