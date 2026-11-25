# Work out whether this machine can run the course container, and if it
# cannot, say which of the few possible reasons it is.
#
# For Windows. macOS and Linux have check-container.sh.
#
#   powershell -ExecutionPolicy Bypass -File tools\check-container.ps1
#
# This runs on your own machine, NOT inside the container -- if the container
# will not start, you cannot get inside it to ask why. Once you are inside,
# tools\check-environment.ps1 is the one to run.
#
# Exits 0 when a container runtime works here, 1 when it does not.
#
# WHY THIS EXISTS
# ---------------
# Whether a trainee can install a container runtime at all depends on their
# employer's administrator policy, their machine's firmware settings and
# Docker Desktop's company-size licence. No testing of ours can settle that
# in advance. What we can do is make the failure self-diagnosing, so somebody
# blocked at the first step knows within thirty seconds which wall they hit
# and whether they can get past it themselves.

$ErrorActionPreference = 'Continue'

Write-Output 'Checking whether this machine can run the course container.'
Write-Output ''
Write-Output ("  machine  Windows {0}" -f $env:PROCESSOR_ARCHITECTURE)
Write-Output ''

# --- Is there a runtime at all ----------------------------------------------

$runtime = $null
foreach ($candidate in @('podman', 'docker')) {
    $probe = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($probe) { $runtime = $candidate; break }
}

if (-not $runtime) {
    Write-Output '  MISSING  no container runtime'
    Write-Output '           Neither podman nor docker is installed, or neither is on'
    Write-Output '           your PATH.'
    Write-Output ''
    Write-Output '           Podman is the one to install: it is free for everyone and'
    Write-Output '           has no company-size licence condition.'
    Write-Output '           https://podman.io'
    Write-Output ''
    Write-Output '           If you cannot install either -- some employers do not'
    Write-Output '           permit it -- use NATIVE-SETUP.md instead. It needs no'
    Write-Output '           container and no administrator rights.'
    exit 1
}

$version = (& $runtime --version 2>$null | Select-Object -First 1)
Write-Output "  found    $runtime"
if ($version) { Write-Output "           $version" }
Write-Output ''

# --- It is installed. Does it actually run anything? ------------------------
#
# Installed and working are different things, and the gap between them is
# where almost everybody gets stuck: the command exists, and the service
# behind it will not start.

$info = (& $runtime info 2>&1 | Out-String)
if ($LASTEXITCODE -eq 0) {
    Write-Output "  ok       $runtime is running"
    Write-Output ''
    if ($runtime -eq 'docker') {
        Write-Output 'NOTE: Docker Desktop requires a paid subscription for companies'
        Write-Output 'above 250 employees or $10M revenue. Podman has no such'
        Write-Output 'threshold and runs this course identically. If a licence prompt'
        Write-Output 'appears, that is what it is about -- switch rather than buy.'
        Write-Output ''
    }
    # Only worth saying to somebody who ran this themselves; the launcher
    # runs it too, and would be telling a learner to build an image it is
    # about to build. See the note in check-container.sh.
    if (-not $env:COURSE_LAUNCHER) {
        Write-Output 'Ready. Start the course by double-clicking start.cmd in'
        Write-Output 'the folder you cloned.'
    } else {
        Write-Output 'Ready.'
    }
    exit 0
}

Write-Output "  FAILED   $runtime is installed but will not run"
Write-Output ''

# Classify it. These are ordered by how often they are the answer, and each
# says who can fix it -- which is the part a learner actually needs, because
# two of the three are not theirs to fix.
if ($info -match 'licen|subscription') {
    Write-Output '           A licence. Docker Desktop is chargeable above a'
    Write-Output '           company-size threshold.'
    Write-Output ''
    Write-Output '           Podman has no such threshold and runs this course'
    Write-Output '           identically. Install it rather than buying anything.'
    Write-Output '           https://podman.io'
} elseif ($info -match 'denied|permission|access is denied') {
    Write-Output '           Permission. Your user is probably not allowed to talk'
    Write-Output '           to the service.'
    Write-Output ''
    Write-Output '           On Windows this usually means your account is not in the'
    Write-Output '           docker-users group, which an administrator adds you to.'
    Write-Output '           Podman does not need one and is the quicker fix if you'
    Write-Output '           cannot get that changed.'
} else {
    Write-Output '           The service is not responding. On a work machine this'
    Write-Output '           is almost always one of two things:'
    Write-Output ''
    Write-Output '             - hardware virtualisation is switched off in the'
    Write-Output '               firmware, or the Windows features this needs are'
    Write-Output '               not enabled. ONLY AN ADMINISTRATOR CAN CHANGE THIS.'
    Write-Output '             - the runtime has not been started yet. Docker Desktop'
    Write-Output '               has to be running; with Podman, try'
    Write-Output "               'podman machine start' first."
    Write-Output ''
    Write-Output '           What it reported:'
    foreach ($line in ($info -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 6)) {
        Write-Output "             $line"
    }
}

Write-Output ''
Write-Output 'You do not have to solve this. NATIVE-SETUP.md is a second route'
Write-Output 'that needs no container and no administrator rights. It is more'
Write-Output 'steps, and it works.'
exit 1
