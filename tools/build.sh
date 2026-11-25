#!/bin/sh
# Build one exercise.
#
#   ./tools/build.sh exercises/01-blink-with-a-delay
#
# Produces firmware.elf inside that directory.
#
# A learner does not normally run this. The board view's "Build and run an
# exercise" calls this same script and then loads what it produced -- the same
# script the course's grading runs, which is why a local result and a graded
# one cannot disagree about whether the code compiles.
#
# What follows is for the route without a container, which NATIVE-SETUP.md
# documents, and for anyone driving the simulator by hand:
#
#   renode --console -e '$bin=@exercises/01-blink-with-a-delay/firmware.elf' -e 'i @board.resc'
#
# Both parts as -e, in that order, and single-quoted. Renode runs a script
# named on the command line before any -e, so board.resc first sets $bin
# too late; double quotes let the shell eat $bin before Renode sees it.
# Either way board.resc falls back to the setup self-test and the board
# comes up running firmware you did not ask for, without saying so.
#
# For Windows, tools\build.ps1 does the same thing.

set -u

here=$(dirname "$0")
root=$(cd "$here/.." && pwd)

# THE EXIT CODES MEAN SOMETHING.
#
#   0  built
#   1  the compiler ran and rejected the code
#   2  the build could not be attempted at all
#
# The same three the course's checks use, and for the same reason. The
# grader turns a non-zero build into "your code does not compile" and
# asks the assistant for a hint about it, so a missing compiler used to
# tell every learner in that run that their code was broken and then
# invent advice about it. Exit 2 is how this script says "not their
# fault" (ADR-0021's shape: report the real problem, do not dress it up
# as somebody else's).

if [ $# -lt 1 ]; then
    echo "Which exercise? For example:"
    echo "  ./tools/build.sh exercises/01-blink-with-a-delay"
    echo
    echo "Available:"
    ls -1 "$root/exercises" 2>/dev/null | sed 's/^/  exercises\//'
    exit 2
fi

target=$1
[ -d "$target" ] || target="$root/$1"

if [ ! -f "$target/main.c" ]; then
    echo "No main.c in $1"
    exit 2
fi

# Encoding before compiler. A Shift-JIS byte reaches the compiler as a
# puzzle and reaches a Makefile as a line continuation that swallows the
# next line, so this runs first and says which file and which byte.
# "command -v python3" is not enough. On Windows, Git Bash finds the
# Microsoft Store alias stub, which prints "Python was not found" and
# exits non-zero -- so the line below would stop the build for a reason
# that has nothing to do with encodings. Exit 2 here means "could not be
# attempted", which the grader records as the course's own defect, for
# every exercise of every learner. Found on a Windows machine before it
# could reach anybody. So each candidate is asked to run something
# trivial before it is believed.
for py in python3 python; do
    command -v "$py" > /dev/null 2>&1 || continue
    "$py" -c "" > /dev/null 2>&1 || continue

    # Held back unless it finds something. The check also says when it was
    # skipped -- in a tree that was unpacked rather than cloned, which is
    # every tree the teacher's grading run builds in -- and that note would
    # otherwise be prepended to the compiler output of every exercise that
    # failed to compile, which is the text handed to the assistant and
    # recorded in the ledger. Run the check on its own to see the note.
    encoding=$("$py" "$root/tools/check_encoding.py" "$root" 2>&1) || {
        printf '%s\n' "$encoding"
        exit 2
    }
    break
done

if ! command -v arm-none-eabi-gcc > /dev/null 2>&1; then
    echo "arm-none-eabi-gcc is not on PATH, so nothing can be built."
    echo "This is not a problem with the code in $1."
    echo "Inside the course container the compiler is already there; run"
    echo "tools/check-environment.sh to see what is missing."
    exit 2
fi

# soft float: these exercises need no floating point, and hard float would
# require enabling the FPU before main. The device has one -- see
# boards/nucleo_f401re.repl -- it is simply not switched on here.
arm-none-eabi-gcc \
    -mcpu=cortex-m4 -mthumb -mfloat-abi=soft \
    -Og -g -Wall -Wextra \
    -ffreestanding -nostdlib \
    -DSTM32F401xE \
    -I "$root/lib/cmsis" \
    -T "$root/lib/linker.ld" \
    -o "$target/firmware.elf" \
    "$root/lib/startup.c" "$target/main.c" || exit 1

echo "Built $1/firmware.elf"
arm-none-eabi-size "$target/firmware.elf"
