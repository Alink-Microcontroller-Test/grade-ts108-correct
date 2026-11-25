#!/bin/sh
# Check that this machine can build and run the course, and say exactly what
# is missing if it cannot.
#
# For macOS and Linux. Windows has check-environment.ps1. Both read the
# required versions from versions.env so neither can go stale alone.
#
#   ./tools/check-environment.sh
#
# Exits 0 when the environment is ready, 1 when something must be fixed.

set -u

here=$(dirname "$0")
root=$(cd "$here/.." && pwd)

if [ ! -f "$root/versions.env" ]; then
    echo "Cannot find versions.env next to this script."
    echo "Run this from inside a clone of the course repository."
    exit 1
fi

# shellcheck disable=SC1090
. "$root/versions.env"

problems=0

say_missing() {
    # name, what to do, where to get it
    echo "  MISSING  $1"
    echo "           $2"
    echo "           $3"
    problems=$((problems + 1))
}

echo "Checking this machine against the course requirements."
echo

# --- What machine is this ---------------------------------------------------

os=$(uname -s)
arch=$(uname -m)
echo "  machine  $os $arch"

if [ "$os" = "Darwin" ] && [ "$arch" = "x86_64" ]; then
    echo
    echo "  NOTE     This is an Intel Mac. Renode publishes no build for it:"
    echo "           Intel macOS packages were removed in Renode 1.17.0, and"
    echo "           Rosetta translates Intel software to run on Apple silicon,"
    echo "           not the other way round."
    echo "           Use the container instead. See SETUP.md."
fi
echo

# --- The cross-compiler -----------------------------------------------------

if command -v "$ARM_GCC_COMMAND" >/dev/null 2>&1; then
    found=$("$ARM_GCC_COMMAND" --version 2>/dev/null | head -1)
    where=$(command -v "$ARM_GCC_COMMAND")
    echo "  found    $ARM_GCC_COMMAND"
    echo "           $found"
    echo "           at $where"
    case "$found" in
        *"$ARM_GCC_VERSION"*) : ;;
        *)
            echo "           NOTE: verified against $ARM_GCC_VERSION. Yours differs."
            echo "           Usually fine. Worth mentioning if something misbehaves."
            ;;
    esac
else
    say_missing "$ARM_GCC_COMMAND (the cross-compiler)" \
        "Extract the Arm GNU Toolchain and add its bin directory to your PATH." \
        "$ARM_GCC_DOWNLOAD"
fi
echo

# --- The simulator ----------------------------------------------------------

renode_cmd=""
for candidate in "${RENODE:-}" renode; do
    [ -n "$candidate" ] || continue
    if command -v "$candidate" >/dev/null 2>&1; then
        renode_cmd=$candidate
        break
    fi
done

if [ -n "$renode_cmd" ]; then
    found=$("$renode_cmd" --version 2>/dev/null | head -1)
    echo "  found    renode"
    echo "           ${found:-version not reported}"
    echo "           at $(command -v "$renode_cmd")"
    case "$found" in
        *"$RENODE_VERSION"*) : ;;
        *)
            echo "           NOTE: this course is verified against Renode $RENODE_VERSION."
            echo "           The board description inherits a file from the Renode"
            echo "           installation, so a different version can change the board"
            echo "           without this repository changing. If the board behaves"
            echo "           oddly, check this first."
            ;;
    esac
else
    say_missing "renode (the simulator)" \
        "Extract the Renode portable archive and add it to your PATH, or set RENODE to its path." \
        "$RENODE_DOWNLOAD"
fi
echo

# --- Do they work together --------------------------------------------------
#
# Knowing both tools exist is not the same as knowing they work on this board.
# Building and running a tiny program settles it, so that a problem later is
# known to be in the learner's code rather than in their installation.

if [ "$problems" -eq 0 ]; then
    echo "Building and running the self-test."
    echo

    if ! "$ARM_GCC_COMMAND" -mcpu=cortex-m4 -mthumb -mfloat-abi=soft -Og \
            -Wall -Wextra -ffreestanding -nostdlib \
            -T "$root/lib/linker.ld" -o "$root/verify/verify.elf" \
            "$root/lib/startup.c" "$root/verify/main.c" 2>/tmp/verify-build.$$; then
        echo "  FAILED   the self-test did not compile"
        sed 's/^/           /' "/tmp/verify-build.$$"
        rm -f "/tmp/verify-build.$$"
        problems=$((problems + 1))
    else
        rm -f "/tmp/verify-build.$$"
        echo "  ok       compiled"

        out=$(cd "$root" && "$renode_cmd" --console --disable-xwt --plain \
              -e "i @verify/verify.resc" -e "quit" 2>&1)

        for probe in "serial ok:the serial port works" \
                     "led on:the user LED responds on PA5" \
                     "button 1:the user button reads on PC13" \
                     "done:the program ran to completion"; do
            marker=${probe%%:*}
            label=${probe#*:}
            if echo "$out" | grep -q "CHECK $marker"; then
                echo "  ok       $label"
            else
                echo "  FAILED   $label"
                problems=$((problems + 1))
            fi
        done

        # The sensor reads 2499 rather than 2500 because of the model's
        # fixed-point conversion. See 'sensor-value-quantisation'.
        if echo "$out" | grep -qE "CHECK sensor 2[45][0-9][0-9]"; then
            echo "  ok       the Si7021 answers over I2C"
        else
            echo "  FAILED   the Si7021 did not answer over I2C"
            problems=$((problems + 1))
        fi

        # The value printed after the CHECK ledstate label, and only that.
        # Matching "True" anywhere in Renode's output would pass on any
        # unrelated line containing the word, which is not a check at all.
        #
        # Carriage returns are stripped first. Renode's console writes this
        # line as "CHECK ledstate\r\r", so an anchored match for the bare
        # label finds nothing -- which passed on Windows, where the reader
        # trimmed whitespace anyway, and failed on Linux.
        ledstate=$(echo "$out" | tr -d '\r' | \
                   sed -n '/^CHECK ledstate$/,$p' | \
                   sed '1d' | grep -v '^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]' | \
                   grep -v '^[[:space:]]*$' | head -1 | tr -d '[:space:]')
        if [ "$ledstate" = "True" ]; then
            echo "  ok       the simulator sees the LED lit"
        else
            echo "  FAILED   the simulator does not see the LED lit"
            echo "           the pin reported '${ledstate:-nothing}', expected True"
            problems=$((problems + 1))
        fi
    fi
    echo
fi

# --- Verdict ----------------------------------------------------------------

if [ "$problems" -eq 0 ]; then
    echo "Ready. Your machine builds and runs this board correctly."
    exit 0
fi

if [ "$problems" -eq 1 ]; then
    echo "Not ready: 1 thing is missing, named above."
else
    echo "Not ready: $problems things are missing, named above."
fi
echo "Fix what is named above and run this again. Nothing here needs administrator rights."
exit 1
