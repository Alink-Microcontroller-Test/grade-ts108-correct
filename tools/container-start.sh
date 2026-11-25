#!/bin/sh
# What the course container starts. Not a shell: the learner types nothing.
#
# The order here is load-bearing, and not merely as a pre-flight.
# tools/check-environment.sh BUILDS verify/verify.elf, and board.resc loads
# that file. It is a build artifact -- .gitignore excludes *.elf -- so a fresh
# clone does not have one, and in Renode a command that fails abandons every
# remaining line of the script it is in. So on a fresh clone the load failed,
# board.resc stopped there, the plugin was never included, the board view was
# never served, and the container sat there reporting "Up" while
# http://localhost:8000 answered nothing at all. The reason was in a log
# nobody had been given a reason to read.
#
# Measured 2026-11-11, by hiding verify/verify.elf and starting the container.
#
# So the check runs first. It is what makes the board possible, as well as what
# says whether this machine can build and run the course; vis/vis_f401re.py
# publishes its report to the board view through the variables exported below.
#
# For macOS and Linux, which is every container. The native route has no need
# of this: there, a learner runs the check themselves and starts the simulator
# themselves, and NATIVE-SETUP.md says so.

set -u

here=$(dirname "$0")
root=$(cd "$here/.." && pwd)
cd "$root"

report=/tmp/course-environment.txt

echo "Checking this environment before starting the board."
echo

status=0
./tools/check-environment.sh > "$report" 2>&1 || status=$?
cat "$report"
echo

# A board cannot run firmware that could not be compiled. Where that is the
# case there will also be no board view to carry the explanation, so this is
# said here, in the one place a learner can still see it.
if [ ! -f "$root/verify/verify.elf" ]; then
    echo "---------------------------------------------------------------"
    echo "The self-test firmware was not built, so the board cannot start."
    echo "What is missing is named above. This is not a problem with the"
    echo "code you have written."
    echo "---------------------------------------------------------------"
    echo
fi

COURSE_ENVIRONMENT_REPORT="$report"
COURSE_ENVIRONMENT_STATUS="$status"
export COURSE_ENVIRONMENT_REPORT COURSE_ENVIRONMENT_STATUS

# `-e "i @board.resc"`, never `renode board.resc`. Naming the script
# positionally runs it before any -e, and board.resc spends twenty lines
# explaining what that does and how quietly it does it. The learner no longer
# types this line, but the line still has to be right.
exec renode --console --disable-xwt --plain -e "i @board.resc"
