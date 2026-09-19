@echo off
rem ==========================================================================
rem  hato-run.cmd -- the double-clickable launcher (spec/10-deployment.md)
rem
rem    double-click           runs every folder in config.toml, prints, PAUSES
rem    drag a folder onto it  Windows passes the path as %1 -- runs that folder
rem    Task Scheduler         points here with --quiet; the log is the record
rem
rem  FOUR THINGS IT MUST GET RIGHT, none of which a developer shell catches:
rem
rem    1. It must not depend on the working directory. Task Scheduler starts a
rem       process somewhere unexpected, so every path below comes from %~dp0
rem       (this script's own folder) or from %LOCALAPPDATA% -- never from ".".
rem    2. It must pause when interactive and NOT when scheduled. A scheduled
rem       run that pauses waits for ever HOLDING THE RUN LOCK, and every later
rem       run then exits on that lock: hato silently stops working.
rem    3. Output must degrade when it is not a console. ANSI colour escapes in
rem       a log file are noise, so --no-color is passed when stdout is not one.
rem    4. It must exit with a real code. 0 = it ran. Refusals and NOT_FOUNDs
rem       are NORMAL OUTCOMES and must never turn a scheduled task red.
rem
rem  THIS FILE IS DELIBERATELY ASCII-ONLY. A non-ASCII byte in a .cmd is read
rem  in the console's codepage, not UTF-8, and one mis-decoded character opens
rem  a string that breaks the parse lines away from where it was written
rem  (measured on this machine for .ps1; the same decoder is at fault here).
rem  Everything the user reads is printed by Python, which is told UTF-8 below.
rem
rem  KNOBS, all optional:
rem    HATO_PYTHON     the interpreter to use (default: py -3, else python)
rem    HATO_RUN_PAUSE  1 = always pause, 0 = never. Overrides the detection
rem    HATO_NO_PAUSE   set = never pause (kept for older habits)
rem    HATO_RUN_DEBUG  set = print what this script decided, to stderr
rem    HATO_CACHE      relocates hato's WHOLE per-user root, this script too
rem ==========================================================================
setlocal EnableExtensions

rem -- 1. every path absolute, from this script and the environment -----------
set "HATO_HERE=%~dp0"
if "%HATO_HERE:~-1%"=="\" set "HATO_HERE=%HATO_HERE:~0,-1%"
if defined HATO_CACHE (set "HATO_ROOT=%HATO_CACHE%") else (set "HATO_ROOT=%LOCALAPPDATA%\hato")
set "HATO_BOOTLOG=%HATO_ROOT%\hato.log"

rem Japanese filenames reach stdout constantly. Windows Python defaults to
rem cp1252 and raises on the first one (LEDGER-HOT.md).
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem Running from a source checkout (this file sitting beside the package):
rem put it on the path so the launcher works before anything is installed.
rem An installed hato has no `hato\__init__.py` beside this file, so this is
rem skipped and the installed package is used.
rem An EMPTY ENTRY IN PYTHONPATH MEANS THE WORKING DIRECTORY, which is rule 1
rem broken by a semicolon: with PYTHONPATH unset, "%HATO_HERE%;%PYTHONPATH%"
rem ends in ";" and Python then imports from wherever the scheduler started us.
if exist "%HATO_HERE%\hato\__init__.py" (
    if defined PYTHONPATH (
        set "PYTHONPATH=%HATO_HERE%;%PYTHONPATH%"
    ) else (
        set "PYTHONPATH=%HATO_HERE%"
    )
)

rem -- 2. the interpreter ----------------------------------------------------
set "PYEXE="
set "PYARGS="
if defined HATO_PYTHON goto :have_python
where py.exe >nul 2>nul
if not errorlevel 1 goto :use_py
where python.exe >nul 2>nul
if not errorlevel 1 goto :use_python
call :bootlog "hato-run.cmd: no Python found. Install Python 3.10+ or set HATO_PYTHON."
echo hato-run.cmd: no Python found on PATH. Install Python 3.10 or newer, 1>&2
echo               or set HATO_PYTHON to the interpreter to use. 1>&2
endlocal
exit /b 1

:have_python
set "PYEXE=%HATO_PYTHON%"
goto :python_ready
:use_py
set "PYEXE=py"
set "PYARGS=-3"
goto :python_ready
:use_python
set "PYEXE=python"
:python_ready

rem -- 3. is our stdout a console? Python answers for the stream we own -------
rem A batch file has no way to ask this; the interpreter we are about to use
rem inherits exactly this script's stdout, so its answer is the right one.
set "CONSOLE=0"
"%PYEXE%" %PYARGS% -c "import sys;sys.exit(0 if sys.stdout.isatty() else 1)"
if not errorlevel 1 set "CONSOLE=1"

set "COLOUR="
if "%CONSOLE%"=="0" set "COLOUR=--no-color"

rem -- 4. the arguments, REBUILT WITH EVERY ONE OF THEM QUOTED ---------------
rem %* is the RAW command-line tail, and forwarding it re-parses it: whether a
rem folder called Tom&Jerry survives then depends on whether the caller thought
rem to quote it. Rebuilt from %1 with quotes we put on ourselves, it does not.
rem This also replaces `call :scan_args %*`, which re-parsed the tail a second
rem time purely to look for --quiet.
rem
rem AND FIRST, REPAIR AN ARGUMENT THE COMMAND PROCESSOR ALREADY SPLIT. Windows
rem does not quote a dropped path with no space in it, so dropping Tom&Jerry on
rem this file makes CMD cut the line at the & BEFORE %1 exists: hato was handed
rem "...\Tom", which is not a folder anybody named, and "Jerry" was then run as
rem a command ("'Jerry' is not recognized..."). Measured 2026-09-17.
rem %CMDCMDLINE% still holds the WHOLE original line, so the path can be put
rem back together. THREE GATES, so this can never redirect a run that was fine:
rem   1. what we were handed is not a folder
rem   2. the recovered remainder starts with the & that did the splitting
rem   3. the two joined back together ARE a folder
rem Anything else -- several dropped paths, a flag after the path, a launcher
rem called from another script -- fails a gate and is left exactly as it was.
rem Both cleared BEFORE the gates below: an early `goto :no_repair` would
rem otherwise leave whatever the caller happened to have in the environment.
set "HATO_FIX1="
set "HATO_REPAIRED="
if "%~1"=="" goto :no_repair
if exist "%~1\" goto :no_repair
set "HATO_LINE=%CMDCMDLINE%"
set "HATO_GIVEN=%~1"
call set "HATO_TAIL=%%HATO_LINE:*%HATO_GIVEN%=%%"
if not defined HATO_TAIL goto :no_repair
if not "%HATO_TAIL:~0,1%"=="&" goto :no_repair
if exist "%HATO_GIVEN%%HATO_TAIL%\" set "HATO_FIX1=%HATO_GIVEN%%HATO_TAIL%"
if defined HATO_FIX1 set "HATO_REPAIRED=1"
if defined HATO_RUN_DEBUG if defined HATO_FIX1 echo hato-run: repaired a path the command processor split on ^& 1>&2
:no_repair

set "QUIET="
set "HATO_ARGS="
:scan_args
if "%~1"=="" goto :args_done
set "HATO_ARG=%~1"
if defined HATO_FIX1 set "HATO_ARG=%HATO_FIX1%"
set "HATO_FIX1="
if /I "%HATO_ARG%"=="--quiet" set "QUIET=1"
set HATO_ARGS=%HATO_ARGS% "%HATO_ARG%"
shift
goto :scan_args
:args_done

rem -- 5. pause when interactive, NEVER when scheduled ------------------------
set "PAUSED=1"
if defined QUIET set "PAUSED="
if "%CONSOLE%"=="0" set "PAUSED="
if defined HATO_NO_PAUSE set "PAUSED="
if "%HATO_RUN_PAUSE%"=="1" set "PAUSED=1"
if "%HATO_RUN_PAUSE%"=="0" set "PAUSED="

if defined HATO_RUN_DEBUG echo hato-run: python="%PYEXE%" %PYARGS% console=%CONSOLE% quiet=%QUIET% pause=%PAUSED% root="%HATO_ROOT%" 1>&2

rem -- 6. the run ------------------------------------------------------------
"%PYEXE%" %PYARGS% -m hato%HATO_ARGS% %COLOUR%
set "CODE=%ERRORLEVEL%"

rem A failure must survive until somebody next looks. hato writes the run
rem itself (one config, not three -- it is the only thing that can read
rem log.path and rotate by runs); this line is for the failures that happen
rem before or around it, which hato never got to record.
if not "%CODE%"=="0" call :bootlog "hato-run.cmd: hato exited %CODE%"

if defined PAUSED pause

rem EXIT, NOT EXIT /B, AND ONLY WHEN WE PUT A SPLIT PATH BACK TOGETHER.
rem The repair above proves CMD already cut its command line at our &, so
rem the fragment after it ("Jerry") is still queued to run as a command the
rem moment we return -- printing "'Jerry' is not recognized" and handing ITS
rem code to whoever asked, which turned a clean run into an exit 1. Ending
rem the command processor instead means the fragment never runs and our own
rem code is the one that is reported. Rule 4: 0 = it ran.
rem It is gated on the repair because `exit` ends a CALLER'S shell too, and
rem a launcher may never do that to a script that merely called it.
if defined HATO_REPAIRED (endlocal & exit %CODE%)
endlocal & exit /b %CODE%

rem ==========================================================================
:bootlog
if not exist "%HATO_ROOT%" mkdir "%HATO_ROOT%" >nul 2>nul
rem The redirect goes FIRST. `echo ... exited 1>>file` parses the trailing 1 as
rem the stdout stream number and swallows it -- measured here: the log read
rem "hato exited " with the code gone, on the one line that exists to carry it.
>>"%HATO_BOOTLOG%" echo [%DATE% %TIME%] %~1
goto :eof
