# Setting up

Everything you need — the compiler and the simulator — comes in one container
image. You install a container runtime, then double-click one file. That is
the whole setup — it builds the image the first time and starts the board every
time, and there is nothing to type. Your own copy of the course is mounted into
it, so you edit files normally on your own machine.

Allow about twenty minutes, most of it waiting for one download.

> This document has a Japanese version: [`SETUP.ja.md`](SETUP.ja.md). Update
> both together.
>
> If you cannot use a container on your machine, there is a second route that
> needs no Docker at all: [`NATIVE-SETUP.md`](NATIVE-SETUP.md).

---

## 1. Get a container runtime

Either of these works. **Check with whoever manages your computer before
installing one**, because this is the step most likely to need permission you
do not have.

| | |
| --- | --- |
| **[Podman](https://podman.io)** | Free for everyone, no licence question. Prefer this one |
| **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** | Requires a paid subscription for companies above 250 employees or $10M revenue |

Everywhere below says `docker`. If you chose Podman, type `podman` instead —
the commands are otherwise identical.

Both need hardware virtualisation enabled in your computer's firmware. On most
machines it already is. If the runtime refuses to start and says something
about virtualisation, that is a setting only an administrator can change — see
[If you get stuck](#if-you-get-stuck).

Once you have installed one, this says whether it actually works here, and if
it does not, which of the few possible reasons it is:

**Windows**

```
powershell -ExecutionPolicy Bypass -File tools\check-container.ps1
```

**macOS and Linux**

```
./tools/check-container.sh
```

Run it on your own machine, not inside the container — if the container will
not start, you cannot get inside it to ask why. It will tell you whether the
thing blocking you is something you can fix yourself or something only an
administrator can, and point you at the second route if it is the latter.

## 2. Get the code

```
git clone https://github.com/<your organisation>/<your repository>.git
cd <your repository>
```

Your teacher will have sent you an invitation to this repository. Accept it
before you clone, signed in as the same GitHub account you gave them.

GitHub expires an invitation seven days after it is sent. If yours has
already gone, the course notices and sends one more by itself, so wait for
the second rather than asking for it. If that one expires too, nothing
further is sent automatically and your teacher is told — usually it means the
account name they were given is not quite right.

## 3. Start it

Double-click **`start.cmd`** on Windows, or **`start.command`** on macOS, in
the folder you have just cloned.

That is the setup. There is nothing to type.

The first start builds the image, which downloads the compiler and the
simulator and takes a few minutes — leave the window open while it does.
Every start after that takes seconds.

What it does, so none of it is a surprise: checks this machine can run a
container at all, checks nothing else is using the two ports the board view
needs, builds the image if it is not there yet, starts the board, waits until
the board view answers, and opens it in your browser. If any of that fails it
stops, says which of the few possible reasons it is, and waits for you to
press Enter so the message is still on screen when you read it.

**On Linux**, run `tools/start.sh` instead. Nothing stops `start.command`
working there, but no Linux desktop treats the extension as runnable.

## 4. Your first exercise

The board view is now open at **http://localhost:8000**, in your own browser,
outside the container. The page is served on port 8000 and the live data that
fills it on 9001; the launcher publishes both.

It opens in Japanese, like the rest of the course. For English, use the button
at its top right or open **http://localhost:8000/?lang=en**; the choice is
remembered on that browser.

**The board is already running something, and it is not your code.** It is the
setup self-test, and the page says so. Its job is to prove your compiler and
the simulator work together on this board, so that a problem later is known to
be in your code rather than in your installation. Its serial output ends

```
CHECK sensor not fitted
```

which is correct and not a fault: a real NUCLEO-F401RE carries no sensor, and
you add one yourself in exercise 4.

**To run an exercise**, use **Build and run an exercise** at the top of the
page: choose one, press the button. It compiles your code with the same build
the course uses to mark it, and loads the result onto the board. There is no
command to type and no file to move.

If it does not compile, the page says so and shows the compiler's own words.
Read the line above them first: it says whether the problem is in your code or
in the setup, and those need opposite responses.

**Nothing will blink yet, and that is correct.** The scaffolding compiles and
does nothing at all until you write the exercise. That is deliberate: it means
a compile error is something you have just introduced, not something you
inherited. The task is at the top of
[`exercises/01-blink-with-a-delay/main.c`](exercises/01-blink-with-a-delay/main.c),
and [`exercises/README.md`](exercises/README.md) covers the other three.

**A sensor reading you set is kept when you rebuild.** Loading firmware resets
every part on the board, so without this the one exercise with a sensor would
lose its reading every time you pressed build. What is put back is the number
you typed rather than the one the board reports — they differ slightly, and
restoring the reported one would drift a little further on every rebuild.

**Running what GitHub built.** A second control, **Run the build GitHub
made**, fetches the firmware your most recent push compiled on GitHub and runs
that instead — for when a result does not add up and you want the binary the
machine built rather than one you built beside it. It tells you which commit
that build came from, and says plainly when it is not the code you currently
have.

**It uses the GitHub credential your clone already has.** Nothing new is
created and nothing is kept: the launcher reads the credential git already
uses for your own repository, hands it to the board for as long as the board
is running, and deletes it afterwards. It is only ever sent to GitHub's API.
If you cloned over SSH, or your credential lives somewhere git cannot read it
back from, the control says so instead of failing — download the build
yourself and drop it on the page, which works the same way.

Before you trust anything you write to work on real hardware, read
[`DIVERGENCES.md`](DIVERGENCES.md). The simulator is more forgiving than the
board in several places, and it does not warn you.

### Stopping the board

Type `quit` at the Renode prompt in the window the launcher opened. `q` works
too.

```
(NUCLEO-F401RE) quit
```

**`Ctrl+C` does not exit Renode.** It stops the emulation and leaves you at
the prompt, where `start` resumes it. That is useful when you want the board
paused, and confusing when you wanted your terminal back.

If you close the window instead, the board carries on running in the
background and keeps holding ports 8000 and 9001 — so the next start stops
on the port check. To clear it:

```
docker stop nucleo-f401re-board
```

---

## How this fits together

**Your files stay yours.** The repository is mounted, not copied, so edit with
your usual editor on your own machine. Nothing inside the container survives
`--rm`, and that is deliberate: the container is the toolchain, not your work.

**The browser runs outside.** The container has no screen and does not need
one. Renode serves the board as a web page, and your own browser opens it over
the published port.

**Your work reaches the course by being pushed.** Building and running here
proves your own machine works. It is not how anything is submitted: nothing
you do inside the container is visible to your teacher until you push.

So the order for each exercise is push first, then look. You push; the course
builds and tests your code on the teacher's side and the AI assistant replies
on an Issue in this repository; and once that reply says the exercise passes,
you build and run it here again to watch it work. Nothing stops you building
locally whenever you like while you are working on it -- but an exercise you
never push is one nobody has checked.
[`COURSE.md`](COURSE.md) has the detail.

## If you get stuck

**`docker: command not found`.** The runtime is not installed, or not on your
`PATH`. With Podman, substitute `podman` for `docker` everywhere.

**It will not start, and mentions virtualisation.** Hardware virtualisation is
switched off in your computer's firmware. Only an administrator can change
that. If you cannot get it changed, use
[`NATIVE-SETUP.md`](NATIVE-SETUP.md) instead — it needs no container and no
administrator rights at all.

**You are told you need a licence.** Docker Desktop is chargeable above a
company-size threshold. Podman has no such threshold and runs this course
identically.

**Permission denied on Linux.** Your user is probably not in the `docker`
group. Either add it, or use Podman, which does not need one.

**Permission denied on Fedora, RHEL or similar, on files you can read
yourself.** SELinux relabels bind mounts, and the container is refused access
to the directory you mounted. Add `:z` to the volume, so `-v "$PWD:/work"`
becomes `-v "$PWD:/work:z"`, in every run command. Nothing in the error
mentions SELinux, which is why this one is hard to find on your own.
`./tools/check-container.sh` says so if SELinux is enforcing on your machine.

**Inside the container, the check says both tools are missing.** You have
almost certainly started a *login* shell — `bash -lc "..."` or `bash --login`.
A login shell reads `/etc/profile`, which replaces `PATH` and throws away the
one the image set, so the tools become invisible even though they are
installed. Use `bash -c` rather than `bash -lc`.

**You want a shell inside the container.** You should not need one —
everything a learner does is on the page — but when something is wrong and
you want to look around:

```
docker run --rm -it -v "$PWD:/work" -p 8000:8000 -p 9001:9001 nucleo-f401re bash
```

Both ports, because from there you are likely to start the simulator by hand,
and a board view reachable on one port but not the other loads and then shows
an empty board. On Windows, spell the first part `"%cd%:/work"` in Command
Prompt or `"${PWD}:/work"` in PowerShell.

**The browser shows nothing on port 8000.** The launcher publishes both `-p 8000:8000`
and `-p 9001:9001`, and that a simulation is actually running inside the
container.

**The board is drawn but has no pins, no LEDs and no readings.** That is
the one missing port. The drawing is served over 8000 and everything on
it arrives over 9001, so without the second mapping the page loads and
then stays empty.

**`cannot execute: required file not found`, and the file is plainly there.**
The script's first line ends in a carriage return, so Linux is looking for an
interpreter named `/bin/sh\r` and not finding one. A clone taken before line
endings were pinned does this on Windows. Fix it in place, from inside the
container:

```
sed -i 's/\r$//' versions.env tools/*.sh
```

If the check then reports the cross-compiler missing, that is the same fault
one file further on: `versions.env` is read by the check, and a carriage
return on the end of the compiler's name makes it look for a program nobody
has.

**`Parsing line 'sysbus LoadELF $bin' failed`, or `Parameters did not match
the signature`.** There is no `firmware.elf` to load, because the exercise has
not been built. Compiled output is not kept in the repository, so a fresh
clone has none. Press **Build and run an exercise** on the page. The message
names neither the file nor the build, which is why it is worth saying here.

**The launcher says "Something on this machine is already using port 8000".**

It stopped rather than starting a board you would not have been able to see.
Both ports matter: the page is served on 8000 and everything drawn on it
arrives over 9001, so a board started with one of them taken loads and then
shows nothing.

Three things cause it, and the first is much the commonest.

*The board from your last session is still running.* Closing the launcher
window does not stop the board — only typing `quit` does, and the window
closing is exactly what happens when somebody is finished for the day. The
board carries on holding both ports. To clear it:

```
docker stop nucleo-f401re-board
```

Then start again. Nothing is lost: your work is in your own folder, not in
the board.

*A second copy of the course is open.* Starting from two different clones
gives two boards wanting the same two ports. The same command clears it, and
only one copy can run at a time.

*Something unrelated has the port.* Port 8000 is a common choice for
development servers. To find out what:

```
netstat -ano | findstr :8000
```

on Windows, or on macOS and Linux:

```
lsof -i :8000
```

Close whatever it names, or stop it, and start again.

**To avoid all of this**, type `quit` in the launcher window when you have
finished, rather than closing it. See [Stopping the board](#stopping-the-board).

**A Python traceback ending `Address already in use`.** Another Renode is
already running in this container and holding ports 8000 and 9001. You get
this by opening a second shell with `docker exec` while the first one is
still running the simulator. Quit that one first, or stop the container and
start it again.

**The board appears and runs, but nothing your code does has any effect.**
Read the top of the page: it says what the board is running. Until you press
**Build and run an exercise** that is the setup self-test rather than anything
of yours. If it names your exercise and still nothing happens, the scaffolding
is behaving correctly — it compiles and does nothing at all until you write
the exercise.

**The build fails downloading.** The image fetches from GitHub and from Arm's
download site. A corporate proxy may block either — worth raising with whoever
manages the machine, because the other route downloads from the same two
places.

**Your result here and your grade disagree.** The grade is the one that
counts. This container, and the check that runs when you push, both use the
`tools/` in *your* repository; the grade is produced from the course's own
copy. So your two results can agree with each other and still differ from
your grade. Tell your teacher rather than assuming something is broken — the
usual cause is that your copy of `tools/` is older than the course's, which
the course checks once a day. Nobody will overwrite your files to fix it.
**You asked for feedback and nothing came.** Open **Actions** and read the
most recent run of **Ask for feedback**, or of **Check my work** if you are
being graded on every push. It always says which of these happened: the
request was sent, or today's ten are used up, or automatic grading is off
and you have not asked. None of those is a fault.

If it says the request was sent and nothing has arrived after five minutes,
tell your teacher. Your work is not lost either way — the course sweeps
twice a day and will pick it up.
