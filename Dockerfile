# The course toolchain in one image: the cross-compiler and the simulator.
#
# This is the route for machines that cannot use the extracted archives, and
# the only route for Intel Macs, which Renode no longer publishes a build for.
# It is maintained and tested rather than tolerated -- see ADR-0014.
#
# Built for both amd64 and arm64. Antmicro's own image is amd64 only, which
# runs under emulation on Apple silicon; this one runs natively on both.
#
#   docker build -t nucleo-f401re .
#   docker run --rm -it -v "$PWD:/work" -p 8000:8000 -p 9001:9001 nucleo-f401re

FROM debian:12-slim

# python3-pytest is here for the verification sweep, not for a learner. The
# sweep runs inside this image on every push -- that is the point of running
# it here rather than on the runner -- and one of the things it runs is the
# unit tests. Without pytest that check failed on every push from 2026-09-29,
# and said nothing about why: pytest's "No module named pytest" goes to
# stderr, and the check only reported stdout.
#
# git is here for two things that both went quiet without it, and it is the
# same lesson twice.
#
# tools/check_encoding.py asks git which files are tracked. With no git it
# reports that it could not ask and exits 0, which is right -- a check that
# cannot run must not fail a build -- but this image is the standard route a
# learner builds by (ADR-0016). So the one environment where most learners
# would meet the check was the one where it did nothing, and a learner on
# Japanese Windows whose editor saved Shift-JIS would have been told nothing
# at all.
#
# The file-mode guard in tests/sweep.py had already been neutered the same
# way, and sweep.yml says so: "Running them inside meant git was missing and
# the mode check quietly skipped itself -- which is how a guard becomes
# decoration." That guard still runs on the runner, because it also needs the
# network, which this image does not have.
#
# A learner needs git to have cloned this repository, so nothing is being
# asked of a managed machine that it was not asked for already (ADR-0014).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git xz-utils libicu72 python3 python3-pytest \
    && rm -rf /var/lib/apt/lists/*

# Installing git is not enough on its own. Inside this image we are root, and
# the checkout at /work belongs to whoever mounted it -- a learner on their
# own machine, or the Actions runner. Git 2.35 refuses to read a repository
# owned by another user and exits non-zero, which would leave the encoding
# check reporting "not a git checkout" about a checkout that is plainly
# there, and would have made installing git look like it had worked while
# changing nothing.
#
# Scoped to /work rather than '*', because /work is the only path this is
# needed for: SETUP.md mounts there on all three platforms, the header above
# mounts there, and the sweep runs with -w /work.
RUN git config --system --add safe.directory /work

# Keep these equal to versions.env. The environment check inside the container
# reads that file and will warn if they drift apart.
ARG RENODE_VERSION=1.16.1
ARG ARM_GCC_VERSION=14.2.rel1

# Renode publishes one build per architecture, and both unpack to the same
# directory name, so only the file name differs.
RUN arch="$(uname -m)" && \
    case "$arch" in \
      x86_64)  file="renode-${RENODE_VERSION}.linux-portable-dotnet.tar.gz" ;; \
      aarch64) file="renode-${RENODE_VERSION}.linux-arm64-portable-dotnet.tar.gz" ;; \
      *) echo "no Renode build published for $arch" >&2; exit 1 ;; \
    esac && \
    curl -fL -o /tmp/renode.tar.gz \
      "https://github.com/renode/renode/releases/download/v${RENODE_VERSION}/${file}" && \
    tar -xzf /tmp/renode.tar.gz -C /opt && \
    rm /tmp/renode.tar.gz

ENV PATH="/opt/renode_1.16.1-dotnet_portable:${PATH}"

# The Arm toolchain is also published per architecture.
RUN arch="$(uname -m)" && \
    case "$arch" in \
      x86_64)  host="x86_64" ;; \
      aarch64) host="aarch64" ;; \
      *) echo "no Arm toolchain published for $arch" >&2; exit 1 ;; \
    esac && \
    file="arm-gnu-toolchain-${ARM_GCC_VERSION}-${host}-arm-none-eabi.tar.xz" && \
    curl -fL -o /tmp/gcc.tar.xz \
      "https://developer.arm.com/-/media/Files/downloads/gnu/${ARM_GCC_VERSION}/binrel/${file}" && \
    mkdir -p /opt/arm-gcc && \
    tar -xJf /tmp/gcc.tar.xz -C /opt/arm-gcc --strip-components=1 && \
    rm /tmp/gcc.tar.xz

ENV PATH="/opt/arm-gcc/bin:${PATH}"

# Fetch the chip's register description once, here, instead of once per start.
#
# Renode's own platforms/cpus/stm32f4.repl ends with
#
#     ApplySVD @https://dl.antmicro.com/projects/renode/svd/STM32F40x.svd.gz
#
# and boards/nucleo_f401re.repl inherits it with `using`. So every simulation a
# learner ran fetched 72 KB over the network before the board existed. Measured
# 2026-11-11 inside this image: 2 to 11 seconds depending on the connection.
#
# The seconds are not the reason. The reason is that this is a network round
# trip on a machine whose network we do not control, and these are managed
# corporate laptops -- the whole premise of ADR-0016. An absent network fails
# fast; a proxy that accepts the connection and never answers does not, and a
# learner would be watching a board that has not appeared yet with nothing
# saying why.
#
# Renode caches what it downloads under ~/.config/renode, and that cache is
# part of the image once it is written here, so no start fetches it again.
# Warmed through Renode's own platform file rather than the board's, because no
# sources are copied into this image -- the SVD is the same either way, and
# this is the file that names it.
#
# Not a new dependency: the simulation runs perfectly without the SVD, which
# only decorates register names in the log. Verified with --network none, which
# is also how the reload test takes its measurements. This removes a dependency
# from every start rather than adding one.
RUN renode --console --disable-xwt --plain \
      -e 'mach create "warm"' \
      -e 'machine LoadPlatformDescription @platforms/cpus/stm32f4.repl' \
      -e quit \
    && test -s "$HOME/.config/renode/binaries_index"

# The board view is served by Renode over this port. Publish it and open the
# page in a browser on the host.
# 8000 serves the drawing; 9001 carries the live data it needs. Mapping
# only 8000 gives a page that loads and then shows an empty board, which
# reads as the drawing being broken rather than as a missing port.
EXPOSE 8000 9001

WORKDIR /work

# No sources are copied in. The learner's repository is mounted at /work, so
# their edits take effect without rebuilding the image.

# Start the course, not a shell.
#
# This is a breaking change for anything that ran this image expecting bash.
# The shell is still here and still reachable by naming it --
#
#     docker run --rm -it -v "${PWD}:/work" -p 8000:8000 -p 9001:9001 nucleo-f401re bash
#
# with both ports, because somebody in that shell is likely to start the
# simulator by hand, and a board view reachable on one port only loads and then
# shows nothing.
#
# -- and SETUP documents that under troubleshooting. What changes is that a
# learner is no longer asked to type anything: board.resc loads the board,
# loads the setup self-test, starts the simulator and serves the board view,
# and the environment check reports itself onto that page.
#
# `-e "i @board.resc"` and not `renode board.resc`. Naming the script
# positionally runs it before any -e, which is the documented trap at the top
# of board.resc: $bin is then set too late and the board silently comes up
# running firmware nobody asked for. The learner never types this line now,
# but the line still has to be right, and it is the same mistake either way.
#
# Through a script in the repository rather than straight to the simulator,
# because something has to happen first: the environment check builds
# verify/verify.elf, which board.resc loads, and without it board.resc stops
# at the failed load and no board view is ever served. tools/container-start.sh
# carries the reasoning and the measurement.
#
# In the mount rather than in the image, so it can be read and corrected in
# the same place as everything else a learner runs, and so it is the version
# their checkout actually has.
#
# Renode expects a terminal, so `docker run` needs -it. Without it the
# simulator reads EOF on stdin and quits a second after starting: the log ends
# "Machine paused / Disposed" and the container stops with nothing saying why.
# The launcher passes -it, and SETUP's troubleshooting says so.
# Named through /bin/sh rather than run directly, so starting the course does
# not depend on an executable bit arriving intact through a bind mount from a
# machine where git sets core.filemode=false. The bit is set in git as well --
# tests/sweep.py insists, having watched ten CI runs fail with exit 126 over
# exactly that -- but nothing a learner does should rest on it.
CMD ["/bin/sh", "./tools/container-start.sh"]
