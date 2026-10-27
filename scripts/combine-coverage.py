#!/usr/bin/env python3
"""
combine-coverage.py — Combine multiple XSpec coverage reports into one.

Reads all *-coverage.html files from a directory, validates that they report
on the same source file with the same line structure, and produces a single
consolidated report. A line is marked as "hit" if ANY input report marks it
as hit. Lines hit only by supporting tests (not the primary/largest report)
are highlighted separately.

Usage:
    python3 scripts/combine-coverage.py                      # default: test/results
    python3 scripts/combine-coverage.py --dir path/to/results
    python3 scripts/combine-coverage.py --open               # open result in browser
    python3 scripts/combine-coverage.py --open --watch       # open and auto-regenerate on changes

The --watch flag monitors the source coverage files for changes and
regenerates the combined report automatically. Useful when iterating on
tests in Oxygen — re-run coverage there, and the combined report updates
within a few seconds. The browser tab just needs a refresh.

Output: <dir>/combined-coverage.html
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_DIR = REPO_ROOT / "test" / "results"


def parse_coverage_file(filepath):
    """Parse a coverage HTML file into structured data.
    
    Returns:
        header_html: everything before the <pre class="xspecCoverage"> block
        lines: list of (line_num, status, raw_html) tuples
            status is one of: 'hit', 'missed', 'ignored', 'unknown'
        footer_html: everything after the </pre> block
        totals: dict with 'hit', 'missed', 'unknown', 'lines' counts
        source_file: the module path from the report
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract source file path
    m = re.search(r'module:\s*([^<]+)', content)
    source_file = m.group(1).strip() if m else "unknown"

    # Extract totals
    m = re.search(r'hit:\s*(\d+)\s*/\s*missed:\s*(\d+)\s*/\s*unknown:\s*(\d+)', content)
    totals = {}
    if m:
        totals = {"hit": int(m.group(1)), "missed": int(m.group(2)), "unknown": int(m.group(3))}

    m = re.search(r'lines<br\s*/?>(\d+)', content)
    if m:
        totals["lines"] = int(m.group(1))

    # Split into header, coverage block, footer
    pre_match = re.search(r'(<pre class="xspecCoverage">)', content)
    pre_end = re.search(r'(</pre>)', content)
    
    if not pre_match or not pre_end:
        print(f"  Error: could not find coverage block in {filepath}", file=sys.stderr)
        sys.exit(1)

    header_html = content[:pre_match.start()]
    coverage_block = content[pre_match.end():pre_end.start()]
    footer_html = content[pre_end.end():]

    # Parse individual lines from the coverage block
    lines = []
    for line_match in re.finditer(
        r'^(\d+):\s*(.*?)$', coverage_block, re.MULTILINE
    ):
        line_num = int(line_match.group(1))
        line_html = line_match.group(2)

        # Determine status from ALL span classes on this line
        # A line with mixed statuses uses priority: hit > missed > unknown > ignored
        statuses = re.findall(
            r'class="(hit|missed|ignored|unknown)"', line_html
        )
        if not statuses:
            status = "ignored"
        elif "hit" in statuses:
            status = "hit"
        elif "missed" in statuses:
            status = "missed"
        elif "unknown" in statuses:
            status = "unknown"
        else:
            status = "ignored"
        lines.append((line_num, status, line_html))

    return header_html, lines, footer_html, totals, source_file


def validate_files(parsed_files):
    """Validate all files report on the same source with the same structure."""
    if not parsed_files:
        print("Error: no coverage files found.", file=sys.stderr)
        sys.exit(1)

    first_name, (_, first_lines, _, _, first_source) = parsed_files[0]
    first_line_nums = [l[0] for l in first_lines]
    errors = []

    for name, (_, lines, _, _, source) in parsed_files[1:]:
        line_nums = [l[0] for l in lines]
        if len(lines) != len(first_lines):
            errors.append(f"  {name}: {len(lines)} lines vs {len(first_lines)} in {first_name}")
        elif line_nums != first_line_nums:
            # Find first divergence
            for i, (a, b) in enumerate(zip(first_line_nums, line_nums)):
                if a != b:
                    errors.append(f"  {name}: line numbers diverge at position {i} ({a} vs {b})")
                    break

        # Check that the raw HTML content matches (ignoring status classes)
        for i, ((n1, _, html1), (n2, _, html2)) in enumerate(zip(first_lines, lines)):
            # Strip status classes for comparison
            clean1 = re.sub(r'class="(hit|missed|unknown)"', 'class="STATUS"', html1)
            clean2 = re.sub(r'class="(hit|missed|unknown)"', 'class="STATUS"', html2)
            if clean1 != clean2:
                errors.append(
                    f"  {name}: line {n1} content differs from {first_name} "
                    f"(possible stale report — regenerate coverage)"
                )
                break

    if errors:
        print("Error: coverage files are inconsistent:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)


def combine_coverage(parsed_files):
    """Combine coverage from all files. A line is 'hit' if hit in ANY file.
    
    Returns:
        combined_lines: list of (line_num, combined_status, raw_html, contributing_files)
        per_file_stats: dict of filename -> set of hit line numbers
    """
    first_name, (_, first_lines, _, _, _) = parsed_files[0]
    
    # Build per-file hit sets
    per_file_hits = {}
    for name, (_, lines, _, _, _) in parsed_files:
        per_file_hits[name] = set()
        for line_num, status, _ in lines:
            if status == "hit":
                per_file_hits[name].add(line_num)

    # Combine
    combined = []
    for line_num, base_status, raw_html in first_lines:
        if base_status == "ignored":
            combined.append((line_num, "ignored", raw_html, []))
            continue

        # Check all files for this line
        contributing = [
            name for name, hits in per_file_hits.items()
            if line_num in hits
        ]

        if contributing:
            combined_status = "hit"
        elif base_status == "unknown":
            # Check if any file has it as non-unknown
            any_known = False
            for name, (_, lines, _, _, _) in parsed_files:
                for ln, st, _ in lines:
                    if ln == line_num and st != "unknown":
                        any_known = True
                        break
                if any_known:
                    break
            combined_status = "missed" if any_known else "unknown"
        else:
            combined_status = "missed"

        combined.append((line_num, combined_status, raw_html, contributing))

    return combined, per_file_hits


def generate_report(parsed_files, combined_lines, per_file_hits, output_path):
    """Generate the combined coverage HTML report."""
    first_name, (header_html, _, footer_html, _, source_file) = parsed_files[0]
    file_names = [name for name, _ in parsed_files]

    # Calculate combined totals
    hit = sum(1 for _, s, _, _ in combined_lines if s == "hit")
    missed = sum(1 for _, s, _, _ in combined_lines if s == "missed")
    unknown = sum(1 for _, s, _, _ in combined_lines if s == "unknown")
    total_lines = len(combined_lines)

    # Identify primary file and count supporting-only hits
    primary_file = max(per_file_hits.keys(), key=lambda n: len(per_file_hits[n]))
    supporting_hit = sum(
        1 for _, s, _, contrib in combined_lines
        if s == "hit" and primary_file not in contrib
    )
    primary_hit = hit - supporting_hit

    # Modify the header: update title and totals
    header = header_html
    header = re.sub(
        r'<title>.*?</title>',
        '<title>Combined Test Coverage Report</title>',
        header
    )

    # Strip local filesystem paths by detecting the prefix from the source file
    # e.g. "/Users/benjamin/repos/CDA-core-xsl/CDA.xsl" → prefix is "/Users/benjamin/repos/CDA-core-xsl/"
    path_prefix = source_file.rsplit("CDA.xsl", 1)[0] if "CDA.xsl" in source_file else ""
    if path_prefix:
        header = header.replace(path_prefix, "")
        header = header.replace("file:" + path_prefix, "")

    # Replace the Stylesheet/XSpec lines with our combined source info
    source_names = ", ".join(f.replace("-coverage.html", ".xspec") for f in file_names)
    header = re.sub(
        r'<p>Stylesheet:.*?</p>\s*<p>XSpec:.*?</p>',
        f'<p>Stylesheet: CDA.xsl</p>\n      <p>Combined from: {source_names}</p>',
        header,
        flags=re.DOTALL
    )

    # Replace the entire thead with our custom version including supporting-hit column
    header = re.sub(
        r'<thead>.*?</thead>',
        f'''<thead>
            <tr>
               <th></th>
               <th></th>
               <th colspan="4" class="totals nodesHead">lines (combined)</th>
               <th></th>
            </tr>
            <tr>
               <th></th>
               <th class="totals">used</th>
               <th class="totals totals-hit">hit<br/>{primary_hit}</th>
               <th class="totals totals-supporting">supporting<br/>{supporting_hit}</th>
               <th class="totals totals-missed">missed<br/>{missed}</th>
               <th class="totals totals-unknown">unknown<br/>{unknown}</th>
               <th class="totals">lines<br/>{total_lines}</th>
            </tr>
        </thead>''',
        header,
        flags=re.DOTALL
    )

    # Update the summary row totals
    header = re.sub(
        r'(<th class="totals">)\d+(</th>\s*<th class="totals">)\d+(</th>\s*<th class="totals">)\d+',
        f'\\g<1>{primary_hit}</th><th class="totals">{supporting_hit}\\g<2>{missed}\\g<3>{unknown}',
        header
    )

    # Update the h2 summary
    header = re.sub(
        r'hit:\s*\d+\s*/\s*missed:\s*\d+\s*/\s*unknown:\s*\d+',
        f'hit: {primary_hit} / supporting: {supporting_hit} / missed: {missed} / unknown: {unknown}',
        header
    )

    # Add custom CSS for the combined report
    extra_css = """
<style type="text/css">
/* Combined coverage report styles */
.combined-info {
    font-family: -apple-system, sans-serif;
    padding: 10px 15px;
    margin: 10px 0;
    background: #f8f8f0;
    border-left: 3px solid #ddd;
    font-size: 9.5pt;
    line-height: 1.5;
}
.combined-info .source-list {
    margin: 5px 0 0 15px;
    font-size: 9pt;
    color: #555;
}
.combined-info .legend {
    margin-top: 8px;
    font-size: 9pt;
}
.combined-info .swatch {
    display: inline-block;
    padding: 1px 8px;
    margin-right: 10px;
    border-radius: 2px;
    font-size: 8.5pt;
}
/* Override XSpec's black-and-white theme */
.missed {
    background-color: #d32f2f !important;
    color: #fff !important;
    text-decoration: none !important;
}
.supporting-hit {
    background-color: #fff3cd !important;
    color: inherit !important;
    text-decoration: none !important;
}
.hit {
    background-color: transparent !important;
    color: inherit !important;
    text-decoration: none !important;
}
.unknown {
    background-color: #f0f0f0 !important;
    color: inherit !important;
    text-decoration: none !important;
}
/* Totals header colors */
.totals-hit { color: inherit; }
.totals-supporting { color: #856404; }
.totals-missed { color: #fff; background-color: #d32f2f; }
.totals-unknown { color: #888; }
</style>
"""
    header = header.replace('</head>', extra_css + '</head>')

    # Build source file list
    source_list = "\n".join(f"    <li>{name}</li>" for name in file_names)
    info_block = f"""
<div class="combined-info">
    <strong>Combined Coverage Report</strong> — merged from {len(file_names)} coverage file{"s" if len(file_names) != 1 else ""}:
    <ul class="source-list">
{source_list}
    </ul>
    A line is marked as <em>hit</em> if it was hit in <strong>any</strong> of the above reports.
    Lines hit only by supporting tests (not the primary <code>{primary_file}</code>) are highlighted in yellow.
</div>
"""

    # Build the coverage lines
    coverage_lines = []
    # Identify the primary file (most hits — typically the main coverage run)
    primary_file = max(per_file_hits.keys(), key=lambda n: len(per_file_hits[n]))
    all_files_set = set(file_names)

    for line_num, status, raw_html, contributing in combined_lines:
        # Rewrite the status classes in the raw HTML
        if status != "ignored":
            if status == "hit" and primary_file not in contributing and len(parsed_files) > 1:
                # Hit only by supporting tests, not the primary coverage run
                new_class = "supporting-hit"
            else:
                new_class = status
            # Replace all hit/missed/unknown classes on this line
            line_out = re.sub(
                r'class="(hit|missed|unknown)"',
                f'class="{new_class}"',
                raw_html
            )
        else:
            line_out = raw_html

        coverage_lines.append(f"{line_num:04d}: {line_out}")

    coverage_block = "\n".join(coverage_lines)

    # Assemble
    output = (
        header
        + info_block
        + '<pre class="xspecCoverage">'
        + coverage_block
        + "</pre>"
        + footer_html
    )

    output_path.write_text(output, encoding="utf-8")


def run_once(coverage_dir, verbose=True):
    """Run a single coverage combination. Returns output_path or None on error."""
    # Find all coverage HTML files
    coverage_files = sorted(coverage_dir.glob("*-coverage.html"))
    coverage_files = [f for f in coverage_files if f.name != "combined-coverage.html"]

    if not coverage_files:
        if verbose:
            print(f"No *-coverage.html files found in {coverage_dir}")
        return None

    if verbose:
        print(f"Found {len(coverage_files)} coverage file(s):")
        for f in coverage_files:
            print(f"  {f.name}")

    # Parse all files
    parsed = []
    for f in coverage_files:
        if verbose:
            print(f"  Parsing {f.name}...")
        parsed.append((f.name, parse_coverage_file(f)))

    # Validate consistency
    if verbose:
        print("Validating consistency...")
    validate_files(parsed)
    if verbose:
        print("  All files consistent.")

    # Combine
    if verbose:
        print("Combining coverage...")
    combined_lines, per_file_hits = combine_coverage(parsed)

    # Stats
    hit = sum(1 for _, s, _, _ in combined_lines if s == "hit")
    missed = sum(1 for _, s, _, _ in combined_lines if s == "missed")
    unknown = sum(1 for _, s, _, _ in combined_lines if s == "unknown")
    ignored = sum(1 for _, s, _, _ in combined_lines if s == "ignored")

    if verbose:
        print(f"  Combined: hit={hit}, missed={missed}, unknown={unknown}, ignored={ignored}")
        print(f"  Per file:")
        for name, hits in per_file_hits.items():
            print(f"    {name}: {len(hits)} hits")

        if len(parsed) > 1:
            primary_file = max(per_file_hits.keys(), key=lambda n: len(per_file_hits[n]))
            supporting = sum(
                1 for _, s, _, contrib in combined_lines
                if s == "hit" and primary_file not in contrib
            )
            print(f"  Primary file: {primary_file}")
            print(f"  Hit by supporting tests only: {supporting}")

    # Generate
    output_path = coverage_dir / "combined-coverage.html"
    if verbose:
        print(f"\nGenerating {output_path.relative_to(REPO_ROOT)}...")
    generate_report(parsed, combined_lines, per_file_hits, output_path)
    if verbose:
        print("Done.")

    return output_path, coverage_files


def get_mtimes(files):
    """Get a dict of file -> mtime for a list of paths."""
    return {f: f.stat().st_mtime for f in files if f.exists()}


def main():
    parser = argparse.ArgumentParser(description="Combine XSpec coverage reports.")
    parser.add_argument("--dir", default=str(DEFAULT_DIR),
                        help=f"Directory containing *-coverage.html files (default: {DEFAULT_DIR.relative_to(REPO_ROOT)})")
    parser.add_argument("--open", action="store_true",
                        help="Open the result in the default browser")
    parser.add_argument("--watch", action="store_true",
                        help="Watch source files and regenerate on changes")
    args = parser.parse_args()

    coverage_dir = Path(args.dir)
    if not coverage_dir.exists():
        print(f"Error: directory not found: {coverage_dir}", file=sys.stderr)
        sys.exit(1)

    result = run_once(coverage_dir)
    if result is None:
        sys.exit(0)

    output_path, coverage_files = result

    if args.open:
        if sys.platform == "darwin":
            subprocess.run(["open", str(output_path)])
        elif sys.platform == "win32":
            os.startfile(str(output_path))
        else:
            subprocess.run(["xdg-open", str(output_path)])

    if args.watch:
        import time
        print(f"\nWatching for changes (Ctrl+C to stop)...")
        last_mtimes = get_mtimes(coverage_files)
        try:
            while True:
                time.sleep(1)
                current_mtimes = get_mtimes(coverage_files)
                if current_mtimes != last_mtimes:
                    changed = [
                        f.name for f in coverage_files
                        if current_mtimes.get(f) != last_mtimes.get(f)
                    ]
                    print(f"\n--- {', '.join(changed)} changed, waiting for writes to finish... ---")
                    # Debounce: wait for files to stop changing
                    time.sleep(2)
                    last_mtimes = get_mtimes(coverage_files)
                    print("Regenerating...")
                    try:
                        run_once(coverage_dir, verbose=True)
                        print(f"\nWatching for changes (Ctrl+C to stop)...")
                    except SystemExit:
                        print("Error during regeneration (files may be inconsistent, retrying on next change)")
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
