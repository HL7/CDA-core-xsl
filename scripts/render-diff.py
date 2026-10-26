#!/usr/bin/env python3
"""
render-diff.py — Visual diff of CDA example renderings between branches.

Renders each example XML with both the current and base branch versions of
CDA.xsl, then produces two diff views:
  1. Structural side-by-side: blocks aligned by label, unchanged collapsed
  2. Text side-by-side: stripped-HTML text diff via difflib

Usage:
    python3 scripts/render-diff.py                    # diff vs origin/master
    python3 scripts/render-diff.py --base origin/main # diff vs specific ref
    python3 scripts/render-diff.py --open             # open results in browser

Requires: Python 3.8+, Java (for Saxon), lib/ dependencies (run run-tests.sh first).
lxml is installed automatically in a virtual environment on first run.
"""

import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure we're running inside a venv with lxml installed
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
VENV_DIR = SCRIPT_DIR / ".venv"

def _bootstrap_venv():
    """Create a venv and install lxml if needed, then re-exec this script inside it."""
    # Skip if lxml is already available (e.g., CI environment)
    try:
        import lxml  # noqa: F401
        return
    except ImportError:
        pass

    venv_python = VENV_DIR / "bin" / "python3"

    # Already inside our venv?
    if sys.prefix == str(VENV_DIR):
        return

    # Create venv if missing
    if not venv_python.exists():
        print("Setting up virtual environment (first run only)...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
        subprocess.check_call([str(venv_python), "-m", "pip", "install",
                               "--quiet", "lxml"])
        print()

    # Re-exec under the venv python
    os.execv(str(venv_python), [str(venv_python), __file__] + sys.argv[1:])

_bootstrap_venv()

# ---------------------------------------------------------------------------
# Real imports (lxml is now guaranteed available)
# ---------------------------------------------------------------------------
import argparse
import hashlib
import re
import shutil
import tempfile
from difflib import HtmlDiff, SequenceMatcher

from lxml import html, etree  # noqa: E402

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
LIB_DIR = REPO_ROOT / "lib"
EXAMPLES_DIR = REPO_ROOT / "examples"
OUTPUT_DIR = SCRIPT_DIR / "diffResults"

SAXON_VERSION = "12.5"
XMLRESOLVER_VERSION = "5.2.2"
SAXON_JAR = LIB_DIR / f"saxon-he-{SAXON_VERSION}.jar"
XMLRESOLVER_JAR = LIB_DIR / f"xmlresolver-{XMLRESOLVER_VERSION}.jar"
XMLRESOLVER_DATA_JAR = LIB_DIR / f"xmlresolver-{XMLRESOLVER_VERSION}-data.jar"
SAXON_CP = f"{SAXON_JAR}:{XMLRESOLVER_JAR}:{XMLRESOLVER_DATA_JAR}"

XSL_FILE = "CDA.xsl"
SUPPORT_FILES = ["cda_l10n.xml", "cda_narrativeblock.xml"]


def check_prereqs():
    """Verify Java and Saxon are available."""
    if not shutil.which("java"):
        print("Error: Java is required but not found in PATH.", file=sys.stderr)
        sys.exit(1)
    if not SAXON_JAR.exists():
        print(f"Error: {SAXON_JAR} not found. Run ./run-tests.sh first to download dependencies.",
              file=sys.stderr)
        sys.exit(1)


def git_ref_label(base_ref: str) -> str:
    """Get a human-readable label for a git ref."""
    try:
        short = subprocess.check_output(
            ["git", "rev-parse", "--short", base_ref],
            cwd=REPO_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
        return f"{base_ref} ({short})"
    except subprocess.CalledProcessError:
        return base_ref


def current_branch_label() -> str:
    """Get label for the current working tree."""
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=REPO_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
        short = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
        dirty = subprocess.call(
            ["git", "diff", "--quiet"], cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ) != 0
        label = f"{branch} ({short})"
        if dirty:
            label += " + uncommitted changes"
        return label
    except subprocess.CalledProcessError:
        return "local"


# ---------------------------------------------------------------------------
# Git / rendering helpers
# ---------------------------------------------------------------------------
def export_base_files(base_ref: str, tmpdir: str):
    """Export XSL and support files from the base ref into tmpdir."""
    for filename in [XSL_FILE] + SUPPORT_FILES:
        content = subprocess.check_output(
            ["git", "show", f"{base_ref}:{filename}"],
            cwd=REPO_ROOT
        )
        with open(os.path.join(tmpdir, filename), "wb") as f:
            f.write(content)


def export_base_example(base_ref: str, xml_name: str, tmpdir: str) -> bool:
    """Export an example XML from the base ref. Returns False if it doesn't exist."""
    try:
        content = subprocess.check_output(
            ["git", "show", f"{base_ref}:examples/{xml_name}"],
            cwd=REPO_ROOT, stderr=subprocess.DEVNULL
        )
        with open(os.path.join(tmpdir, xml_name), "wb") as f:
            f.write(content)
        return True
    except subprocess.CalledProcessError:
        return False


def render_xml(xml_path: str, xsl_path: str, output_path: str) -> bool:
    """Render an XML file with Saxon. Returns True on success."""
    result = subprocess.run(
        ["java", "-cp", SAXON_CP, "net.sf.saxon.Transform",
         f"-s:{xml_path}", f"-xsl:{xsl_path}", f"-o:{output_path}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  Warning: Saxon failed for {xml_path}: {result.stderr[:200]}", file=sys.stderr)
        return False
    return True


# ---------------------------------------------------------------------------
# Diff logic
# ---------------------------------------------------------------------------
def serialize(elem):
    return etree.tostring(elem, encoding="unicode", method="html")


def ws_normalize(s):
    return re.sub(r"\s+", " ", s).strip()


def fingerprint(elem):
    return hashlib.md5(ws_normalize(serialize(elem)).encode()).hexdigest()


def block_label(elem):
    """Extract semantic label from a block for alignment."""
    for cls in ("td_label td_label_width", "td_label"):
        label_td = elem.find(f'.//*[@class="{cls}"]')
        if label_td is not None:
            t = ws_normalize(label_td.text_content())[:60]
            if t:
                return t
    for tag in ("h1", "h2", "h3", "h4"):
        h = elem.find(f".//{tag}")
        if h is not None:
            return ws_normalize(h.text_content())[:60]
    cls = elem.get("class", "")
    eid = elem.get("id", "")
    if cls or eid:
        return f"{elem.tag}.{cls or eid}"
    return ws_normalize(elem.text_content())[:40]


def get_blocks(body):
    """Extract sub-blocks from body, flattening major sections."""
    blocks = []
    for child in body:
        if child.tag in ("script", "style"):
            continue
        eid = child.get("id", "")
        if eid in ("documentheader", "documentbody", "documentfooter", "buttontable"):
            for sub in child:
                if sub.tag in ("script", "style"):
                    continue
                blocks.append((eid, sub))
        else:
            blocks.append(("", child))
    return blocks


def tokenize_html(html_str):
    """Split HTML into tags and word tokens."""
    tokens = []
    for m in re.finditer(r"(<[^>]+>)|([^<]+)", html_str):
        tag, text = m.groups()
        if tag:
            tokens.append(tag)
        elif text:
            tokens.extend(re.findall(r"\S+|\s+", text))
    return tokens


def highlight_diff(old_html, new_html):
    """Produce two HTML strings with intra-block change highlighting."""
    old_tokens = tokenize_html(old_html)
    new_tokens = tokenize_html(new_html)
    sm = SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
    old_out, new_out = [], []

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            old_out.extend(old_tokens[i1:i2])
            new_out.extend(new_tokens[j1:j2])
        elif op == "replace":
            old_chunk = "".join(old_tokens[i1:i2])
            new_chunk = "".join(new_tokens[j1:j2])
            if not old_chunk.startswith("<"):
                old_out.append(f'<span class="hl-del">{old_chunk}</span>')
            else:
                old_out.append(old_chunk)
            if not new_chunk.startswith("<"):
                new_out.append(f'<span class="hl-add">{new_chunk}</span>')
            else:
                new_out.append(new_chunk)
        elif op == "delete":
            chunk = "".join(old_tokens[i1:i2])
            if not chunk.startswith("<"):
                old_out.append(f'<span class="hl-del">{chunk}</span>')
            else:
                old_out.append(chunk)
        elif op == "insert":
            chunk = "".join(new_tokens[j1:j2])
            if not chunk.startswith("<"):
                new_out.append(f'<span class="hl-add">{chunk}</span>')
            else:
                new_out.append(chunk)

    return "".join(old_out), "".join(new_out)


# ---------------------------------------------------------------------------
# Structural diff (side-by-side rendered blocks)
# ---------------------------------------------------------------------------
def generate_structural_diff(old_html: str, new_html: str,
                             base_label: str, current_label: str,
                             example_name: str) -> str:
    """Generate the structural side-by-side diff HTML."""
    old_doc = html.fromstring(old_html.encode() if isinstance(old_html, str) else old_html)
    new_doc = html.fromstring(new_html.encode() if isinstance(new_html, str) else new_html)

    # Extract CSS from the new rendering
    styles = re.findall(r"<style[^>]*>.*?</style>", new_html, re.DOTALL)
    css_blocks = "\n".join(styles)

    old_body = old_doc.find(".//body")
    new_body = new_doc.find(".//body")

    old_blocks = get_blocks(old_body)
    new_blocks = get_blocks(new_body)

    old_fps = [fingerprint(b[1]) for b in old_blocks]
    new_fps = [fingerprint(b[1]) for b in new_blocks]

    old_struct = [(b[0], block_label(b[1])) for b in old_blocks]
    new_struct = [(b[0], block_label(b[1])) for b in new_blocks]

    sm = SequenceMatcher(None, old_struct, new_struct, autojunk=False)
    pairs = []

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                pairs.append((old_blocks[i], new_blocks[j], old_fps[i] == new_fps[j]))
        elif op == "replace":
            oi, nj = i1, j1
            while oi < i2 and nj < j2:
                pairs.append((old_blocks[oi], new_blocks[nj], False))
                oi += 1; nj += 1
            while oi < i2:
                pairs.append((old_blocks[oi], None, False)); oi += 1
            while nj < j2:
                pairs.append((None, new_blocks[nj], False)); nj += 1
        elif op == "delete":
            for i in range(i1, i2):
                pairs.append((old_blocks[i], None, False))
        elif op == "insert":
            for j in range(j1, j2):
                pairs.append((None, new_blocks[j], False))

    # Build rows
    rows = []
    unchanged_buf = 0
    current_section = ""
    section_labels = {
        "documentheader": "📋 Header", "buttontable": "📑 Table of Contents",
        "documentbody": "📄 Document Body", "documentfooter": "📝 Footer",
    }

    for old_b, new_b, is_same in pairs:
        section = (new_b or old_b)[0]
        if section != current_section:
            if unchanged_buf > 0:
                rows.append(f'<tr class="collapsed-row"><td colspan="2" class="collapsed">'
                            f'⋯ {unchanged_buf} unchanged block{"s" if unchanged_buf != 1 else ""} ⋯</td></tr>')
                unchanged_buf = 0
            current_section = section
            label = section_labels.get(section, section)
            rows.append(f'<tr><td colspan="2" class="section-header">{label}</td></tr>')

        if is_same:
            unchanged_buf += 1
            continue

        if unchanged_buf > 0:
            rows.append(f'<tr class="collapsed-row"><td colspan="2" class="collapsed">'
                        f'⋯ {unchanged_buf} unchanged block{"s" if unchanged_buf != 1 else ""} ⋯</td></tr>')
            unchanged_buf = 0

        if old_b and new_b:
            old_c, new_c = highlight_diff(serialize(old_b[1]), serialize(new_b[1]))
        else:
            old_c = serialize(old_b[1]) if old_b else '<div class="empty-block">(not present)</div>'
            new_c = serialize(new_b[1]) if new_b else '<div class="empty-block">(not present)</div>'

        rows.append(f'<tr class="diff-row"><td class="diff-old">{old_c}</td>'
                    f'<td class="diff-new">{new_c}</td></tr>')

    if unchanged_buf > 0:
        rows.append(f'<tr class="collapsed-row"><td colspan="2" class="collapsed">'
                    f'⋯ {unchanged_buf} unchanged block{"s" if unchanged_buf != 1 else ""} ⋯</td></tr>')

    diff_count = sum(1 for _, _, s in pairs if not s)
    same_count = sum(1 for _, _, s in pairs if s)

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{example_name} - Structural Diff</title>
{css_blocks}
<style>
    body {{ margin: 0; padding: 0; color: #003366; }}
    .diff-legend {{
        position: sticky; top: 0; z-index: 100;
        background: #fff; padding: 10px 20px;
        border-bottom: 2px solid #ccc;
        font-family: -apple-system, sans-serif; font-size: 11pt;
    }}
    .diff-legend .swatch {{
        display: inline-block; padding: 2px 8px; margin: 0 4px;
        border-radius: 3px; font-size: 9pt;
    }}
    .diff-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    .diff-table > tbody > tr > td {{
        vertical-align: top; padding: 6px 12px;
        border: 1px solid #ddd; width: 50%; overflow: hidden;
    }}
    .diff-old {{ background-color: #fff8f8; border-left: 3px solid #e8a0a0 !important; }}
    .diff-new {{ background-color: #f5fff5; border-left: 3px solid #7cb87c !important; }}
    .hl-del {{ background-color: #ffd7d5; padding: 1px 2px; border-radius: 2px; }}
    .hl-add {{ background-color: #acf2bd; padding: 1px 2px; border-radius: 2px; }}
    .collapsed {{
        text-align: center; padding: 4px; color: #bbb; font-style: italic;
        background: #fafafa; font-family: sans-serif; font-size: 9pt;
    }}
    .empty-block {{
        color: #ccc; font-style: italic; padding: 20px;
        font-family: sans-serif; text-align: center;
    }}
    .section-header {{
        background: #e0e4e8; font-family: -apple-system, sans-serif;
        font-weight: bold; font-size: 11pt; padding: 8px 12px;
        border-top: 2px solid #bbb;
    }}
    .col-header {{
        background: #f0f0f0; font-family: -apple-system, sans-serif;
        font-weight: bold; font-size: 10pt; padding: 8px 12px;
        text-align: center; position: sticky; top: 50px; z-index: 99;
    }}
    .diff-row table {{ border-collapse: collapse; }}
</style>
</head>
<body>
<div class="diff-legend">
    <strong>Structural Diff:</strong> {example_name} —
    {diff_count} changed region{"s" if diff_count != 1 else ""},
    {same_count} unchanged (collapsed)
    &nbsp;
    <span class="swatch" style="background:#ffd7d5;">removed</span>
    <span class="swatch" style="background:#acf2bd;">added</span>
    <span style="float: right; font-size: 9pt;"><a href="index.html">← Back to index</a></span>
    <br/>
    <span style="font-size: 9pt; color: #666;">Comparing <strong>{current_label}</strong> vs <strong>{base_label}</strong></span>
</div>
<table class="diff-table">
<tbody>
    <tr>
        <td class="col-header" style="border-right: 2px solid #ccc;">{base_label}</td>
        <td class="col-header">{current_label}</td>
    </tr>
    {"".join(rows)}
</tbody>
</table>
</body>
</html>'''


# ---------------------------------------------------------------------------
# Text diff (stripped-HTML side-by-side via difflib)
# ---------------------------------------------------------------------------
def generate_text_diff(old_html: str, new_html: str,
                       base_label: str, current_label: str,
                       example_name: str) -> str:
    """Generate the plain-text side-by-side diff HTML."""
    def strip_html(h):
        h = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", h, flags=re.DOTALL)
        h = re.sub(r"<(?:br|/p|/div|/tr|/li|/h[1-6])[^>]*>", "\n", h)
        h = re.sub(r"<[^>]+>", "", h)
        h = h.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        lines = [l.strip() for l in h.split("\n")]
        return [l for l in lines if l]

    old_lines = strip_html(old_html)
    new_lines = strip_html(new_html)

    differ = HtmlDiff(wrapcolumn=80)
    diff_html = differ.make_file(
        old_lines, new_lines,
        fromdesc=base_label, todesc=current_label,
        context=True, numlines=3
    )

    # Inject a header banner after <body>
    banner = f'''<div style="font-family: -apple-system, sans-serif; padding: 10px 20px;
                             border-bottom: 2px solid #ccc; margin-bottom: 10px; font-size: 11pt;">
        <strong>Text Diff:</strong> {example_name}
        <span style="float: right; font-size: 9pt;"><a href="index.html">&larr; Back to index</a></span>
        <br/>
        <span style="font-size: 9pt; color: #666;">Comparing <strong>{current_label}</strong> vs <strong>{base_label}</strong></span>
    </div>'''
    diff_html = diff_html.replace("<body>", f"<body>\n{banner}", 1)

    return diff_html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Visual diff of CDA example renderings.")
    parser.add_argument("--base", default=None,
                        help="Base git ref to compare against (default: auto-detect origin/master or origin/main)")
    parser.add_argument("--open", action="store_true",
                        help="Open results in the default browser")
    args = parser.parse_args()

    check_prereqs()

    # Auto-detect base ref
    if args.base:
        base_ref = args.base
    else:
        for candidate in ("origin/master", "origin/main"):
            try:
                subprocess.check_output(
                    ["git", "rev-parse", "--verify", candidate],
                    cwd=REPO_ROOT, stderr=subprocess.DEVNULL
                )
                base_ref = candidate
                break
            except subprocess.CalledProcessError:
                continue
        else:
            print("Error: Could not find origin/master or origin/main. Use --base to specify.", file=sys.stderr)
            sys.exit(1)

    base_label = git_ref_label(base_ref)
    curr_label = current_branch_label()

    print(f"Comparing: {curr_label}  vs  {base_label}")

    # Find example XMLs (exclude support files and viewer)
    example_xmls = sorted([
        f.name for f in EXAMPLES_DIR.glob("*.xml")
        if f.name not in ("cda_l10n.xml", "cda_narrativeblock.xml")
    ])

    if not example_xmls:
        print("No example XML files found in examples/")
        sys.exit(0)

    print(f"Examples: {', '.join(example_xmls)}")

    # Prepare output dir
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Export base branch files to temp dir
    with tempfile.TemporaryDirectory(prefix="cda-diff-base-") as base_dir:
        print(f"Exporting {base_ref} files...")
        export_base_files(base_ref, base_dir)

        generated = []

        for xml_name in example_xmls:
            basename = xml_name.replace(".xml", "")
            print(f"\n--- {xml_name} ---")

            # Export base example, or fall back to current branch's XML
            # (new examples still get diffed — same XML, different XSL)
            base_xml_path = os.path.join(base_dir, xml_name)
            if not export_base_example(base_ref, xml_name, base_dir):
                print(f"  {xml_name} is new (not in {base_ref}), using current XML with base XSL")
                shutil.copy(str(EXAMPLES_DIR / xml_name), base_xml_path)

            # Render with base XSL
            old_html_path = os.path.join(base_dir, f"{basename}-old.html")
            if not render_xml(
                base_xml_path,
                os.path.join(base_dir, XSL_FILE),
                old_html_path
            ):
                print(f"  Skipping: failed to render base version")
                continue

            # Render with current XSL
            new_html_path = os.path.join(base_dir, f"{basename}-new.html")
            if not render_xml(
                str(EXAMPLES_DIR / xml_name),
                str(REPO_ROOT / XSL_FILE),
                new_html_path
            ):
                print(f"  Skipping: failed to render current version")
                continue

            with open(old_html_path, "r", encoding="utf-8") as f:
                old_html = f.read()
            with open(new_html_path, "r", encoding="utf-8") as f:
                new_html = f.read()

            # Generate structural diff
            print(f"  Generating structural diff...")
            structural = generate_structural_diff(old_html, new_html, base_label, curr_label, basename)
            structural_path = OUTPUT_DIR / f"{basename}-diff-structural.html"
            structural_path.write_text(structural, encoding="utf-8")
            print(f"  → {structural_path.relative_to(REPO_ROOT)}")

            # Generate text diff
            print(f"  Generating text diff...")
            text = generate_text_diff(old_html, new_html, base_label, curr_label, basename)
            text_path = OUTPUT_DIR / f"{basename}-diff-text.html"
            text_path.write_text(text, encoding="utf-8")
            print(f"  → {text_path.relative_to(REPO_ROOT)}")

            generated.append((basename, structural_path, text_path))

        # Generate index page
        if generated:
            index_rows = ""
            first_file = generated[0][1].name
            for basename, sp, tp in generated:
                index_rows += f"""<tr>
                    <td>{basename}</td>
                    <td><a href="#" onclick="loadDiff('{sp.name}', this); return false;">Structural</a>
                        <a href="{sp.name}" target="_blank" class="newwin" title="Open in new tab">↗</a></td>
                    <td><a href="#" onclick="loadDiff('{tp.name}', this); return false;">Text</a>
                        <a href="{tp.name}" target="_blank" class="newwin" title="Open in new tab">↗</a></td>
                </tr>"""

            index_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Render Diffs</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, sans-serif; color: #333; display: flex; flex-direction: column; height: 100vh; }}
    .header {{ padding: 16px 20px; border-bottom: 1px solid #ddd; background: #fff; flex-shrink: 0; }}
    h1 {{ font-size: 16pt; margin-bottom: 6px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
    th, td {{ text-align: left; padding: 6px 12px; border-bottom: 1px solid #eee; }}
    th {{ background: #f6f8fa; font-size: 9.5pt; }}
    td {{ font-size: 9.5pt; }}
    a {{ color: #0366d6; cursor: pointer; }}
    a.active {{ font-weight: bold; background: #e8f0fe; padding: 2px 4px; border-radius: 3px; }}
    a.newwin {{ font-size: 8pt; color: #999; text-decoration: none; margin-left: 2px; }}
    a.newwin:hover {{ color: #0366d6; }}
    .meta {{ color: #666; font-size: 9pt; }}
    .disclaimer {{ color: #555; font-size: 9pt; background: #f8f8f0; border-left: 3px solid #ddd;
                    padding: 6px 12px; margin: 8px 0; line-height: 1.4; }}
    .viewer {{ flex: 1; border: none; border-top: 2px solid #ccc; }}
</style>
</head>
<body>
<div class="header">
    <h1>Render Diffs</h1>
    <p class="disclaimer">
        These diffs are auto-generated by rendering example CDA documents with both
        the released and updated versions of the stylesheet. They provide a useful approximation
        of visual changes but may not capture every difference — always review the rendered
        examples directly for a complete picture.
    </p>
    <div class="meta">
        Comparing <strong>{curr_label}</strong> vs <strong>{base_label}</strong>
    </div>
    <table>
        <thead><tr><th>Example</th><th>Structural Diff</th><th>Text Diff</th></tr></thead>
        <tbody>{index_rows}</tbody>
    </table>
</div>
<iframe id="viewer" class="viewer" src="{first_file}"></iframe>
<script>
    let activeLink = null;
    function loadDiff(url, el) {{
        document.getElementById('viewer').src = url;
        if (activeLink) activeLink.classList.remove('active');
        el.classList.add('active');
        activeLink = el;
    }}
    // Mark the first structural link as active on load
    document.querySelector('tbody a').classList.add('active');
    activeLink = document.querySelector('tbody a.active');
</script>
</body>
</html>"""
            index_path = OUTPUT_DIR / "index.html"
            index_path.write_text(index_html, encoding="utf-8")
            print(f"\nIndex: {index_path.relative_to(REPO_ROOT)}")

            if args.open:
                if sys.platform == "darwin":
                    subprocess.run(["open", str(index_path)])
                elif sys.platform == "win32":
                    os.startfile(str(index_path))
                else:
                    subprocess.run(["xdg-open", str(index_path)])

        print(f"\nDone. {len(generated)} example(s) processed.")


if __name__ == "__main__":
    main()
