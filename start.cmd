@echo off
rem Double-click this to start the course on Windows.
rem
rem Deliberately almost empty. The work is in tools\start.ps1, beside the
rem other PowerShell tooling, because PowerShell can check a port, poll a URL
rem and open a browser and batch can barely do any of it. This file exists
rem because a .ps1 cannot be double-clicked.
rem
rem It is also LF, like everything else in this repository: .gitattributes
rem pins every file to LF and tests/sweep.py refuses a carriage return in
rem anything Linux has to read. cmd.exe is content with LF for simple lines
rem like these -- measured on 2026-11-11 -- and keeping the file to simple
rem lines is why. Do not add a parenthesised block or a goto here; those are
rem where LF-only batch files are known to misparse. Put it in the .ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start.ps1" %*
