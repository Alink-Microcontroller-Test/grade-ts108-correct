# How this course works

Everything about being graded, rather than about doing an exercise. For the
exercises themselves see [`exercises/README.md`](exercises/README.md), and for
one exercise in particular, that exercise's own page.

> This document has a Japanese version: [`COURSE.ja.md`](COURSE.ja.md).

## Checking on a clean machine

Your own machine compiles these in under a second, so there is nothing to
wait for — but code sometimes builds only for you, because of a file you
never committed. To check that:

**It runs on every push**, so there is nothing to start. Watch it under
**Actions → Check my work**, or start one by hand from there with
**Run workflow** if you want to re-check without pushing.

**This is not the same as being graded.** Pushing runs this check, and
it also starts grading — your program actually run, and an explanation
written to your Issue. That is a slower, separate thing, and
[Getting your work checked](#getting-your-work-checked) covers it,
including how to turn it off.

It takes about thirty seconds. If you push again while one is running, the
older one is cancelled — only your newest push gets an answer, so you cannot
be told about code you have already replaced.

**It only checks that your code compiles.** It does not run your program, so
a green result means it built, not that it works. Whether the LED actually
blinks is something you see by running it in the simulator yourself.

**It is not your grade.** You can edit that workflow — it is in your own
repository — so nothing it reports is trusted as an assessment. Your
teacher's own run is what counts.

## Getting your work checked

Two different things look at your work, and it is worth keeping them
apart. Both start when you push, and neither needs anything pressed.

**Your own check compiles every exercise.** It answers in about ten
seconds. It does not run your program, so a green tick means your code
built, not that it works.

**Being graded runs your program.** Your teacher's side runs it in the
simulator, judges whether it does what the exercise asked, and writes
you an explanation. That takes about three minutes.

### Being graded

Push. That is the whole thing — nothing to start and nothing to press.
Grading begins within seconds and the reply arrives as a comment on your
Issue, usually about three minutes later. It looks at what you just
pushed.

**You have ten a day.** They are yours alone — nobody else's work uses
them up — and they come back at midnight.

**Every reply tells you how many are left**, on the last line of the
comment. A comment that arrives from the course's own twice-daily look
says so instead, because those cost you nothing.

If you run out, pushing again costs nothing and you are told on your
Issue, once that day however many times you push.

**You can also ask for one at any time**, from **Actions → Ask for
feedback → Run workflow**. It is the same grading out of the same ten,
and it is what to use once you have turned off grading on every push.

### A commit you did not make

Sometimes the course updates one of its own files in your repository — a
fix to the check that runs on your pushes, or to these instructions. You
will see a commit you did not write, and a run starting that you did not
begin.

The commit says so itself, in Japanese and then English: what was changed
and why that run appeared. **It costs you nothing** — none of your ten is
used, because you did not ask for anything.

That run reports whatever is in your code at that moment, so it can be red
for something you were halfway through. It is not a grade and it is not a
judgement on the change the course made. Your own work is never touched:
the course only replaces its own files, never the exercises you are
writing.

### Turning it off, and back on

To stop being graded on every push, delete `.grade-on-push` from the top
level of this repository:

```
git rm .grade-on-push
git commit -m "Stop grading me on every push"
git push
```

One block for every platform, because `git rm` removes the file and
records the removal together.

From then on, pushing runs your own check and nothing else, and grading
happens when you ask for it from **Actions → Ask for feedback**.

**To turn it back on**, create the empty file again and commit it. This
is the one step that differs by platform, because creating an empty file
does:

**Windows**

```
New-Item -ItemType File .grade-on-push
git add .grade-on-push
git commit -m "Grade me on every push again"
git push
```

**macOS and Linux**

```
touch .grade-on-push
git add .grade-on-push
git commit -m "Grade me on every push again"
git push
```

**Neither switch costs you anything.** Both commits change no code, so
nothing is graded and no request is used either way. The next push after
turning it on is the first one graded.

It is your file, in your repository. Nothing in the course puts it back
or takes it away, and it affects nobody else.

**Most people want it off while they are reorganising things and on
while they are stuck on one exercise.** Switching it back and forth is
expected, not untidy.

### Why you might turn it off

Because not every push is a question. You are halfway through a change,
or renaming a file, or fixing a typo, and being told what is wrong with
a half-finished exercise is noise. Ten a day is plenty when they go on
the pushes you wanted an answer to, and runs out quickly when they do
not.

That is what the switch is for, and not a recommendation to leave it
off. While you are working on an exercise, an answer three minutes after
each push is the quickest way to find out you were wrong about
something.

### If nothing appears

**If you have used up today's ten, a comment on your Issue says so.** It
appears once a day, however many more times you push, and tells you when
the count returns.

For anything else, open **Actions** and look at the most recent run of
**Check my work** or **Ask for feedback**. It says what happened in plain
words: that your request was sent, or that automatic grading is off and
how to ask once.

**A reply does not always arrive, and that is usually fine.** The course
comments when it has something to tell you: a result that has changed, an
exercise you have just attempted, something that failed and now passes. If
it looks again and nothing has changed, it finds the same answer as last
time, and says nothing rather than repeating itself.

So if the run says your request was sent and no comment appears, the
ordinary explanation is that nothing has changed since it last looked.
Change something and push again. If a real change gets no reply after five
minutes, that is worth telling your teacher about.

### The reply arrives as an Issue

When there is something to say, the AI assistant writes it to an **Issue on
this repository** — one Issue per exercise, titled `課題01：AIフィードバック`.

Nothing is written into your code, and nothing is committed to this
repository on your behalf. There is no need to `git pull` before carrying on.

Each reply is another comment on that exercise's Issue, so one exercise's
whole history is in one place. When the exercise is finished the Issue gets a
closing comment and is closed; if it later stops working the same Issue is
reopened and the next reply continues there. The Issues still open are the
list of what is outstanding.

### Your passing builds are in Releases

When an exercise passes, the firmware that was built from your code during
grading is published as a release on this repository. One release per
exercise, tagged `passed/<exercise>`, holding a single file named after the
exercise — `01-blink-with-a-delay.elf`.

Find them under **Releases** in this repository, or follow the link in the
closing comment on that exercise's Issue.

To run one, download it and drop it on the board view. It loads exactly as a
build you made yourself does, and there is nothing to type.

**This is not the same binary as "Run the build GitHub made" gives you.** A
release is frozen at the commit that first passed the exercise. That control
fetches whatever your most recent push compiled. When the two differ, the
release is the older one — which is the point of it: it is the build that was
judged.

It is git-ignored, like anything else ending in `.elf`, so it will not show
up as a change to your repository.

**It is the binary from the commit the release names, not from your current
code.** The release says which commit it came from. If you have edited that
exercise since, build locally — the download will not show your change, and
that is the one way to be confused by it.

Two things you may notice. An exercise you passed before this existed gets
its build the next time you push anything, and arrives with no comment about
it, because its Issue closed long ago. And a tag appears in the repository
for each published build: it is a label on a commit you already made, not a
change to your code and not a commit on your behalf.

### A hint is a hint

It names the concept and asks you a question. It will not write the corrected
line, because working that out is the exercise.

Fail the same exercise again and the next hint is narrower — the same place,
but pointed at more precisely. After four attempts it stops hinting and says
to ask an instructor, because by then that is the more useful help.

### Ten hints a day

There is a limit of ten automatic hints a day, counted across all four
exercises together. What it counts is times the AI assistant was asked, not
times you pushed: a push that changes nothing is set aside before the limit is
consulted, and the hand-over after four attempts does not count against it
either.

If you reach it you are told so, and told that nothing further arrives that
day. The allowance is back before the first look of the next working day — but
a hint comes only for a push that changes something, so waiting without
editing gets you nothing.

Ten hints in one day is the same signal the hand-over is about. Ask an
instructor.

### Why the checker is not in here

It builds your code and it holds a credential to do so. You can edit every
file in this repository, including the ones that decide what runs — so
anything with a credential has to live somewhere you cannot change it. That
is also why `Check my work` is not your grade: you could edit it.

### Checking it yourself, before you push

Every exercise ships its own behaviour check, sitting next to the
exercise in your repository. Build first, then run it where Renode is —
inside the container:

```
python3 exercises/01-blink-with-a-delay/check.py \
  --elf exercises/01-blink-with-a-delay/firmware.elf
```

It reports in Japanese. Register names and compiler messages stay in
English, because those are the strings you search for.

It answers one of three ways:

| Exit | Meaning |
| --- | --- |
| 0 | it did what the exercise asks |
| 1 | it did not, and the output says what it saw |
| 2 | it could not tell |

**Two is not a failure.** It means the check never got far enough to have
an opinion: no Renode in this environment, no `firmware.elf` because you
have not built yet, the simulation not finishing in time, or the board or
firmware failing to load at all. Nothing there is a statement about your
code.

This is also why `Check my work` reports every behaviour check as "not
checked" — that runner has the compiler but not the simulator, so every one
of them exits 2.

Editing your copy changes nothing about your grade. The grader runs the
course's copy of the check, never the one in your repository, for the same
reason the grading workflow is not in here.

Exercise 4 has a behaviour check, and it works differently from the others.
It asks you to choose the thresholds, so there is no particular pattern of
lit LEDs it can compare against. What it checks instead is the shape: as the
sensor warms, the number of lit LEDs must never go down, and somewhere across
the range it must go up.
