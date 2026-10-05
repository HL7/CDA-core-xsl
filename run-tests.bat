@echo off
setlocal enabledelayedexpansion
REM Run XSpec unit tests and example regression tests for CDA.xsl
REM
REM Usage:
REM   run-tests.bat              Run all unit tests + example regression tests
REM   run-tests.bat test\X.xspec Run only the specified XSpec file(s)
REM   run-tests.bat --xspec      Run only the XSpec unit tests
REM   run-tests.bat --examples   Run only the example regression tests
REM   run-tests.bat --update     Regenerate the golden HTML files in examples\
REM
REM Dependencies are automatically downloaded on first run.
REM Requires: java, git, curl (or PowerShell for downloads)

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "LIB_DIR=%SCRIPT_DIR%\lib"
set "EXAMPLES_DIR=%SCRIPT_DIR%\examples"

REM Dependency versions
set "SAXON_VERSION=12.5"
set "XMLRESOLVER_VERSION=5.2.2"
set "XSPEC_REPO=https://github.com/xspec/xspec.git"

REM Derived paths
set "SAXON_JAR=%LIB_DIR%\saxon-he-%SAXON_VERSION%.jar"
set "XMLRESOLVER_JAR=%LIB_DIR%\xmlresolver-%XMLRESOLVER_VERSION%.jar"
set "XMLRESOLVER_DATA_JAR=%LIB_DIR%\xmlresolver-%XMLRESOLVER_VERSION%-data.jar"
set "XSPEC_BAT=%LIB_DIR%\xspec\bin\xspec.bat"
set "SAXON_CP=%SAXON_JAR%;%XMLRESOLVER_JAR%;%XMLRESOLVER_DATA_JAR%"

REM ---------------------------------------------------------------------------
REM Check for Java
REM ---------------------------------------------------------------------------
where java >nul 2>&1
if errorlevel 1 (
    echo ERROR: Java is required but not found on PATH.
    echo   Install Java 11+ from one of:
    echo     Amazon Corretto: https://aws.amazon.com/corretto/
    echo     Eclipse Temurin: https://adoptium.net/
    echo     Oracle JDK:      https://www.oracle.com/java/technologies/downloads/
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM Auto-install missing dependencies
REM ---------------------------------------------------------------------------
call :install_deps

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
if "%~1"=="" goto :run_all
if "%~1"=="--update" goto :update_examples
if "%~1"=="--examples" goto :run_examples_only
if "%~1"=="--xspec" goto :run_xspec_only
goto :run_specific

REM ---------------------------------------------------------------------------
REM Run everything
REM ---------------------------------------------------------------------------
:run_all
call :run_xspec_all
set "XSPEC_FAILURES=%ERRORLEVEL%"
call :run_examples
set "EXAMPLE_FAILURES=%ERRORLEVEL%"
set /a "TOTAL=%XSPEC_FAILURES%+%EXAMPLE_FAILURES%"
if %TOTAL% gtr 0 exit /b 1
exit /b 0

:run_xspec_only
call :run_xspec_all
exit /b %ERRORLEVEL%

:run_examples_only
call :run_examples
exit /b %ERRORLEVEL%

REM ---------------------------------------------------------------------------
REM Run specific XSpec file(s)
REM ---------------------------------------------------------------------------
:run_specific
set "PASS=0"
set "FAIL=0"
:run_specific_loop
if "%~1"=="" goto :run_specific_done
if not exist "%~1" (
    echo WARNING: Test file not found: %~1
    shift
    goto :run_specific_loop
)
echo ========================================
echo Running: %~nx1
echo ========================================
call "%XSPEC_BAT%" -t "%~1"
if errorlevel 1 (
    set /a "FAIL+=1"
) else (
    set /a "PASS+=1"
)
echo.
shift
goto :run_specific_loop
:run_specific_done
echo ========================================
echo XSpec: %PASS% passed, %FAIL% failed
echo ========================================
if %FAIL% gtr 0 exit /b 1
exit /b 0

REM ---------------------------------------------------------------------------
REM Run all XSpec tests (excluding coverage and shared-params)
REM ---------------------------------------------------------------------------
:run_xspec_all
set "PASS=0"
set "FAIL=0"
for %%f in ("%SCRIPT_DIR%\test\*.xspec") do (
    set "BASENAME=%%~nxf"
    if /i not "!BASENAME!"=="CDA-coverage.xspec" (
        if /i not "!BASENAME!"=="CDA-shared-params.xspec" (
            echo ========================================
            echo Running: !BASENAME!
            echo ========================================
            call "%XSPEC_BAT%" -t "%%f"
            if errorlevel 1 (
                set /a "FAIL+=1"
            ) else (
                set /a "PASS+=1"
            )
            echo.
        )
    )
)
set /a "TOTAL_FILES=%PASS%+%FAIL%"
echo ========================================
echo XSpec: %PASS% passed, %FAIL% failed (out of %TOTAL_FILES% test files)
echo ========================================
echo.
exit /b %FAIL%

REM ---------------------------------------------------------------------------
REM Run example regression tests
REM ---------------------------------------------------------------------------
:run_examples
set "PASS=0"
set "FAIL=0"
set "SKIP=0"
set "RENDERS_DIR=%SCRIPT_DIR%\test\example-renders"
if not exist "%RENDERS_DIR%" mkdir "%RENDERS_DIR%"

echo ========================================
echo Example regression tests
echo ========================================

for %%x in ("%EXAMPLES_DIR%\*.xml") do (
    call :run_one_example "%%x"
)

echo ========================================
echo Examples: %PASS% passed, %FAIL% failed, %SKIP% skipped
echo ========================================
echo.
exit /b %FAIL%

REM ---------------------------------------------------------------------------
REM Regenerate golden HTML files
REM ---------------------------------------------------------------------------
:update_examples
echo ========================================
echo Regenerating golden HTML files
echo ========================================
set "COUNT=0"
for %%x in ("%EXAMPLES_DIR%\*.xml") do (
    set "BASE=%%~nx"
    echo   %%~nxx.xml -^> %%~nx.html
    java -cp "%SAXON_CP%" net.sf.saxon.Transform -s:"%%x" -xsl:"%SCRIPT_DIR%\CDA.xsl" -o:"%EXAMPLES_DIR%\%%~nx.html"
    set /a "COUNT+=1"
)
echo ========================================
echo Updated %COUNT% file(s)
echo ========================================
exit /b 0

REM ---------------------------------------------------------------------------
REM Process a single example file (called from run_examples loop)
REM ---------------------------------------------------------------------------
:run_one_example
set "EX_XML=%~1"
set "EX_BASE=%~n1"
set "EX_EXPECTED=%EXAMPLES_DIR%\%~n1.html"
set "EX_ACTUAL=%RENDERS_DIR%\%~n1.html"

if not exist "%EX_EXPECTED%" (
    echo   SKIP: %EX_BASE%.xml (no matching .html^)
    set /a "SKIP+=1"
    exit /b 0
)

java -cp "%SAXON_CP%" net.sf.saxon.Transform -s:"%EX_XML%" -xsl:"%SCRIPT_DIR%\CDA.xsl" -o:"%EX_ACTUAL%" 2>nul
if errorlevel 1 (
    echo   FAIL: %EX_BASE% (transformation error^)
    set /a "FAIL+=1"
    exit /b 0
)

fc /b "%EX_EXPECTED%" "%EX_ACTUAL%" >nul 2>&1
if errorlevel 1 (
    echo   FAIL: %EX_BASE%
    echo         To accept: run-tests.bat --update
    set /a "FAIL+=1"
) else (
    echo   PASS: %EX_BASE%
    set /a "PASS+=1"
)
exit /b 0

REM ---------------------------------------------------------------------------
REM Auto-install missing dependencies
REM ---------------------------------------------------------------------------
:install_deps
set "NEEDED=false"
if not exist "%SAXON_JAR%" set "NEEDED=true"
if not exist "%XMLRESOLVER_JAR%" set "NEEDED=true"
if not exist "%XMLRESOLVER_DATA_JAR%" set "NEEDED=true"
if not exist "%XSPEC_BAT%" set "NEEDED=true"

if "%NEEDED%"=="false" exit /b 0

echo Installing missing test dependencies into lib\...
if not exist "%LIB_DIR%" mkdir "%LIB_DIR%"

if not exist "%SAXON_JAR%" (
    echo   Downloading Saxon HE %SAXON_VERSION%...
    curl -sSL -o "%SAXON_JAR%" "https://repo1.maven.org/maven2/net/sf/saxon/Saxon-HE/%SAXON_VERSION%/Saxon-HE-%SAXON_VERSION%.jar" 2>nul || (
        powershell -Command "Invoke-WebRequest -Uri 'https://repo1.maven.org/maven2/net/sf/saxon/Saxon-HE/%SAXON_VERSION%/Saxon-HE-%SAXON_VERSION%.jar' -OutFile '%SAXON_JAR%'"
    )
)

if not exist "%XMLRESOLVER_JAR%" (
    echo   Downloading XML Resolver %XMLRESOLVER_VERSION%...
    curl -sSL -o "%XMLRESOLVER_JAR%" "https://repo1.maven.org/maven2/org/xmlresolver/xmlresolver/%XMLRESOLVER_VERSION%/xmlresolver-%XMLRESOLVER_VERSION%.jar" 2>nul || (
        powershell -Command "Invoke-WebRequest -Uri 'https://repo1.maven.org/maven2/org/xmlresolver/xmlresolver/%XMLRESOLVER_VERSION%/xmlresolver-%XMLRESOLVER_VERSION%.jar' -OutFile '%XMLRESOLVER_JAR%'"
    )
)

if not exist "%XMLRESOLVER_DATA_JAR%" (
    echo   Downloading XML Resolver %XMLRESOLVER_VERSION% data...
    curl -sSL -o "%XMLRESOLVER_DATA_JAR%" "https://repo1.maven.org/maven2/org/xmlresolver/xmlresolver/%XMLRESOLVER_VERSION%/xmlresolver-%XMLRESOLVER_VERSION%-data.jar" 2>nul || (
        powershell -Command "Invoke-WebRequest -Uri 'https://repo1.maven.org/maven2/org/xmlresolver/xmlresolver/%XMLRESOLVER_VERSION%/xmlresolver-%XMLRESOLVER_VERSION%-data.jar' -OutFile '%XMLRESOLVER_DATA_JAR%'"
    )
)

if not exist "%LIB_DIR%\xspec" (
    echo   Cloning XSpec...
    git clone --depth 1 "%XSPEC_REPO%" "%LIB_DIR%\xspec"
)

echo Dependencies installed.
echo.
exit /b 0
