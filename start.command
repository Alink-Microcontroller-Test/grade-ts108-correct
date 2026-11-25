#!/bin/sh
# Double-click this to start the course on macOS.
#
# The .command extension is what makes a shell script double-clickable there:
# Finder opens it in Terminal. The work is in tools/start.sh, beside the rest
# of the tooling, so that this file and start.cmd are the same shape -- two
# entry points, one implementation each, nothing clever in either.
#
# On Linux, run tools/start.sh directly. Nothing stops this file working
# there, but no desktop treats .command as runnable.
exec "$(dirname "$0")/tools/start.sh" "$@"
