# Start the course. Windows.
#
# The learner double-clicks start.cmd in the repository root, which runs this.
# Everything the old SETUP asked them to type happens here instead: the
# container pre-flight, the port check, the image build on a first run, the
# container itself, and the browser.
#
# Reports and stops rather than working around. Whether a learner can run a
# container at all depends on their employer's policy, their machine's
# firmware settings and Docker Desktop's licence, and no testing of ours
# settles that in advance (ADR-0014, ADR-0016). What we can do is make the
# failure say which of the few possible reasons it is, in a window that is
# still on screen when they read it.
#
# For macOS and Linux, tools/start.sh does the same thing.

# Continue, not Stop, and that is not laziness.
#
# Windows PowerShell 5.1 wraps every line a native command writes to stderr in
# an ErrorRecord. Under `Stop` that ends the script -- so `docker rm -f` on a
# container that is not there, which is the ordinary case on every first run,
# killed this launcher before it started anything. Measured 2026-11-11.
#
# Every docker call below is checked by $LASTEXITCODE instead, which is what a
# native command actually means by failure. Anything that is genuinely fatal
# calls Stop-WithReason.
$ErrorActionPreference = "Continue"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$image = "nucleo-f401re"
$name = "nucleo-f401re-board"
$pagePort = 8000
$dataPort = 9001
$url = "http://localhost:$pagePort/"

function Remove-Secret {
    # The credential file, gone. Called on every way out of this script,
    # because leaving a learner's token in their temp directory would be a
    # worse outcome than the board not starting.
    if ($script:secret -and (Test-Path $script:secret)) {
        try { Remove-Item -Force $script:secret } catch { }
    }
}

function Stop-WithReason([string]$why) {
    Remove-Secret
    Write-Host ""
    Write-Host "---------------------------------------------------------------"
    Write-Host $why
    Write-Host "---------------------------------------------------------------"
    Write-Host ""
    Write-Host "Press Enter to close this window."
    [void](Read-Host)
    exit 1
}

Set-Location $root

# 1. Can this machine run a container at all? check-container.ps1 exists to
#    answer exactly that and to say which reason applies, so it is asked
#    rather than guessed at.
Write-Host "Checking that this machine can run the course container."
$env:COURSE_LAUNCHER = "1"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\check-container.ps1")
if ($LASTEXITCODE -ne 0) {
    Stop-WithReason "The container runtime is not usable on this machine. What is wrong is named above."
}

# 2. Both ports, before anything starts.
#
#    Port 8000 is a common one, and a corporate machine may well have
#    something on it. While a learner typed the start command themselves a
#    clash was an error in front of them; now that this script owns that
#    command, the message could scroll past in a window that closes. And a
#    board view reachable on one port but not the other loads and then shows
#    an empty board, which reads as the drawing being broken rather than as a
#    port being taken -- so both are checked and neither is worked around.
foreach ($port in @($pagePort, $dataPort)) {
    $inUse = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($inUse) {
        Stop-WithReason ("Something on this machine is already using port $port, " +
                         "which the board view needs.`n`n" +
                         "Close whatever is using it and run this again. It is " +
                         "often another development server.")
    }
}

# 3. The image. Built here on a first run, which takes minutes and downloads
#    a cross-compiler and a simulator -- said out loud, because silence reads
#    as a hung window and a learner who closes it is left with a half-built
#    image.
& docker image inspect $image 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Building the course container. This happens once."
    Write-Host "It downloads a compiler and a simulator, so it takes a few"
    Write-Host "minutes. Later starts are immediate. Please leave this window open."
    Write-Host ""
    & docker build -t $image $root
    if ($LASTEXITCODE -ne 0) {
        Stop-WithReason "The course container could not be built. The reason is above."
    }
}

# 3a. The learner's own credential, if their clone left one.
#
#     Nothing is minted and nothing is stored. This asks git for the
#     credential it already uses for their repository -- the one their clone
#     put there -- so a learner who has cloned over HTTPS needs to do nothing
#     at all, and the course never holds a credential of its own (ADR-0044).
#
#     Returning nothing is an ordinary outcome, not a failure. An SSH clone
#     has none; so does a helper that keeps credentials somewhere git cannot
#     read them back from. The board still starts, the fetch control says why
#     it is unavailable, and the route that needs no credential is right
#     beside it.
#
#     GIT_TERMINAL_PROMPT and credential.interactive are both off, so this
#     can never stop and ask. A launcher that opened a password prompt on
#     startup would be worse than one that quietly did without.
$token = $null
try {
    $remote = & git -C $root remote get-url origin 2>$null
    if ($LASTEXITCODE -eq 0 -and $remote) {
        $env:GIT_TERMINAL_PROMPT = "0"
        $filled = ("url=$remote`n`n" |
                   & git -c credential.interactive=false `
                         -c credential.modalPrompt=false credential fill 2>$null)
        foreach ($line in $filled) {
            if ($line -is [string] -and $line.StartsWith("password=")) {
                $token = $line.Substring(9)
            }
        }
    }
} catch {
    $token = $null
}

$secret = $null
if ($token) {
    # A file, never an environment variable: an environment variable is in
    # `docker inspect` for the container's whole life, readable by anything
    # that can reach the daemon. This file is removed in the `finally` below,
    # whatever happens to the board.
    $secret = Join-Path ([System.IO.Path]::GetTempPath()) "nucleo-f401re-gh.txt"
    [System.IO.File]::WriteAllText($secret, $token)
    $token = $null
    Write-Host "Using the GitHub credential your clone already has."
} else {
    Write-Host "No GitHub credential found, so the board cannot fetch builds."
    Write-Host "Everything else works; you can drop a downloaded build in instead."
}

# 4. Start it.
#
#    Detached first, so the browser can be opened once the board answers, and
#    attached afterwards so the simulator's output is on screen and Ctrl-C
#    reaches it. `-it` is not optional: without a terminal the simulator reads
#    EOF on stdin and quits a second after starting, and the only trace is
#    "Machine paused / Disposed" in a log nobody is looking at.
& docker rm -f $name 2>&1 | Out-Null
Write-Host "Starting the board."
$arguments = @("-dit", "--rm", "--name", $name,
               "-v", "${root}:/work",
               "-p", "${pagePort}:8000", "-p", "${dataPort}:9001")
if ($secret) {
    # Read-only, and at a path the plugin knows. The file is removed when the
    # board stops; it cannot be removed sooner, because a bind-mounted file
    # that disappears from the host takes the mount with it.
    $arguments += @("-v", "${secret}:/run/secrets/gh:ro")
}
& docker run @arguments $image
if ($LASTEXITCODE -ne 0) {
    Stop-WithReason "The container would not start. The reason is above."
}

# 5. Wait for the board view to answer, then open it. Polled rather than
#    slept: a fixed wait is the kind of thing that works on the machine it
#    was written on and fails on a cold laptop.
Write-Host "Waiting for the board view."
$ready = $false
foreach ($attempt in 1..90) {
    try {
        $answer = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        if ($answer.StatusCode -eq 200) { $ready = $true; break }
    } catch {
        # Not up yet, or the environment check is still running. Both are
        # ordinary for the first few seconds.
    }
    if (-not (& docker ps -q -f "name=$name")) {
        Write-Host ""
        & docker logs $name
        Stop-WithReason "The board stopped before it finished starting. Its output is above."
    }
    Start-Sleep -Milliseconds 700
}

if ($ready) {
    Write-Host "Opening $url"
    Start-Process $url
} else {
    Write-Host ""
    Write-Host "The board view did not answer in time. Try opening $url yourself."
}

Write-Host ""
Write-Host "The board is running. To stop it, type  quit  at the prompt below."
Write-Host ""
Write-Host "Ctrl-C does not exit: Renode takes it as 'pause the board', and"
Write-Host "'start' resumes. That is Renode's own behaviour, not ours."
Write-Host ""
& docker attach $name

# Whatever ended the attach -- `quit`, a detach, a dropped connection -- the
# container must not be left running. It holds both ports, and the next start
# would stop on the port check with nothing to suggest the cause was the last
# session. `--rm` only cleans up once it has actually stopped.
& docker stop $name 2>&1 | Out-Null
Remove-Secret

# Attaching needs a terminal. Double-clicked there is one, but this script may
# also be run from somewhere without -- a pipe, a task runner, a CI step --
# where attach refuses with "the input device is not a TTY". The board is
# running either way, so say how to stop it rather than leaving it with no
# visible means of being stopped.
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "This window could not attach to the board, so the board is"
    Write-Host "running in the background instead. It still works: open $url"
    Write-Host ""
    Write-Host "To stop it:   docker stop $name"
}
