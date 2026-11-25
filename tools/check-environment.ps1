# Check that this machine can build and run the course, and say exactly what
# is missing if it cannot.
#
# For Windows. macOS and Linux have check-environment.sh. Both read the
# required versions from versions.env so neither can go stale alone.
#
#   powershell -ExecutionPolicy Bypass -File tools\check-environment.ps1
#
# Exits 0 when the environment is ready, 1 when something must be fixed.

$ErrorActionPreference = 'Continue'

$root = Split-Path -Parent $PSScriptRoot
$manifest = Join-Path $root 'versions.env'

if (-not (Test-Path $manifest)) {
    Write-Output 'Cannot find versions.env next to this script.'
    Write-Output 'Run this from inside a clone of the course repository.'
    exit 1
}

# versions.env is plain KEY=VALUE so that sh and PowerShell can both read it
# without a parser. Comments start with #.
$required = @{}
foreach ($line in Get-Content $manifest) {
    $trimmed = $line.Trim()
    if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
    $split = $trimmed.IndexOf('=')
    if ($split -lt 1) { continue }
    $required[$trimmed.Substring(0, $split)] = $trimmed.Substring($split + 1)
}

$problems = 0

function Say-Missing($name, $what, $where) {
    Write-Output "  MISSING  $name"
    Write-Output "           $what"
    Write-Output "           $where"
    $script:problems++
}

Write-Output 'Checking this machine against the course requirements.'
Write-Output ''

Write-Output ("  machine  Windows {0}" -f $env:PROCESSOR_ARCHITECTURE)
Write-Output ''

# --- The cross-compiler -----------------------------------------------------

$gccName = $required['ARM_GCC_COMMAND']
$gcc = Get-Command $gccName -ErrorAction SilentlyContinue

if ($gcc) {
    $found = (& $gccName --version 2>$null | Select-Object -First 1)
    Write-Output "  found    $gccName"
    Write-Output "           $found"
    Write-Output ("           at {0}" -f $gcc.Source)
    if ($found -notlike ('*' + $required['ARM_GCC_VERSION'] + '*')) {
        Write-Output ("           NOTE: verified against {0}. Yours differs." -f $required['ARM_GCC_VERSION'])
        Write-Output '           Usually fine. Worth mentioning if something misbehaves.'
    }
} else {
    Say-Missing "$gccName (the cross-compiler)" `
        'Extract the Arm GNU Toolchain and add its bin directory to your PATH.' `
        $required['ARM_GCC_DOWNLOAD']
}
Write-Output ''

# --- The simulator ----------------------------------------------------------

$renodeCmd = $null
foreach ($candidate in @($env:RENODE, 'renode', 'renode.exe')) {
    if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
    $probe = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($probe) { $renodeCmd = $probe; break }
    if (Test-Path $candidate) { $renodeCmd = Get-Item $candidate; break }
}

if ($renodeCmd) {
    $path = if ($renodeCmd.Source) { $renodeCmd.Source } else { $renodeCmd.FullName }
    $found = (& $path --version 2>$null | Select-Object -First 1)
    Write-Output '  found    renode'
    if ([string]::IsNullOrWhiteSpace($found)) {
        Write-Output '           version not reported'
    } else {
        Write-Output "           $found"
    }
    Write-Output "           at $path"
    if ($found -notlike ('*' + $required['RENODE_VERSION'] + '*')) {
        Write-Output ("           NOTE: this course is verified against Renode {0}." -f $required['RENODE_VERSION'])
        Write-Output '           The board description inherits a file from the Renode'
        Write-Output '           installation, so a different version can change the board'
        Write-Output '           without this repository changing. If the board behaves'
        Write-Output '           oddly, check this first.'
    }
} else {
    Say-Missing 'renode (the simulator)' `
        'Extract the Renode portable archive and add it to your PATH, or set RENODE to its path.' `
        $required['RENODE_DOWNLOAD']
}
Write-Output ''

# --- Do they work together --------------------------------------------------
#
# Knowing both tools exist is not the same as knowing they work on this board.
# Building and running a tiny program settles it, so that a problem later is
# known to be in the learner's code rather than in their installation.

if ($problems -eq 0) {
    Write-Output 'Building and running the self-test.'
    Write-Output ''

    $elf = Join-Path $root 'verify\verify.elf'
    $buildLog = & $gccName -mcpu=cortex-m4 -mthumb -mfloat-abi=soft -Og `
        -Wall -Wextra -ffreestanding -nostdlib `
        -T (Join-Path $root 'lib\linker.ld') -o $elf `
        (Join-Path $root 'lib\startup.c') (Join-Path $root 'verify\main.c') 2>&1

    if (-not (Test-Path $elf)) {
        Write-Output '  FAILED   the self-test did not compile'
        foreach ($line in $buildLog) { Write-Output "           $line" }
        $problems++
    } else {
        Write-Output '  ok       compiled'

        Push-Location $root
        $out = & $path --console --disable-xwt --plain `
            -e 'i @verify/verify.resc' -e 'quit' 2>&1 | Out-String
        Pop-Location

        $probes = @(
            @{ marker = 'serial ok'; label = 'the serial port works' },
            @{ marker = 'led on';    label = 'the user LED responds on PA5' },
            @{ marker = 'button 1';  label = 'the user button reads on PC13' },
            @{ marker = 'done';      label = 'the program ran to completion' }
        )
        foreach ($probe in $probes) {
            if ($out -match [regex]::Escape('CHECK ' + $probe.marker)) {
                Write-Output ('  ok       {0}' -f $probe.label)
            } else {
                Write-Output ('  FAILED   {0}' -f $probe.label)
                $problems++
            }
        }

        # The sensor reads 2499 rather than 2500 because of the model's
        # fixed-point conversion. See 'sensor-value-quantisation'.
        if ($out -match 'CHECK sensor 2[45]\d\d') {
            Write-Output '  ok       the Si7021 answers over I2C'
        } else {
            Write-Output '  FAILED   the Si7021 did not answer over I2C'
            $problems++
        }

        # The value printed after the CHECK ledstate label, and only that.
        # Matching 'True' anywhere in Renode's output would pass on any
        # unrelated line containing the word, which is not a check at all.
        $ledstate = $null
        $lines = $out -split "`r?`n"
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i].Trim() -ne 'CHECK ledstate') { continue }
            # If the label is the last line there is nothing after it. Without
            # this, PowerShell's range operator counts DOWNWARDS -- the slice
            # $lines[$Count..($Count - 1)] walks backwards through the output
            # and could find a 'True' printed before the label.
            if ($i + 1 -ge $lines.Count) { break }
            foreach ($candidate in $lines[($i + 1)..($lines.Count - 1)]) {
                $value = $candidate.Trim()
                if ($value -eq '' -or $value -match '^\d\d:\d\d:\d\d') { continue }
                $ledstate = $value
                break
            }
            break
        }
        if ($ledstate -eq 'True') {
            Write-Output '  ok       the simulator sees the LED lit'
        } else {
            Write-Output '  FAILED   the simulator does not see the LED lit'
            $shown = if ($ledstate) { $ledstate } else { 'nothing' }
            Write-Output "           the pin reported '$shown', expected True"
            $problems++
        }
    }
    Write-Output ''
}

# --- Verdict ----------------------------------------------------------------

if ($problems -eq 0) {
    Write-Output 'Ready. Your machine builds and runs this board correctly.'
    exit 0
}

if ($problems -eq 1) {
    Write-Output 'Not ready: 1 thing is missing, named above.'
} else {
    Write-Output "Not ready: $problems things are missing, named above."
}
Write-Output 'Fix what is named above and run this again. Nothing here needs administrator rights.'
exit 1
