"""Detect drift between this repository and a copy of it in another place.

This repository exists twice: the live course, and a rehearsal copy in a
second organisation used to try enrolment and grading somewhere that is not
the live one. They were seeded by upload rather than by clone, so they have no
common ancestor and `git push` cannot carry a change between them. Changes are
copied by hand, and nothing reported whether that had happened.

On 2026-10-09 it had not. Six files differed. The rehearsal copy was missing
the whole section telling learners that the exercise checks exist and that
exit code 2 is not a failure -- so anybody enrolled there was reading
documentation the live course had already replaced. Nothing failed, and the
only thing that found it was going to look.

The same fault had already happened once in `course-operations`, four days
earlier, and was fixed there. It was not fixed here, because nobody had
noticed that this repository is copied too.

TWO CHECKS, POINTED IN OPPOSITE DIRECTIONS
------------------------------------------
Neither subsumes the other, and the asymmetry is the whole reason both exist.

  --copy    Compares this repository against the hashes in its own record.
            Catches a file edited in the copy rather than upstream, which is
            how drift starts. FAILS.

  --source  Compares the commit the copy was last synced at against this
            repository's own history, and names the copied files that have
            changed since. Catches the copy being left behind. WARNS.

A stale copy cannot detect its own staleness. Its files match its record
exactly, because nothing is wrong with it -- it is old. Only the source knows
it has moved.

WHY ONE FAILS AND THE OTHER ONLY WARNS
--------------------------------------
An edit to the copy is a mistake: the change belongs upstream and will be
lost at the next sync. Staleness is not a mistake -- the rehearsal copy is
disposable and is allowed to lag -- and failing the live repository's build
because a test organisation is behind would block real work, after which the
quickest way to clear the red would be to delete this file.

WHY THIS IS NOT THE `course-operations` FILE
--------------------------------------------
It is the same record format and the same two directions, deliberately, so a
maintainer who knows one knows the other. It is not the same file, and when
this was written that one imported its record parser from
`check_provisioning_drift.py` -- a check on a copy of the backend's
provisioning code, with no business in a repository every learner receives.
Copying one would have meant copying both, so the parser was inlined here.

That coupling is gone: the provisioning stopped being a copy on 2026-10-20,
that file was deleted, and its parser moved into the `course-operations`
checker. The inlining stays, because the reason it is a separate
implementation never was the coupling. Two implementations of one agreement,
each tested in its own repository, is what keeps the agreement honest
(ADR-0023) -- a vendored copy would make the two agree by construction and
prove nothing.

WHAT IS NOT HASHED
------------------
Build output. `*.elf` and friends are git-ignored, so they are not part of
what is copied, but they ARE in the working tree of anybody who has built an
exercise. Hashing them would make this check fail on a developer's machine
and pass in CI, and the quickest way to clear that is to re-record the
hashes -- which is exactly the action that hides real drift.

Exit codes: 0 compared and fine, 1 the copy was edited or the record is
wrong, 2 could not compare and is not claiming otherwise.

    python tests/check_copy_drift.py --copy
    python tests/check_copy_drift.py --source
    python tests/check_copy_drift.py --copy --update --ref 'org/repo@sha'         --from ../nucleo-f401re
    python tests/check_copy_drift.py --source --update
"""

import argparse
import hashlib
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# What the copy records about itself, and what the source records about the
# copy. Same format; opposite directions. PROVENANCE points inward at where
# this came from, COPIES points outward at what was taken from here. Neither
# is ever compared, because each side has only one of them.
PROVENANCE = os.path.join(REPO, "PROVENANCE")
COPIES = os.path.join(REPO, "COPIES")
RECORDS = ("PROVENANCE", "COPIES")

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache"}

# Git-ignored build output. See the header.
SKIP_SUFFIXES = (".pyc", ".elf", ".bin", ".hex", ".o", ".map")


def read_record(path):
    """Parse a record file: `key = value` lines, then `hash  path` lines.

    The same format `course-operations/tools/check_copy_drift.py` reads, and
    the same format `--update` writes here. Keys repeat, so each maps to a
    list. Returns (keys, hashes).
    """
    keys = {}
    hashes = {}
    if not os.path.isfile(path):
        return keys, hashes
    with io.open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line and not line.split("=", 1)[0].strip().count(" "):
                name, value = line.split("=", 1)
                keys.setdefault(name.strip(), []).append(value.strip())
            elif " " in line:
                body, rel = line.split(None, 1)
                hashes[rel.strip()] = body
    return keys, hashes


def digest(body):
    """Line endings normalised first.

    git checks the same commit out as CRLF on Windows and LF on the runner,
    so hashing raw bytes makes a check pass locally and fail in CI, naming
    files nobody touched.
    """
    return hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest()


def differs(rel, patterns):
    """Is this path one the two copies are meant to disagree about?

    A pattern ending in `/` covers everything beneath it, so a record can say
    `differs = exports/` once rather than naming a file at a time and
    silently starting to compare the one nobody added.
    """
    for pattern in patterns:
        if pattern.endswith("/"):
            if rel == pattern.rstrip("/") or rel.startswith(pattern):
                return True
        elif rel == pattern:
            return True
    return False


def files_under(root, patterns=()):
    out = {}
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            if name.endswith(SKIP_SUFFIXES):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if rel in RECORDS or differs(rel, patterns):
                continue
            with open(path, "rb") as handle:
                out[rel] = digest(handle.read())
    return out


def copy_problems(recorded, current):
    """Pure, so every case is testable without a second repository."""
    problems = []
    for rel in sorted(set(recorded) | set(current)):
        if rel not in current:
            problems.append("%s is recorded but missing from the copy" % rel)
        elif rel not in recorded:
            problems.append("%s is in the copy and was never recorded" % rel)
        elif recorded[rel] != current[rel]:
            problems.append("%s was edited here rather than upstream" % rel)
    return problems


def source_problems(source, current):
    """Is what is about to be recorded actually what the source holds?

    Without this, `--update` blesses whatever is in the copy. An edit made
    only here -- the exact thing `--copy` exists to fail on -- is cleared by
    the command that clears a legitimate sync, and the two are indistinguish-
    able afterwards. The failing direction could be silenced by the command
    meant to settle it.

    ADR-0023 recorded that hole and that on 2026-10-09 the only thing closing
    it was somebody diffing thirteen files by hand before re-recording. This
    is that diff, done by the tool instead.
    """
    problems = []
    for rel in sorted(set(source) | set(current)):
        if rel not in source:
            problems.append("%s is here and not in the source" % rel)
        elif rel not in current:
            problems.append("%s is in the source and not here" % rel)
        elif source[rel] != current[rel]:
            problems.append("%s differs from the source" % rel)
    return problems


def stale_files(changed, patterns):
    """Which of the paths changed since the sync are the copy's business."""
    return sorted(rel for rel in changed
                  if rel and not differs(rel, patterns)
                  and rel not in RECORDS)


def git(*args):
    try:
        done = subprocess.run(("git",) + args, cwd=REPO,
                              capture_output=True, text=True)
    except OSError as exc:
        return 127, "", str(exc)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def write_provenance(path, source, hashes, patterns):
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(u"# Where this repository was copied from, and what it "
                     u"looked like when it arrived.\n")
        handle.write(u"# Written by tests/check_copy_drift.py --copy "
                     u"--update; do not edit the hashes by hand.\n")
        handle.write(u"#\n")
        handle.write(u"# A file edited HERE is lost at the next sync. Make "
                     u"the change upstream and copy it down.\n")
        handle.write(u"source = %s\n" % source)
        for pattern in sorted(patterns):
            handle.write(u"differs = %s\n" % pattern)
        handle.write(u"\n")
        for rel in sorted(hashes):
            handle.write(u"%s  %s\n" % (hashes[rel], rel))


def write_copies(path, copy, head, patterns):
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(u"# A copy of this repository that lives somewhere "
                     u"else, and the commit it holds.\n")
        handle.write(u"# Written by tests/check_copy_drift.py --source "
                     u"--update after copying changes across.\n")
        handle.write(u"#\n")
        handle.write(u"# The two have unrelated histories -- the copy was "
                     u"seeded by upload rather than\n")
        handle.write(u"# by clone -- so git push cannot carry a change "
                     u"between them. Changes are\n")
        handle.write(u"# copied by hand, and this line is how anybody knows "
                     u"whether that has happened.\n")
        handle.write(u"copy = %s\n" % copy)
        handle.write(u"synced = %s\n" % head)
        for pattern in sorted(patterns):
            handle.write(u"differs = %s\n" % pattern)


def check_copy(update, ref, from_path=None):
    keys, recorded = read_record(PROVENANCE)
    patterns = keys.get("differs", [])
    source = (keys.get("source") or [None])[0]
    current = files_under(REPO, patterns)

    if update:
        source = ref or source
        if not source:
            print("Say where it came from: --ref 'org/repo@sha'")
            return 2

        # Required, not optional. An optional check is not run on the day it
        # matters, and the day it matters is the day somebody re-records to
        # clear a red build they have not read.
        if not from_path:
            print("Say where to check against: --from PATH, a checkout of "
                  "the source.")
            print("Recording without it would bless whatever is here, "
                  "including an edit made only here.")
            return 2
        if not os.path.isdir(from_path):
            print("--from %s is not a directory." % from_path)
            return 2

        problems = source_problems(files_under(from_path, patterns), current)
        if problems:
            print("Not recording. This copy does not match %s:" % from_path)
            for problem in problems:
                print("  - " + problem)
            print("")
            print("Finish the sync first. If one of these is meant to differ "
                  "between the two, add it to PROVENANCE as `differs = ...`.")
            return 1

        write_provenance(PROVENANCE, source, current, patterns)
        print("Recorded %d files from %s" % (len(current), source))
        print("  checked against %s first" % from_path)
        return 0

    if not os.path.isfile(PROVENANCE):
        print("copy: NOT CHECKED. No PROVENANCE here, so this repository "
              "does not record itself as a copy of anything.")
        return 2

    if not recorded:
        # Saying "matches" against nothing recorded would be a lie that
        # reads exactly like success.
        print("copy: COULD NOT COMPARE. PROVENANCE names %s but records no "
              "file hashes." % (source or "no source"))
        print("Run: python tests/check_copy_drift.py --copy --update")
        return 2

    problems = copy_problems(recorded, current)
    if not problems:
        print("copy: %d files match what was recorded (from %s)"
              % (len(current), source))
        return 0

    print("The copy has been changed since it was taken from %s:" % source)
    for problem in problems:
        print("  - " + problem)
    print("")
    print("A change made here is lost at the next sync. Make it upstream "
          "and copy it down.")
    return 1


def check_source():
    keys, _ = read_record(COPIES)
    if not os.path.isfile(COPIES):
        print("source: NOT CHECKED. No COPIES here, so nothing records that "
              "a copy of this repository exists.")
        return 2

    copy = (keys.get("copy") or [None])[0]
    synced = (keys.get("synced") or [None])[0]
    patterns = keys.get("differs", [])
    if not copy or not synced:
        print("COPIES must name both `copy` and `synced`.")
        return 2

    code, _out, err = git("cat-file", "-e", synced + "^{commit}")
    if code == 127:
        # Inside the container there is no git. Honest about it, because a
        # guard that silently stops guarding is worse than no guard.
        print("source: COULD NOT COMPARE. No git here: %s" % err)
        return 2
    if code != 0:
        if git("rev-parse", "--is-shallow-repository")[1] == "true":
            # actions/checkout fetches depth 1 by default, which would make
            # this check permanently silent in CI while looking fine.
            print("source: COULD NOT COMPARE. The history here is shallow, "
                  "so %s is not present. Fetch the full history."
                  % synced[:12])
            return 2
        print("COPIES says the copy is synced at %s, which is not in this "
              "repository's history." % synced[:12])
        print("Either the record is wrong or the history was rewritten.")
        return 1

    code, out, err = git("diff", "--name-only", synced, "HEAD")
    if code != 0:
        print("source: COULD NOT COMPARE. git diff failed: %s" % err)
        return 2

    behind = stale_files(out.splitlines(), patterns)
    if not behind:
        print("source: %s is up to date (synced at %s)" % (copy, synced[:12]))
        return 0

    # A warning, deliberately. See the header.
    print("source: %s is BEHIND and this is not a failure." % copy)
    print("  synced at %s. Changed here since:" % synced[:12])
    for rel in behind:
        print("    - " + rel)
    print("  Copy these across, then record it:")
    print("    python tests/check_copy_drift.py --source --update")
    return 0


def update_source():
    keys, _ = read_record(COPIES)
    copy = (keys.get("copy") or [None])[0]
    patterns = keys.get("differs", [])
    if not copy:
        print("COPIES must name `copy` before it can be updated.")
        return 2
    code, head, _err = git("rev-parse", "HEAD")
    if code != 0:
        print("Not a git repository, or no commits.")
        return 2
    write_copies(COPIES, copy, head, patterns)
    print("Recorded %s as synced at %s" % (copy, head[:12]))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy", action="store_true",
                        help="check this repository against its own record")
    parser.add_argument("--source", action="store_true",
                        help="check whether the copy has been left behind")
    parser.add_argument("--update", action="store_true",
                        help="record the current state, after a real sync")
    parser.add_argument("--ref", default=None,
                        help="what the copy was taken from, for the record")
    parser.add_argument("--from", dest="from_path", default=None,
                        metavar="PATH",
                        help="a checkout of the source, to check this copy "
                             "against before recording it")
    args = parser.parse_args(argv)

    if args.copy == args.source:
        print("Pick one: --copy or --source.")
        return 2

    # A repository is a source or a copy, never both. COPIES belongs to the
    # source and must not travel with a sync, but `git archive` carries it,
    # and a copy holding both says it is the source of itself: the commit
    # COPIES names is not in its own history, so --source reports a rewritten
    # history and nobody reading that would guess why. Said plainly instead.
    # Not checked under --update, because clearing the state means writing a
    # record while the other one is still being removed.
    if not args.update and os.path.isfile(PROVENANCE) \
            and os.path.isfile(COPIES):
        print("Both PROVENANCE and COPIES are here. A repository is a source "
              "or a copy, never both.")
        print("PROVENANCE says this is a copy of %s."
              % ((read_record(PROVENANCE)[0].get("source") or ["?"])[0]))
        print("Delete COPIES: it belongs to the repository this was copied "
              "from, and arrived by being included in the sync.")
        return 1

    if args.source:
        return update_source() if args.update else check_source()
    return check_copy(args.update, args.ref, args.from_path)


if __name__ == "__main__":
    sys.exit(main())
