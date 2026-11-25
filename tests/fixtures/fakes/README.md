# Programs that cheat

Each of these produces an exercise's observable without doing the exercise.
They exist so the course can **demonstrate** what its checks reject rather
than claim it (ADR-0051).

`tests/sweep.py` builds every one and requires the matching check to reject
it. A check that accepts its fake fails the build and is named.

## Layout

    fakes/<exercise directory>/<what it fakes>/main.c

The exercise is the directory name, not something parsed out of a filename,
so a renamed exercise breaks the mapping loudly instead of quietly matching
nothing.

## These are not solutions

Every one deliberately **fails** its exercise. A learner who found this
directory would learn how to be caught, not how to pass — which is why these
can live here while real solutions may not (ADR-0003, and `solutions/` in
`course-operations` under ADR-0027).

Do not fix one so that it passes. A fake that does the exercise demonstrates
nothing, and the sweep would then be asserting that a correct program is
rejected.

## Each one was accepted before the check that catches it

Measured 2026-11-19, against the checks as they stood at `1d463b0`:

| Fake | Then | Now |
| --- | --- | --- |
| `01/odr-only` | 0 | 1 |
| `02/delay-loop` | 0 | 1 |
| `03/delay-loop` | 0 | 1 |
| `04/time-ramp` | 0 | 1 |
| `04/no-pins` | 0 | 1 |

That table is the point of the directory. A fake the old check already
rejected would demonstrate nothing, so a new one has to be shown to pass the
check it is meant to defeat before the check is changed to defeat it.

`04/no-pins` is the experiment from 2026-09-25 that
`pin-configuration-not-enforced` cites: reference solution `thresholds.c`
with its five I2C pin-setup lines deleted. It reads the sensor correctly and
shows the right bar.

## Timing

`02/delay-loop` is tuned to a one-second half-period on purpose, so it passes
exercise 2's period check and fails only the causal one. If exercise 2's
tolerance ever changes, re-tune this rather than letting the period check
start doing the causal check's job — the two would then be impossible to tell
apart from the sweep's output.
