# Setting up without a container

The standard route is the container: [`SETUP.md`](SETUP.md). Use this one if
you cannot.

It needs **no Docker, no administrator rights, no firmware setting and no
licence**. You download two archives, extract them, and add them to your
`PATH`. Nothing is installed into your system, so this works on a locked-down
work laptop where the container route does not.

There is one machine it does *not* cover — see [Intel Macs](#intel-macs).

Allow about fifteen minutes.

> This document has a Japanese version:
> [`NATIVE-SETUP.ja.md`](NATIVE-SETUP.ja.md). Update both together.

---

## 1. Get the code

```
git clone https://github.com/<your organisation>/<your repository>.git
cd <your repository>
```

Accept your teacher's invitation before you clone, signed in as the same GitHub
account you gave them.

**Clone before the next steps**, not after: the check in step 4 is a script
inside this repository.

## 2. Get the compiler

Download the **Arm GNU Toolchain** for your system from
[Arm's download page](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads).
Choose the `arm-none-eabi` build — that is the one producing code for
microcontrollers rather than for your own computer.

Extract it somewhere you will remember, then add its `bin` directory to your
`PATH`.

The version this course is verified against is in
[`versions.env`](versions.env). A close version is normally fine; step 4 tells
you if yours differs.

## 3. Get the simulator

Download **Renode** from
[its release page](https://github.com/renode/renode/releases/tag/v1.16.1), and
take the **portable** archive rather than the installer. Portable means
extract-and-run, with nothing written into your system.

| Your system | Take |
| --- | --- |
| Windows | `renode-1.16.1.windows-portable-dotnet.zip` |
| macOS, Apple silicon | `renode-1.16.1-dotnet.osx-arm64-portable.dmg` |
| macOS, Intel | see [Intel Macs](#intel-macs) |
| Linux | `renode-1.16.1.linux-portable.tar.gz` |

These are the exact names on the release page, checked against it. There are
several similar ones — take the row for your system and ignore the rest.

Extract it, then either add it to your `PATH` or set a `RENODE` environment
variable pointing at the `renode` program inside it. On Windows the zip
extracts to a folder called `renode_1.16.1-dotnet_portable`, and the program
inside it is `renode.exe`, so setting `RENODE` to
`...\renode_1.16.1-dotnet_portable\renode.exe` is the least fiddly way.

The Linux archive was tested on a machine holding nothing but `curl`: it needs
no Mono, no .NET and no extra libraries.

**Use this version.** The board description builds on a file that comes from
inside Renode, so a different version can change how the board behaves without
anything in your code changing.

## 4. Check it worked

**Windows**

```
powershell -ExecutionPolicy Bypass -File tools\check-environment.ps1
```

**macOS and Linux**

```
./tools/check-environment.sh
```

This looks for each tool and reports the version found, then builds a small
self-test and runs it on the simulated board — so you know the two work
*together*.

A working machine ends with:

```
Ready. Your machine builds and runs this board correctly.
```

## 5. Start the first exercise

Go to [`exercises/README.md`](exercises/README.md), and read
[`DIVERGENCES.md`](DIVERGENCES.md) before trusting anything you write to run on
real hardware.

---

## Intel Macs

**This route does not work on an Intel Mac.** Renode publishes no build for
them at the version this course uses: 1.16.1 ships only `osx-arm64`. The last
release with an Intel macOS package was 1.16.0. And Rosetta cannot help — it translates Intel software to run on
Apple silicon, not the other way round.

Use the container route instead: [`SETUP.md`](SETUP.md).

Check which Mac you have with:

```
uname -m
```

`arm64` is Apple silicon and can use this route. `x86_64` is Intel and cannot.

## If you get stuck

**The check says the compiler is missing, but I extracted it.** Its `bin`
directory is probably not on your `PATH`. Open a new terminal after changing
`PATH` — an already-open one keeps the old value.

**The check says the simulator is missing.** Set `RENODE` to the full path of
the `renode` program inside the extracted folder, rather than relying on
`PATH`.

**The check warns that my Renode version differs.** It will still run. If the
board then behaves oddly, suspect this first.

**Everything passes but my own program misbehaves.** Then the problem is in
your code rather than your setup, which is what this check exists to establish.
