# Build one exercise.
#
#   powershell -ExecutionPolicy Bypass -File tools\build.ps1 exercises\01-blink-with-a-delay
#
# The -ExecutionPolicy argument is not decoration. A Windows machine that
# nobody has changed refuses to run a .ps1 at all, and the refusal names
# the policy rather than the script, so it reads as the course being
# broken. The other two scripts here have always been invoked this way.
#
# Produces firmware.elf inside that directory. macOS and Linux have
# tools/build.sh, which does the same thing with the same flags.

param([string]$Exercise)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot

if (-not $Exercise) {
    Write-Output 'Which exercise? For example:'
    Write-Output '  powershell -ExecutionPolicy Bypass -File tools\build.ps1 exercises\01-blink-with-a-delay'
    Write-Output ''
    Write-Output 'Available:'
    Get-ChildItem (Join-Path $root 'exercises') -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Output ('  exercises\' + $_.Name) }
    exit 2
}

$target = $Exercise
if (-not (Test-Path (Join-Path $target 'main.c'))) {
    $target = Join-Path $root $Exercise
}
if (-not (Test-Path (Join-Path $target 'main.c'))) {
    Write-Output "No main.c in $Exercise"
    exit 2
}

# The same three exit codes as tools/build.sh: 0 built, 1 the compiler
# rejected the code, 2 the build could not be attempted. See the note in
# build.sh for why the third one has to be distinguishable.
# Encoding before compiler, as in build.sh. A Shift-JIS byte reaches the
# compiler as a puzzle and reaches a Makefile as a line continuation that
# swallows the next line, so this runs first and names the file and byte.
# Get-Command finds the Microsoft Store alias stub as readily as a real
# interpreter, and the stub prints "Python was not found" and exits
# non-zero -- which would stop the build for something that is not an
# encoding at all. So each candidate is asked to run something trivial
# before it is believed.
foreach ($name in @("python", "python3")) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $found) { continue }
    & $found.Source -c "pass" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { continue }
    # Written straight to the console, and NOT captured. tools/build.sh
    # holds the same output back until the check finds something, because
    # the grader reads what that script prints and hands it to the
    # assistant. Nobody reads this script's output but the person who ran
    # it, so there is nothing to protect them from -- and capturing it
    # here made things worse: PowerShell wraps each line a native program
    # writes to stderr in an ErrorRecord, so the learner was shown a
    # NativeCommandError and a tilde-underlined line of this file before
    # the message that was written for them.
    & $found.Source (Join-Path $root "tools/check_encoding.py") $root
    if ($LASTEXITCODE -ne 0) { exit 2 }
    break
}

if (-not (Get-Command arm-none-eabi-gcc -ErrorAction SilentlyContinue)) {
    Write-Output "arm-none-eabi-gcc is not on PATH, so nothing can be built."
    Write-Output "This is not a problem with the code in $Exercise."
    Write-Output "Inside the course container the compiler is already there; run"
    Write-Output "tools\check-environment.sh to see what is missing."
    exit 2
}

$elf = Join-Path $target 'firmware.elf'

# soft float: these exercises need no floating point, and hard float would
# require enabling the FPU before main. The device has one -- see
# boards\nucleo_f401re.repl -- it is simply not switched on here.
& arm-none-eabi-gcc `
    -mcpu=cortex-m4 -mthumb -mfloat-abi=soft `
    -Og -g -Wall -Wextra `
    -ffreestanding -nostdlib `
    -DSTM32F401xE `
    -I (Join-Path $root 'lib\cmsis') `
    -T (Join-Path $root 'lib\linker.ld') `
    -o $elf `
    (Join-Path $root 'lib\startup.c') (Join-Path $target 'main.c')

if (-not (Test-Path $elf)) { exit 1 }

Write-Output "Built $Exercise\firmware.elf"
& arm-none-eabi-size $elf
