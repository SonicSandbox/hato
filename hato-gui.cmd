@echo off
rem ==========================================================================
rem  hato-gui.cmd -- the double-clickable launcher for the WINDOW (RUNBOOK 7c)
rem
rem  The sibling of hato-run.cmd, and it differs in exactly two ways, both
rem  because this one opens a window instead of printing:
rem
rem    1. NO PAUSE, EVER. hato-run.cmd pauses so a person can read the output
rem       of a run. A window has no output to read, and a pause here would
rem       leave a dead console sitting behind the window until it is closed.
rem    2. pythonw.exe, NOT python.exe. A GUI started from python.exe keeps a
rem       console open behind it for the life of the window -- and every child
rem       hato spawns would inherit it. pythonw has no console at all.
rem
rem  THIS FILE IS DELIBERATELY ASCII-ONLY. A non-ASCII byte in a .cmd is read
rem  in the console's codepage, not UTF-8, and one mis-decoded character opens
rem  a string that breaks the parse lines away from where it was written.
rem
rem  KNOBS, all optional:
rem    HATO_PYTHONW  the windowed interpreter to use (default: pythonw beside
rem                  HATO_PYTHON, else pythonw on PATH, else python)
rem    HATO_PYTHON   the console interpreter, used only as the last resort
rem    HATO_CACHE    relocates hato's WHOLE per-user root, this script too
rem ==========================================================================
setlocal EnableExtensions

rem -- every path absolute, from this script -- never from "." ---------------
set "HATO_HERE=%~dp0"
if "%HATO_HERE:~-1%"=="\" set "HATO_HERE=%HATO_HERE:~0,-1%"

rem Japanese show titles reach the window constantly. Windows Python defaults
rem to cp1252 and raises on the first one (LEDGER-HOT.md).
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem The package has to be importable wherever the shortcut was launched from.
rem A shortcut's working directory is whatever it was told, and Windows will
rem happily make that System32.
if defined PYTHONPATH (
  set "PYTHONPATH=%HATO_HERE%;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%HATO_HERE%"
)

rem -- pick a WINDOWED interpreter -------------------------------------------
set "HATO_GUI_EXE="
if defined HATO_PYTHONW set "HATO_GUI_EXE=%HATO_PYTHONW%"

if not defined HATO_GUI_EXE (
  for %%I in (pythonw.exe) do if not "%%~$PATH:I"=="" set "HATO_GUI_EXE=%%~$PATH:I"
)
if not defined HATO_GUI_EXE (
  rem py -3 knows where the interpreter is even when PATH does not.
  for /f "usebackq delims=" %%I in (`py -3 -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul`) do (
    if exist "%%~I" set "HATO_GUI_EXE=%%~I"
  )
)

if defined HATO_GUI_EXE (
  rem start "" detaches, so this console closes immediately instead of
  rem sitting there for as long as the window is open.
  start "" "%HATO_GUI_EXE%" -m hato.gui %*
  endlocal
  exit /b 0
)

rem -- last resort: a console interpreter ------------------------------------
rem The window still opens; there is simply a console behind it. Saying so is
rem better than failing, and better than a console nobody can explain.
echo hato: pythonw.exe was not found, so the window will open with a console
echo       behind it. Set HATO_PYTHONW to the pythonw.exe you want used.
if defined HATO_PYTHON (
  "%HATO_PYTHON%" -m hato.gui %*
) else (
  py -3 -m hato.gui %* 2>nul || python -m hato.gui %*
)
set "HATO_CODE=%ERRORLEVEL%"
endlocal & exit /b %HATO_CODE%
