#!/bin/sh
# Work out whether this machine can run the course container, and if it
# cannot, say which of the few possible reasons it is.
#
# For macOS and Linux. Windows has check-container.ps1.
#
#   ./tools/check-container.sh
#
# This runs on your own machine, NOT inside the container -- if the container
# will not start, you cannot get inside it to ask why. Once you are inside,
# tools/check-environment.sh is the one to run.
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

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

system=$(uname -s 2>/dev/null || echo unknown)
arch=$(uname -m 2>/dev/null || echo unknown)

echo "Checking whether this machine can run the course container."
echo
echo "  machine  $system $arch"
echo

# --- The Intel Mac exception ------------------------------------------------
#
# Everywhere else the container is the standard route and the archive is the
# fallback. Here they swap: the archive route needs a Renode build for this
# platform that does not exist, so the container is the only way.

intel_mac=no
if [ "$system" = "Darwin" ] && [ "$arch" = "x86_64" ]; then
    intel_mac=yes
fi

# --- Is there a runtime at all ----------------------------------------------

runtime=""
for candidate in podman docker; do
    if command -v "$candidate" >/dev/null 2>&1; then
        runtime=$candidate
        break
    fi
done

if [ -z "$runtime" ]; then
    echo "  MISSING  no container runtime"
    echo "           Neither podman nor docker is installed, or neither is on"
    echo "           your PATH."
    echo
    echo "           Podman is the one to install: it is free for everyone and"
    echo "           has no company-size licence condition."
    echo "           https://podman.io"
    echo
    if [ "$intel_mac" = "yes" ]; then
        echo "           On an Intel Mac the container is the ONLY route. The"
        echo "           archive route in NATIVE-SETUP.md cannot work here,"
        echo "           because there is no simulator build for this platform."
        echo "           If you cannot install a runtime, say so early -- this"
        echo "           one needs somebody else to solve."
    else
        echo "           If you cannot install either -- some employers do not"
        echo "           permit it -- use NATIVE-SETUP.md instead. It needs no"
        echo "           container and no administrator rights."
    fi
    exit 1
fi

echo "  found    $runtime"
echo "           $($runtime --version 2>/dev/null | head -1)"
echo

# --- It is installed. Does it actually run anything? ------------------------
#
# Installed and working are different things, and the gap between them is
# where almost everybody gets stuck: the command exists, and the service
# behind it will not start.

if info=$("$runtime" info 2>&1); then
    echo "  ok       $runtime is running"
    echo
    if [ "$runtime" = "docker" ]; then
        echo "NOTE: Docker Desktop requires a paid subscription for companies"
        echo "above 250 employees or \$10M revenue. Podman has no such"
        echo "threshold and runs this course identically. If a licence prompt"
        echo "appears, that is what it is about -- switch rather than buy."
        echo
    fi
    # SELinux relabels bind mounts, and a container is refused a volume it
    # has no label for. On Fedora, RHEL and their derivatives the mount in
    # SETUP.md fails with permission denied on files the learner can read
    # perfectly well themselves, and the message does not mention SELinux at
    # all -- so the one clue points nowhere near the cause. Said here rather
    # than left to be discovered. getenforce does not exist on macOS or on
    # Debian-family Linux, so this is silent everywhere it does not apply.
    if command -v getenforce >/dev/null 2>&1 &&
       [ "$(getenforce 2>/dev/null)" = "Enforcing" ]; then
        echo "NOTE: SELinux is enforcing here. Add ':z' to the volume in"
        echo "every run command, so that"
        echo
        echo "  -v \"\$PWD:/work\""
        echo
        echo "becomes"
        echo
        echo "  -v \"\$PWD:/work:z\""
        echo
        echo "Without it the container is denied access to files you can read"
        echo "yourself, and nothing in the error says SELinux."
        echo
    fi

    # The next step is only worth saying to somebody who ran this
    # themselves. The launcher runs this check too, and telling a learner to
    # build an image the launcher is about to build -- or has built -- is
    # advice they should not follow. COURSE_LAUNCHER is how it says so.
    if [ -z "${COURSE_LAUNCHER:-}" ]; then
        echo "Ready. Start the course by double-clicking start.command"
        echo "(macOS) in the folder you cloned, or by running tools/start.sh."
    else
        echo "Ready."
    fi
    exit 0
fi

echo "  FAILED   $runtime is installed but will not run"
echo

# Classify it. These are ordered by how often they are the answer, and each
# says who can fix it -- which is the part a learner actually needs, because
# two of the three are not theirs to fix.
case "$info" in
    *[Pp]ermission*denied*|*permission*)
        echo "           Permission. Your user is probably not allowed to talk"
        echo "           to the service."
        echo
        echo "           On Linux with Docker this means you are not in the"
        echo "           'docker' group. Podman does not need one and is the"
        echo "           quicker fix if you cannot change groups."
        ;;
    *[Ll]icen*|*subscription*)
        echo "           A licence. Docker Desktop is chargeable above a"
        echo "           company-size threshold."
        echo
        echo "           Podman has no such threshold and runs this course"
        echo "           identically. Install it rather than buying anything."
        echo "           https://podman.io"
        ;;
    *)
        echo "           The service is not responding. On a work machine this"
        echo "           is almost always one of two things:"
        echo
        echo "             - hardware virtualisation is switched off in the"
        echo "               firmware. ONLY AN ADMINISTRATOR CAN CHANGE THIS."
        echo "             - the runtime's own service or virtual machine has"
        echo "               not been started yet. Try starting it by hand"
        echo "               first; on macOS with Podman that is"
        echo "               'podman machine start'."
        echo
        echo "           What it reported:"
        printf '%s\n' "$info" | head -6 | sed 's/^/             /'
        ;;
esac

echo
if [ "$intel_mac" = "yes" ]; then
    echo "On an Intel Mac the container is the ONLY route -- the archive route"
    echo "in NATIVE-SETUP.md cannot work here, because there is no simulator"
    echo "build for this platform. This one has to be solved rather than"
    echo "worked around, so raise it early."
else
    echo "You do not have to solve this. NATIVE-SETUP.md is a second route"
    echo "that needs no container and no administrator rights. It is more"
    echo "steps, and it works."
fi
exit 1
