"""This repository exists twice, and nothing noticed when the two diverged.

Six files differed on 2026-10-09, including the section that tells learners
the exercise checks exist. The copy had been stale since the day it was
seeded, and every check in this repository passed throughout.

Two things are tested here. The comparison itself, whose functions are pure
so neither a second organisation nor a network is needed. And the guard on
the workflow, because the reason the drift went unreported for ten days is
that the guard named one organisation by hand, so the sweep -- including the
check that would have caught this -- was skipped in the copy on every push.
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import check_copy_drift as drift  # noqa: E402


class TestWhatCountsAsAnEditedCopy:

    def test_matching_hashes_are_no_problem(self):
        assert drift.copy_problems({"a": "1"}, {"a": "1"}) == []

    def test_a_changed_file_is_named_and_blamed_correctly(self):
        problems = drift.copy_problems({"a": "1"}, {"a": "2"})
        assert problems == ["a was edited here rather than upstream"]

    def test_a_file_deleted_from_the_copy_is_reported(self):
        assert drift.copy_problems({"a": "1"}, {}) == [
            "a is recorded but missing from the copy"]

    def test_a_file_added_to_the_copy_is_reported(self):
        """The direction that matters most: somebody fixing something here.

        The fix is lost at the next sync, and until then the two
        organisations behave differently for a reason nothing records.
        """
        assert drift.copy_problems({}, {"a": "1"}) == [
            "a is in the copy and was never recorded"]

    def test_every_problem_is_reported_not_just_the_first(self):
        problems = drift.copy_problems({"a": "1", "b": "1"},
                                       {"b": "2", "c": "1"})
        assert len(problems) == 3


class TestWhatCountsAsStale:

    def test_nothing_changed_means_not_behind(self):
        assert drift.stale_files([], []) == []

    def test_a_changed_file_is_the_copys_business(self):
        assert drift.stale_files(["README.md"], []) == ["README.md"]

    def test_the_records_themselves_are_never_stale(self):
        """COPIES changes every time a sync is recorded. Counting it would
        make the check report drift created by the act of clearing it."""
        assert drift.stale_files(["COPIES", "PROVENANCE"], []) == []

    def test_a_file_the_two_are_meant_to_disagree_about_is_ignored(self):
        assert drift.stale_files(["roster.csv"], ["roster.csv"]) == []

    def test_a_pattern_ending_in_a_slash_covers_what_is_under_it(self):
        assert drift.stale_files(["ledger/2026.csv"], ["ledger/"]) == []

    def test_a_directory_pattern_does_not_swallow_a_similar_name(self):
        """`ledger/` must not excuse `ledgerbook.md`."""
        assert drift.stale_files(["ledgerbook.md"], ["ledger/"]) == [
            "ledgerbook.md"]

    def test_blank_lines_from_git_are_dropped(self):
        assert drift.stale_files(["", "README.md", ""], []) == ["README.md"]


class TestTheRecordFormat:

    def write(self, tmp_path, body):
        path = tmp_path / "RECORD"
        path.write_text(body, encoding="utf-8")
        return str(path)

    def test_keys_and_hashes_are_both_read(self, tmp_path):
        keys, hashes = drift.read_record(self.write(tmp_path, (
            "# a comment\n"
            "source = example-org/nucleo-f401re@abc\n"
            "\n"
            "aaaa  README.md\n")))
        assert keys["source"] == [
            "example-org/nucleo-f401re@abc"]
        assert hashes == {"README.md": "aaaa"}

    def test_a_repeated_key_keeps_every_value(self, tmp_path):
        """`differs` is written once per path, so the second must not win."""
        keys, _ = drift.read_record(self.write(tmp_path, (
            "differs = a.csv\ndiffers = b/\n")))
        assert keys["differs"] == ["a.csv", "b/"]

    def test_a_missing_record_is_empty_rather_than_an_error(self, tmp_path):
        keys, hashes = drift.read_record(str(tmp_path / "absent"))
        assert (keys, hashes) == ({}, {})


class TestWhatIsHashed:

    def build(self, tmp_path):
        (tmp_path / "exercises").mkdir()
        (tmp_path / "exercises" / "main.c").write_text("int main(){}",
                                                       encoding="utf-8")
        return tmp_path

    def test_source_is_hashed(self, tmp_path):
        got = drift.files_under(str(self.build(tmp_path)))
        assert "exercises/main.c" in got

    def test_build_output_is_not(self, tmp_path):
        """A learner or a maintainer who has built an exercise has a
        firmware.elf next to it. It is git-ignored, so it is not part of what
        is copied, and hashing it would fail the check on their machine."""
        root = self.build(tmp_path)
        (root / "exercises" / "firmware.elf").write_bytes(b"\x7fELF")
        got = drift.files_under(str(root))
        assert "exercises/firmware.elf" not in got

    def test_the_record_files_are_not_hashed(self, tmp_path):
        """Each side holds only one of them, so comparing them would report
        drift between every source and every copy, for ever."""
        root = self.build(tmp_path)
        (root / "COPIES").write_text("copy = x\n", encoding="utf-8")
        (root / "PROVENANCE").write_text("source = y\n", encoding="utf-8")
        got = drift.files_under(str(root))
        assert "COPIES" not in got and "PROVENANCE" not in got

    def test_bytecode_and_caches_are_not_hashed(self, tmp_path):
        root = self.build(tmp_path)
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\x00")
        assert drift.files_under(str(root)) == {
            "exercises/main.c": drift.digest(b"int main(){}")}

    def test_line_endings_do_not_change_a_hash(self, tmp_path):
        """The same commit is CRLF on Windows and LF on the runner. Hashing
        raw bytes made an earlier check pass locally and fail in CI."""
        assert drift.digest(b"a\r\nb") == drift.digest(b"a\nb")

    def test_a_file_the_copies_disagree_about_is_not_hashed(self, tmp_path):
        root = self.build(tmp_path)
        (root / "local.csv").write_text("x", encoding="utf-8")
        got = drift.files_under(str(root), ["local.csv"])
        assert "local.csv" not in got
        assert "exercises/main.c" in got


class TestARepositoryIsOneOrTheOther:
    """A copy that holds COPIES says it is the source of itself.

    `git archive` carries COPIES into a sync, so this is the default outcome
    of the obvious sync procedure rather than an exotic mistake. Without the
    guard, the copy's sweep reports that its history was rewritten, which
    sends the reader looking for a force-push that never happened.
    """

    def both(self, tmp_path, monkeypatch):
        (tmp_path / "PROVENANCE").write_text(
            "source = example-org/nucleo-f401re@abc\n"
            "\naaaa  README.md\n", encoding="utf-8")
        (tmp_path / "COPIES").write_text(
            "copy = other-org/nucleo-f401re\nsynced = abc\n",
            encoding="utf-8")
        monkeypatch.setattr(drift, "PROVENANCE",
                            str(tmp_path / "PROVENANCE"))
        monkeypatch.setattr(drift, "COPIES", str(tmp_path / "COPIES"))

    def test_holding_both_records_fails(self, tmp_path, monkeypatch):
        self.both(tmp_path, monkeypatch)
        assert drift.main(["--copy"]) == 1
        assert drift.main(["--source"]) == 1

    def test_it_says_which_one_to_delete(self, tmp_path, monkeypatch, capsys):
        self.both(tmp_path, monkeypatch)
        drift.main(["--source"])
        said = capsys.readouterr().out
        assert "Delete COPIES" in said
        assert "never both" in said

    def test_recording_is_still_allowed(self, tmp_path, monkeypatch):
        """A sync writes one record while the other is being removed, so
        --update must not be blocked by the state it is clearing."""
        self.both(tmp_path, monkeypatch)
        monkeypatch.setattr(drift, "REPO", str(tmp_path))
        source = tmp_path / "src"
        source.mkdir()
        assert drift.main(["--copy", "--update", "--ref", "org/repo@abc",
                           "--from", str(source)]) == 0


class TestRecordingChecksBeforeItBlesses:
    """`--update` used to record whatever was in the copy.

    That made the failing direction silenceable by the command that clears
    it: an edit made only in the copy -- the exact thing `--copy` exists to
    fail on -- is cleared by re-recording, and afterwards the two cases are
    indistinguishable. ADR-0023 recorded the hole, and that on 2026-10-09 the
    only thing closing it was somebody diffing thirteen files by hand.
    """

    def copy_and_source(self, tmp_path, monkeypatch, differs=()):
        copy = tmp_path / "copy"
        source = tmp_path / "source"
        for root in (copy, source):
            (root / "exercises").mkdir(parents=True)
            (root / "exercises" / "main.c").write_text("int main(){}",
                                                       encoding="utf-8")
        record = "source = org/repo@old\n"
        for pattern in differs:
            record += "differs = %s\n" % pattern
        (copy / "PROVENANCE").write_text(record, encoding="utf-8")
        monkeypatch.setattr(drift, "REPO", str(copy))
        monkeypatch.setattr(drift, "PROVENANCE", str(copy / "PROVENANCE"))
        monkeypatch.setattr(drift, "COPIES", str(copy / "COPIES"))
        return copy, source

    def record(self, source, extra=()):
        return drift.main(["--copy", "--update", "--ref", "org/repo@new",
                           "--from", str(source)] + list(extra))

    def test_a_matching_copy_is_recorded(self, tmp_path, monkeypatch):
        _copy, source = self.copy_and_source(tmp_path, monkeypatch)
        assert self.record(source) == 0

    def test_an_edit_made_only_in_the_copy_is_refused(self, tmp_path,
                                                     monkeypatch):
        """The whole point. This is the case hand-diffing was covering."""
        copy, source = self.copy_and_source(tmp_path, monkeypatch)
        (copy / "exercises" / "main.c").write_text("int main(){return 1;}",
                                                   encoding="utf-8")
        assert self.record(source) == 1

    def test_it_names_the_file_rather_than_only_refusing(self, tmp_path,
                                                        monkeypatch, capsys):
        copy, source = self.copy_and_source(tmp_path, monkeypatch)
        (copy / "exercises" / "main.c").write_text("edited",
                                                   encoding="utf-8")
        self.record(source)
        said = capsys.readouterr().out
        assert "exercises/main.c differs from the source" in said

    def test_a_file_only_in_the_copy_is_refused(self, tmp_path, monkeypatch):
        copy, source = self.copy_and_source(tmp_path, monkeypatch)
        (copy / "NOTES.md").write_text("local", encoding="utf-8")
        assert self.record(source) == 1

    def test_a_file_the_sync_forgot_is_refused(self, tmp_path, monkeypatch):
        """Half a sync must not be recorded as a whole one."""
        _copy, source = self.copy_and_source(tmp_path, monkeypatch)
        (source / "NEW.md").write_text("added upstream", encoding="utf-8")
        assert self.record(source) == 1

    def test_a_file_the_two_may_disagree_about_is_not_compared(
            self, tmp_path, monkeypatch):
        """`differs` already excuses it from the drift check; excusing it
        here too is what makes the roster and the ledger syncable at all."""
        copy, source = self.copy_and_source(tmp_path, monkeypatch,
                                            differs=["roster.csv"])
        (copy / "roster.csv").write_text("theirs", encoding="utf-8")
        (source / "roster.csv").write_text("ours", encoding="utf-8")
        assert self.record(source) == 0

    def test_recording_without_a_source_is_refused(self, tmp_path,
                                                  monkeypatch):
        """Required rather than optional: an optional check is not run on
        the day somebody is clearing a red build they have not read."""
        _copy, _source = self.copy_and_source(tmp_path, monkeypatch)
        assert drift.main(["--copy", "--update",
                           "--ref", "org/repo@new"]) == 2

    def test_a_source_that_is_not_there_is_refused(self, tmp_path,
                                                   monkeypatch):
        _copy, _source = self.copy_and_source(tmp_path, monkeypatch)
        assert drift.main(["--copy", "--update", "--ref", "org/repo@new",
                           "--from", str(tmp_path / "absent")]) == 2


class TestTheWorkflowGuard:
    """Why the drift above was invisible for ten days.

    The sweep's guard named one organisation, so in the copy every run was
    skipped -- and a skipped job is not a failure, so nothing said so. The
    organisation used to rehearse enrolment and grading was the one with no
    CI at all.
    """

    def workflow(self):
        path = os.path.join(ROOT, ".github", "workflows", "sweep.yml")
        return io.open(path, encoding="utf-8").read()

    def jobs_and_guards(self):
        """Read it as text rather than YAML.

        The sweep runs these tests inside the container as well as on the
        runner, and the container has no pyyaml. A test that cannot run in
        one of the two places it is asked to run is not much of a test.
        """
        jobs, guards = [], []
        inside = False
        for line in self.workflow().splitlines():
            if line.startswith("jobs:"):
                inside = True
                continue
            if inside and re.match(r"^  [a-z][a-z0-9_-]*:$", line):
                jobs.append(line.strip().rstrip(":"))
            if inside and line.strip().startswith("if:"):
                guards.append(line.strip())
        return jobs, guards

    def test_every_job_is_guarded(self):
        """Counted, not spot-checked.

        One guarded job and one forgotten one is the same outcome as no
        guard at all for whichever learner's repository runs the second:
        a full container build on every push, across a whole cohort.
        """
        jobs, guards = self.jobs_and_guards()
        assert len(jobs) >= 1
        assert len(guards) == len(jobs), \
            "%d job(s) but %d guard(s)" % (len(jobs), len(guards))

    def test_no_guard_names_an_organisation(self):
        _jobs, guards = self.jobs_and_guards()
        for guard in guards:
            assert "example-org/" not in guard
            assert "other-org/" not in guard

    def test_every_guard_matches_this_repository_by_name(self):
        _jobs, guards = self.jobs_and_guards()
        for guard in guards:
            assert "endsWith(github.repository, '/nucleo-f401re')" in guard

    def test_the_checkout_asks_for_the_whole_history(self):
        """Otherwise the staleness check can never compare anything.

        actions/checkout fetches depth 1 by default, and the commit the copy
        was synced at is then absent, so the check says "could not compare"
        on every run while the job stays green. It said exactly that on the
        first run it was ever part of. A guard that quietly stops guarding is
        worse than no guard, so the condition it needs is asserted here
        rather than left to whoever next edits the workflow.
        """
        body = self.workflow()
        checkout = body.index("actions/checkout@")
        assert "fetch-depth: 0" in body[checkout:checkout + 300]


class TestTheRecommendedRuntimeIsActuallyRun:
    """SETUP.md recommends Podman. Nothing ran it until 2026-10-09.

    CI used docker only, so the route learners are told to prefer was the one
    route nobody had executed, and "identical except for the program name"
    was a claim rather than a result.
    """

    def workflow(self):
        path = os.path.join(ROOT, ".github", "workflows", "sweep.yml")
        return io.open(path, encoding="utf-8").read()

    def podman_job(self):
        """Just that job's block, not the whole file.

        A first draft grepped the whole workflow, and `check-environment.sh`
        appears in the docker job too -- so deleting the podman step entirely
        left the test passing. Found by mutation, not by reading.
        """
        lines = self.workflow().splitlines()
        start = next(i for i, line in enumerate(lines)
                     if line.startswith("  podman:"))
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if re.match(r"^  [a-z][a-z0-9_-]*:$", lines[i]):
                end = i
                break
        return "\n".join(lines[start:end])

    def test_podman_builds_the_image(self):
        assert "podman build" in self.podman_job()

    def test_podman_runs_the_environment_check(self):
        job = self.podman_job()
        assert "podman run" in job
        assert "check-environment.sh" in job

    def test_podman_proves_the_bind_mount_works(self):
        """The one thing that genuinely differs between the two runtimes.

        Reading is not enough: a mount can be readable and still refuse a
        write, which is what SELinux relabelling actually does. So the probe
        file is named here -- asserting `-v "$PWD:/work"` alone passed even
        with the whole probe step disabled, because the environment-check
        step mounts the same way.
        """
        job = self.podman_job()
        assert '-v "$PWD:/work"' in job
        assert ".podman-write-probe" in job

    def test_it_does_not_use_a_login_shell(self):
        """'bash -lc' re-reads /etc/profile, replaces PATH, and hides both
        tools -- which once made a working image look broken.

        Comment lines are excluded, because the comments warn against it by
        name. A first draft of this test failed on the warning itself, which
        would have taught the next reader to delete the explanation.
        """
        commands = [line for line in self.workflow().splitlines()
                    if not line.strip().startswith("#")]
        assert not [line for line in commands if "bash -lc" in line]

    def test_the_documents_recommend_the_runtime_that_is_tested(self):
        setup = io.open(os.path.join(ROOT, "SETUP.md"),
                        encoding="utf-8").read()
        assert "Podman" in setup
        assert "podman build" in self.workflow()


class TestSELinuxIsNotLeftToBeDiscovered:
    """The one difference the runner cannot reproduce, so it is documented.

    SELinux relabels bind mounts, and on Fedora and RHEL the mount in
    SETUP.md is refused with permission denied on files the learner can read
    themselves. Nothing in the error names SELinux, so the only clue points
    away from the cause. Until 2026-10-09 neither document nor either
    self-check mentioned it at all.

    Only the shell check is asserted: SELinux does not exist on Windows, so
    the PowerShell check correctly says nothing about it.
    """

    def read(self, *parts):
        return io.open(os.path.join(ROOT, *parts), encoding="utf-8").read()

    def test_the_shell_check_detects_it(self):
        """The detection, not merely the word.

        `getenforce` appears twice in that block -- once to ask whether the
        command exists and once to read it -- so asserting the bare name
        passed even with the detection replaced by `if false`. The condition
        is named instead.
        """
        body = self.read("tools", "check-container.sh")
        assert "command -v getenforce" in body
        assert '= "Enforcing"' in body

    def test_the_shell_check_names_the_flag_to_add(self):
        assert ":z" in self.read("tools", "check-container.sh")

    def test_the_windows_check_does_not_mention_it(self):
        """There is no SELinux on Windows. Saying so would be noise that
        sends somebody looking for a setting they do not have."""
        assert "getenforce" not in self.read("tools", "check-container.ps1")

    def test_both_documents_say_it(self):
        for name in ("SETUP.md", "SETUP.ja.md"):
            body = self.read(name)
            assert "SELinux" in body, name
            assert ":z" in body, name

    def test_the_checkout_asks_for_the_whole_history(self):
        """Otherwise the staleness check can never compare anything.

        actions/checkout fetches depth 1 by default, and the commit the copy
        was synced at is then absent, so the check says "could not compare"
        on every run while the job stays green. It said exactly that on the
        first run it was ever part of. A guard that quietly stops guarding is
        worse than no guard, so the condition it needs is asserted here
        rather than left to whoever next edits the workflow.
        """
        path = os.path.join(ROOT, ".github", "workflows", "sweep.yml")
        body = io.open(path, encoding="utf-8").read()
        checkout = body.index("actions/checkout@")
        following = body[checkout:checkout + 300]
        assert "fetch-depth: 0" in following
