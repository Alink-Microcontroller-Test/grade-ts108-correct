#!/bin/sh
# Start the course. macOS and Linux.
#
# The learner double-clicks start.command in the repository root, which runs
# this. Everything the old SETUP asked them to type happens here instead: the
# container pre-flight, the port check, the image build on a first run, the
# container itself, and the browser.
#
# Reports and stops rather than working around. Whether a learner can run a
# container at all depends on their employer's policy and their machine, and
# no testing of ours settles that in advance (ADR-0014, ADR-0016). What we can
# do is make the failure say which of the few possible reasons it is, in a
# window still on screen when they read it.
#
# For Windows, tools/start.ps1 does the same thing.

set -u

here=$(dirname "$0")
root=$(cd "$here/.." && pwd)
image=nucleo-f401re
name=nucleo-f401re-board
page_port=8000
data_port=9001
url="http://localhost:$page_port/"

cd "$root"

remove_secret() {
    # The credential file, gone. Called on every way out, because leaving a
    # learner's token in their temp directory would be a worse outcome than
    # the board not starting.
    [ -n "${secret:-}" ] && rm -f "$secret"
    return 0
}

stop_with_reason() {
    remove_secret
    echo
    echo "---------------------------------------------------------------"
    printf '%s\n' "$1"
    echo "---------------------------------------------------------------"
    echo
    echo "Press Enter to close this window."
    read _ignored 2>/dev/null || true
    exit 1
}

# 1. Can this machine run a container at all? check-container.sh exists to
#    answer that and to say which reason applies.
echo "Checking that this machine can run the course container."
COURSE_LAUNCHER=1
export COURSE_LAUNCHER
if ! "$root/tools/check-container.sh"; then
    stop_with_reason "The container runtime is not usable on this machine. What is wrong is named above."
fi

# 2. Both ports, before anything starts.
#
#    Port 8000 is a common one. While a learner typed the start command
#    themselves a clash was an error in front of them; now that this script
#    owns that command the message could scroll past. And a board view
#    reachable on one port but not the other loads and then shows an empty
#    board, which reads as the drawing being broken rather than as a port
#    being taken -- so both are checked and neither is worked around.
port_in_use() {
    if command -v lsof > /dev/null 2>&1; then
        lsof -nP -iTCP:"$1" -sTCP:LISTEN > /dev/null 2>&1 && return 0
        return 1
    fi
    # No lsof: say so rather than report a free port we did not check.
    return 2
}

for port in "$page_port" "$data_port"; do
    port_in_use "$port"
    case $? in
        0) stop_with_reason "Something on this machine is already using port $port, which the board view needs.

Close whatever is using it and run this again. It is often another
development server." ;;
        2) echo "  note     lsof is not here, so the ports were not checked." ;;
    esac
done

# 3. The image. Built here on a first run, which takes minutes and downloads a
#    cross-compiler and a simulator -- said out loud, because silence reads as
#    a hung window and a learner who closes it is left with a half-built image.
if ! docker image inspect "$image" > /dev/null 2>&1; then
    echo
    echo "Building the course container. This happens once."
    echo "It downloads a compiler and a simulator, so it takes a few minutes."
    echo "Later starts are immediate. Please leave this window open."
    echo
    if ! docker build -t "$image" "$root"; then
        stop_with_reason "The course container could not be built. The reason is above."
    fi
fi

# 3a. The learner's own credential, if their clone left one.
#
#     Nothing is minted and nothing is stored. This asks git for the
#     credential it already uses for their repository, so a learner who
#     cloned over HTTPS does nothing at all and the course never holds a
#     credential of its own (ADR-0044).
#
#     Returning nothing is ordinary rather than a failure: an SSH clone has
#     none, and neither does a helper git cannot read back from. The board
#     still starts and the fetch control says why it is unavailable.
#
#     Both prompts are off, so this can never stop and ask. A launcher that
#     opened a password prompt on startup would be worse than one that
#     quietly did without.
secret=""
remote=$(git -C "$root" remote get-url origin 2>/dev/null || true)
token=""
if [ -n "$remote" ]; then
    token=$(printf 'url=%s\n\n' "$remote" |
            GIT_TERMINAL_PROMPT=0 git -c credential.interactive=false \
                -c credential.modalPrompt=false credential fill 2>/dev/null |
            sed -n 's/^password=//p' | head -1)
fi

if [ -n "$token" ]; then
    # A file, never an environment variable: an environment variable sits in
    # `docker inspect` for the container's whole life, readable by anything
    # that can reach the daemon.
    secret=$(mktemp "${TMPDIR:-/tmp}/nucleo-f401re-gh.XXXXXX")
    chmod 600 "$secret"
    printf '%s' "$token" > "$secret"
    token=""
    echo "Using the GitHub credential your clone already has."
else
    echo "No GitHub credential found, so the board cannot fetch builds."
    echo "Everything else works; you can drop a downloaded build in instead."
fi

# 4. Start it.
#
#    Detached first, so the browser can be opened once the board answers, and
#    attached afterwards so the simulator's output is on screen and Ctrl-C
#    reaches it. `-it` is not optional: without a terminal the simulator reads
#    EOF on stdin and quits a second after starting, leaving only
#    "Machine paused / Disposed" in a log nobody is looking at.
docker rm -f "$name" > /dev/null 2>&1 || true
echo "Starting the board."
set -- -dit --rm --name "$name" \
       -v "$root:/work" \
       -p "$page_port:8000" -p "$data_port:9001"
if [ -n "$secret" ]; then
    # Read-only, at the path the plugin knows. Removed when the board stops
    # and not before: a bind-mounted file that vanishes from the host takes
    # the mount with it.
    set -- "$@" -v "$secret:/run/secrets/gh:ro"
fi
if ! docker run "$@" "$image" > /dev/null; then
    stop_with_reason "The container would not start. The reason is above."
fi

# 5. Wait for the board view to answer, then open it. Polled rather than
#    slept: a fixed wait is the kind of thing that works on the machine it was
#    written on and fails on a cold laptop.
echo "Waiting for the board view."
ready=0
attempt=0
while [ "$attempt" -lt 90 ]; do
    if curl -s -o /dev/null --max-time 2 "$url"; then
        ready=1
        break
    fi
    if [ -z "$(docker ps -q -f "name=$name")" ]; then
        echo
        docker logs "$name" 2>&1 || true
        stop_with_reason "The board stopped before it finished starting. Its output is above."
    fi
    attempt=$((attempt + 1))
    sleep 1
done

if [ "$ready" -eq 1 ]; then
    echo "Opening $url"
    if command -v open > /dev/null 2>&1; then
        open "$url"
    elif command -v xdg-open > /dev/null 2>&1; then
        xdg-open "$url" > /dev/null 2>&1 &
    else
        echo "  note     no browser opener here; open $url yourself."
    fi
else
    echo
    echo "The board view did not answer in time. Try opening $url yourself."
fi

echo
echo "The board is running. To stop it, type  quit  at the prompt below."
echo
echo "Ctrl-C does not exit: Renode takes it as 'pause the board', and"
echo "'start' resumes. That is Renode's own behaviour, not ours."
echo
if ! docker attach "$name"; then
    # Attaching needs a terminal. Double-clicked there is one, but this may
    # also be run from somewhere without -- a pipe, a task runner, a CI step.
    # The board is running either way, so say how to stop it rather than
    # leaving it with no visible means of being stopped.
    echo
    echo "This window could not attach to the board, so the board is running"
    echo "in the background instead. It still works: open $url"
    echo
    echo "To stop it:   docker stop $name"
fi

# Whatever ended the attach -- `quit`, a detach, a dropped connection -- the
# container must not be left running. It holds both ports, and the next start
# would stop on the port check with nothing to suggest the cause was the last
# session. `--rm` only cleans up once it has actually stopped.
docker stop "$name" > /dev/null 2>&1 || true
remove_secret
