#!/usr/bin/env bash
# Run XSpec unit tests and example regression tests for CDA.xsl
#
# Usage:
#   ./run-tests.sh              # Run all validation + unit tests + regression tests
#   ./run-tests.sh test/X.xspec # Run only the specified XSpec file(s)
#   ./run-tests.sh --xspec      # Run only the XSpec unit tests
#   ./run-tests.sh --examples   # Run only the example regression tests
#   ./run-tests.sh --validate   # Run only the validation checks
#   ./run-tests.sh --update     # Regenerate the golden HTML files in examples/
#
# Dependencies are automatically downloaded on first run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/lib"
EXAMPLES_DIR="${SCRIPT_DIR}/examples"

# Dependency versions
SAXON_VERSION="12.5"
XMLRESOLVER_VERSION="5.2.2"
XSPEC_REPO="https://github.com/xspec/xspec.git"

# Derived paths
SAXON_JAR="${LIB_DIR}/saxon-he-${SAXON_VERSION}.jar"
XMLRESOLVER_JAR="${LIB_DIR}/xmlresolver-${XMLRESOLVER_VERSION}.jar"
XMLRESOLVER_DATA_JAR="${LIB_DIR}/xmlresolver-${XMLRESOLVER_VERSION}-data.jar"
XSPEC_SH="${LIB_DIR}/xspec/bin/xspec.sh"
SAXON_CP="${SAXON_JAR}:${XMLRESOLVER_JAR}:${XMLRESOLVER_DATA_JAR}"

# ---------------------------------------------------------------------------
# Check for Java
# ---------------------------------------------------------------------------
if ! command -v java &>/dev/null; then
    echo "ERROR: Java is required but not found on PATH."
    echo "  Install Java 11+ from one of:"
    echo "    Amazon Corretto: https://aws.amazon.com/corretto/"
    echo "    Eclipse Temurin: https://adoptium.net/"
    echo "    Oracle JDK:      https://www.oracle.com/java/technologies/downloads/"
    exit 1
fi

# ---------------------------------------------------------------------------
# Auto-install missing dependencies
# ---------------------------------------------------------------------------
install_deps() {
    local needed=false

    if [[ ! -f "$SAXON_JAR" ]] || [[ ! -f "$XMLRESOLVER_JAR" ]] || [[ ! -f "$XMLRESOLVER_DATA_JAR" ]] || [[ ! -x "$XSPEC_SH" ]]; then
        needed=true
    fi

    if [[ "$needed" == false ]]; then
        return
    fi

    echo "Installing missing test dependencies into lib/..."
    mkdir -p "$LIB_DIR"

    if [[ ! -f "$SAXON_JAR" ]]; then
        echo "  Downloading Saxon HE ${SAXON_VERSION}..."
        curl -sSL -o "$SAXON_JAR" \
            "https://repo1.maven.org/maven2/net/sf/saxon/Saxon-HE/${SAXON_VERSION}/Saxon-HE-${SAXON_VERSION}.jar"
    fi

    if [[ ! -f "$XMLRESOLVER_JAR" ]]; then
        echo "  Downloading XML Resolver ${XMLRESOLVER_VERSION}..."
        curl -sSL -o "$XMLRESOLVER_JAR" \
            "https://repo1.maven.org/maven2/org/xmlresolver/xmlresolver/${XMLRESOLVER_VERSION}/xmlresolver-${XMLRESOLVER_VERSION}.jar"
    fi

    if [[ ! -f "$XMLRESOLVER_DATA_JAR" ]]; then
        echo "  Downloading XML Resolver ${XMLRESOLVER_VERSION} data..."
        curl -sSL -o "$XMLRESOLVER_DATA_JAR" \
            "https://repo1.maven.org/maven2/org/xmlresolver/xmlresolver/${XMLRESOLVER_VERSION}/xmlresolver-${XMLRESOLVER_VERSION}-data.jar"
    fi

    if [[ ! -d "${LIB_DIR}/xspec" ]]; then
        echo "  Cloning XSpec..."
        git clone --depth 1 "$XSPEC_REPO" "${LIB_DIR}/xspec" 2>&1 | tail -1
    fi

    chmod +x "$XSPEC_SH"
    echo "Dependencies installed."
    echo
}

# ---------------------------------------------------------------------------
# Run XSpec unit tests
# ---------------------------------------------------------------------------
run_xspec() {
    local files=("$@")
    local pass=0
    local fail=0

    export SAXON_CP

    for test_file in "${files[@]}"; do
        if [[ ! -f "$test_file" ]]; then
            echo "WARNING: Test file not found: $test_file"
            continue
        fi

        echo "========================================"
        echo "Running: $(basename "$test_file")"
        echo "========================================"

        if "$XSPEC_SH" -t "$test_file"; then
            ((pass++))
        else
            ((fail++))
        fi
        echo
    done

    echo "========================================"
    echo "XSpec: ${pass} passed, ${fail} failed (out of $((pass + fail)) test files)"
    echo "========================================"
    echo

    return "$fail"
}

# ---------------------------------------------------------------------------
# Run example regression tests
# Transforms each examples/*.xml with CDA.xsl and diffs against examples/*.html
# ---------------------------------------------------------------------------
run_examples() {
    local pass=0
    local fail=0
    local skip=0
    local renders_dir="${SCRIPT_DIR}/test/example-renders"

    mkdir -p "$renders_dir"

    echo "========================================"
    echo "Example regression tests"
    echo "========================================"

    for xml_file in "${EXAMPLES_DIR}"/*.xml; do
        [[ -f "$xml_file" ]] || continue

        local base
        base="$(basename "$xml_file" .xml)"
        local expected_html="${EXAMPLES_DIR}/${base}.html"
        local actual_html="${renders_dir}/${base}.html"

        if [[ ! -f "$expected_html" ]]; then
            echo "  SKIP: ${base}.xml (no matching ${base}.html)"
            ((skip++))
            continue
        fi

        # Transform with Saxon
        if ! java -cp "$SAXON_CP" net.sf.saxon.Transform \
            -s:"$xml_file" -xsl:"${SCRIPT_DIR}/CDA.xsl" -o:"$actual_html" 2>/dev/null; then
            echo "  FAIL: ${base}.xml (transformation error)"
            ((fail++))
            continue
        fi

        # Exact diff
        if diff -q "$expected_html" "$actual_html" > /dev/null 2>&1; then
            echo "  PASS: ${base}"
            ((pass++))
        else
            echo "  FAIL: ${base}"
            echo "        diff examples/${base}.html test/example-renders/${base}.html"
            echo "        To accept: ./run-tests.sh --update"
            ((fail++))
        fi
    done

    if [[ $((pass + fail + skip)) -eq 0 ]]; then
        echo "  No example XML files found in examples/"
    fi

    echo "========================================"
    echo "Examples: ${pass} passed, ${fail} failed, ${skip} skipped"
    echo "========================================"
    echo

    return "$fail"
}

# ---------------------------------------------------------------------------
# Regenerate golden HTML files from examples/*.xml
# ---------------------------------------------------------------------------
update_examples() {
    echo "========================================"
    echo "Regenerating golden HTML files"
    echo "========================================"

    local count=0

    for xml_file in "${EXAMPLES_DIR}"/*.xml; do
        [[ -f "$xml_file" ]] || continue

        local base
        base="$(basename "$xml_file" .xml)"
        local html_file="${EXAMPLES_DIR}/${base}.html"

        echo "  ${base}.xml -> ${base}.html"
        java -cp "$SAXON_CP" net.sf.saxon.Transform \
            -s:"$xml_file" -xsl:"${SCRIPT_DIR}/CDA.xsl" -o:"$html_file"
        ((count++))
    done

    echo "========================================"
    echo "Updated ${count} file(s)"
    echo "========================================"
}

# ---------------------------------------------------------------------------
# Validate stylesheet and schema
# ---------------------------------------------------------------------------
run_validate() {
    local pass=0
    local fail=0

    echo "========================================"
    echo "Validation checks"
    echo "========================================"

    # Compile-check CDA.xsl by invoking a nonexistent template
    # Saxon will compile the stylesheet and fail at runtime — compile errors exit differently
    local xsl_output
    xsl_output=$(java -cp "$SAXON_CP" net.sf.saxon.Transform \
        -xsl:"${SCRIPT_DIR}/CDA.xsl" -it:__validation_check__ 2>&1)
    if echo "$xsl_output" | grep -q "XTDE0040"; then
        echo "  PASS: CDA.xsl compiles"
        ((pass++))
    else
        echo "  FAIL: CDA.xsl does not compile"
        echo "$xsl_output"
        ((fail++))
    fi

    # Validate cda_l10n.xml against cda_l10n.xsd
    javac -d "${SCRIPT_DIR}/test" "${SCRIPT_DIR}/test/Validate.java" 2>/dev/null
    if java -cp "${SCRIPT_DIR}/test" Validate \
        "${SCRIPT_DIR}/cda_l10n.xsd" "${SCRIPT_DIR}/cda_l10n.xml" 2>/dev/null; then
        ((pass++))
    else
        echo "  FAIL: cda_l10n.xml does not validate against cda_l10n.xsd"
        java -cp "${SCRIPT_DIR}/test" Validate \
            "${SCRIPT_DIR}/cda_l10n.xsd" "${SCRIPT_DIR}/cda_l10n.xml"
        ((fail++))
    fi

    echo "========================================"
    echo "Validation: ${pass} passed, ${fail} failed"
    echo "========================================"
    echo

    return "$fail"
}

# ---------------------------------------------------------------------------
# Collect all runnable XSpec files (excludes coverage and shared-params)
# ---------------------------------------------------------------------------
collect_xspec_files() {
    xspec_files=()
    for f in "${SCRIPT_DIR}"/test/*.xspec; do
        case "$(basename "$f")" in
            CDA-coverage.xspec|CDA-shared-params.xspec) continue ;;
        esac
        xspec_files+=("$f")
    done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
install_deps

VALIDATE_FAILURES=0
XSPEC_FAILURES=0
EXAMPLE_FAILURES=0

case "${1:-}" in
    --update)
        update_examples
        exit 0
        ;;
    --examples)
        run_examples || EXAMPLE_FAILURES=$?
        exit "$EXAMPLE_FAILURES"
        ;;
    --xspec)
        collect_xspec_files
        run_xspec "${xspec_files[@]}" || XSPEC_FAILURES=$?
        exit "$XSPEC_FAILURES"
        ;;
    --validate)
        run_validate || VALIDATE_FAILURES=$?
        exit "$VALIDATE_FAILURES"
        ;;
    "")
        # Run everything: validation + XSpec + examples
        run_validate || VALIDATE_FAILURES=$?
        collect_xspec_files
        run_xspec "${xspec_files[@]}" || XSPEC_FAILURES=$?
        run_examples || EXAMPLE_FAILURES=$?

        TOTAL_FAILURES=$((VALIDATE_FAILURES + XSPEC_FAILURES + EXAMPLE_FAILURES))
        if [[ $TOTAL_FAILURES -gt 0 ]]; then
            exit 1
        fi
        ;;
    *)
        # Specific XSpec files passed as arguments
        run_xspec "$@" || XSPEC_FAILURES=$?
        if [[ $XSPEC_FAILURES -gt 0 ]]; then
            exit 1
        fi
        ;;
esac
