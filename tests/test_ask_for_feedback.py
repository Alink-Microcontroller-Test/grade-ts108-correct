"""Whether asking for feedback happens, and what the learner is told.

Three things are decided here and every one costs money or silence if it
is wrong: whether this push was asked to be graded, whether today's
allowance is used up, and what the learner reads when the answer is no.

The last one is not decoration. The complaint this whole mechanism
answers was a learner watching for feedback that was never coming, so a
refusal that says nothing is the original fault wearing a new shape.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import ask_for_feedback as ask  # noqa: E402


class TestCountingTodaysRequests:
    """By matching the course's run names, because the runs list
    endpoint does not return a dispatch's inputs."""

    def test_no_runs_is_none_used(self):
        assert ask.requests_used([], "S001") == 0

    def test_this_learners_runs_are_counted(self):
        titles = ["grade: requested by S001"] * 3
        assert ask.requests_used(titles, "S001") == 3

    def test_another_learners_runs_are_not(self):
        titles = ["grade: requested by S002",
                  "grade: requested by S001",
                  "grade: requested by S003"]
        assert ask.requests_used(titles, "S001") == 1

    def test_a_sweep_is_not_counted(self):
        """Nobody asked for it, so it must not come out of anybody's
        allowance."""
        titles = ["grade: scheduled sweep", "grade: requested by S001"]
        assert ask.requests_used(titles, "S001") == 1

    def test_a_longer_name_that_starts_the_same_is_not_counted(self):
        """S0011's runs must not come out of S001's allowance.

        A substring test would count them: "grade: requested by S0011"
        contains "requested by S001". This is the quiet one -- it fails
        in the direction of refusing a learner who has requests left.
        """
        titles = ["grade: requested by S0011"] * 5
        assert ask.requests_used(titles, "S001") == 0

    def test_an_empty_title_is_ignored(self):
        assert ask.requests_used(["", "grade: requested by S001"],
                                 "S001") == 1


class TestWhenNobodyAsked:
    """The default. A push runs the compile check and nothing else."""

    def test_no_marker_and_no_button_does_not_dispatch(self):
        send, _, _ = ask.decide(marker_present=False, asked_by_hand=False,
                                used=0)
        assert send is False

    def test_and_it_says_why_and_how(self):
        """ADR-0039: a report that reaches nobody is not a report, and
        the run log is the only place a learner is already looking."""
        _, level, message = ask.decide(False, False, 0)
        assert level == "notice"
        assert "not graded" in message
        assert "Ask for feedback" in message, "it must say how to ask once"
        assert ask.MARKER in message, "and how to ask every time"

    def test_it_does_not_consult_the_allowance(self):
        """A learner who has not opted in is told why nothing happened,
        not that they are out of requests. Those are different facts."""
        _, _, message = ask.decide(False, False, used=999)
        assert "allowance" not in message


class TestWhenTheLearnerAsked:
    def test_the_button_dispatches_without_a_marker(self):
        send, _, _ = ask.decide(marker_present=False, asked_by_hand=True,
                                used=0)
        assert send is True

    def test_the_marker_dispatches_without_the_button(self):
        send, _, _ = ask.decide(marker_present=True, asked_by_hand=False,
                                used=0)
        assert send is True

    def test_the_message_says_how_long_to_wait(self):
        """"About three minutes" rather than "immediately". A run starts
        in seconds and the verdict does not, and conflating them is the
        fault that has recurred most often on this project.

        It said "two to three minutes" until 2026-11-06, when five real
        requests measured 157, 169, 194, 197 and 200 seconds. Three of
        the five exceeded three minutes, so the old wording was a
        promise the system did not keep."""
        _, _, message = ask.decide(True, False, 0)
        assert "about three minutes" in message

    def test_the_message_warns_that_silence_can_mean_nothing_changed(self):
        """Observed on 2026-11-06, on the first real end-to-end request.

        The course only comments when it has something to say. A learner
        who asks having changed nothing gets a grading run and silence,
        after being told to expect a comment in about three minutes --
        which is indistinguishable from the mechanism being broken, and
        is the exact complaint this whole change was built to end.

        Saying it in advance is the cheap half of the fix. The other
        half, having the course say "nothing has changed since X" when a
        learner explicitly asked, is recorded as an open question.
        """
        _, _, message = ask.decide(True, False, 0)
        assert "nothing has changed" in message
        assert "not a fault" in message

    def test_the_message_says_how_many_are_left(self):
        _, _, message = ask.decide(True, False, used=0)
        assert "9 of today's 10" in message

    def test_the_last_one_says_none_left(self):
        _, _, message = ask.decide(True, False, used=9)
        assert "0 of today's 10" in message


class TestWhenTheAllowanceIsUsedUp:
    def test_the_tenth_request_is_sent(self):
        send, _, _ = ask.decide(True, False, used=9)
        assert send is True

    def test_the_eleventh_is_not(self):
        send, _, _ = ask.decide(True, False, used=10)
        assert send is False

    def test_being_over_it_does_not_dispatch_either(self):
        """The count can exceed the allowance -- a learner holding the
        grading secret can dispatch directly. Refusing is still the
        right answer for the workflow."""
        send, _, _ = ask.decide(True, False, used=40)
        assert send is False

    def test_the_refusal_says_it_cost_nothing(self):
        """True, and worth saying. The count is taken inside the job the
        push already paid for, so an over-quota push bills the course
        nothing at all."""
        _, level, message = ask.decide(True, False, used=10)
        assert level == "warning"
        assert "costs nothing" in message

    def test_the_refusal_says_when_the_allowance_returns(self):
        _, _, message = ask.decide(True, False, used=10)
        assert "midnight JST" in message

    def test_the_refusal_says_the_code_was_still_checked(self):
        """The compile check ran and reported. A learner reading only
        the refusal must not conclude that nothing happened."""
        _, _, message = ask.decide(True, False, used=10)
        assert "still checked" in message

    def test_the_button_is_refused_too(self):
        """The allowance binds however the request was made. Otherwise
        a learner out of automatic requests just presses the button."""
        send, _, _ = ask.decide(False, True, used=10)
        assert send is False


class TestTheAllowanceItself:
    def test_ten_a_day(self):
        assert ask.DAILY_ALLOWANCE == 10

    def test_a_smaller_allowance_binds_sooner(self):
        """The figure is a budget judgement rather than a measurement,
        so it has to be changeable in one place."""
        assert ask.decide(True, False, used=2, allowance=3)[0] is True
        assert ask.decide(True, False, used=3, allowance=3)[0] is False

    def test_the_marker_is_dotted_so_it_stays_out_of_the_way(self):
        assert ask.MARKER.startswith(".")


class TestTheDispatchPayload:
    """Both inputs go as strings, including the boolean one.

    The API takes workflow_dispatch inputs as strings, and the previous
    dispatcher sent "false" that way over dozens of real runs. A JSON
    boolean is the obvious shape and is not the proven one.

    `dry_run` matters more than it looks: it defaults to TRUE on the
    course's workflow so a person pressing the button there changes
    nothing by accident. A request that let the default stand would be
    graded and then deliver nothing, silently -- which is the exact bug
    found on 2026-11-02 in the mechanism this replaces.
    """

    def payload(self):
        sent = {}

        class Fake(ask.Course):
            def _request(self, method, path, body=None):
                sent["method"] = method
                sent["path"] = path
                sent["body"] = body
                return {}

        Fake("t", "org", "course-operations", "grade.yml").dispatch(
            "main", "S001")
        return sent

    def test_it_posts_to_the_workflow_dispatch_endpoint(self):
        sent = self.payload()
        assert sent["method"] == "POST"
        assert sent["path"].endswith(
            "/actions/workflows/grade.yml/dispatches")

    def test_it_is_not_the_repository_dispatch_endpoint(self):
        """That one needs Contents: write, which also reads -- and
        reading the course means reading everybody's solutions. The
        whole design rests on this being the other endpoint."""
        path = self.payload()["path"]
        assert "/actions/workflows/" in path
        # repository_dispatch is /repos/{owner}/{repo}/dispatches, with
        # nothing between the repository and "dispatches".
        assert not path.endswith("/course-operations/dispatches")

    def test_the_learner_is_sent(self):
        assert self.payload()["body"]["inputs"]["learner"] == "S001"

    def test_dry_run_is_the_string_false(self):
        value = self.payload()["body"]["inputs"]["dry_run"]
        assert value == "false"
        assert isinstance(value, str), "a JSON boolean is not the proven shape"

    def test_the_ref_is_sent(self):
        assert self.payload()["body"]["ref"] == "main"
class TestTheRunsQuery:
    """The query that counts today's requests.

    This was wrong and nothing caught it: `requests_used` is pure and
    was tested on titles, so the part that could fail -- building the
    URL -- had no test at all. A probe run on 2026-11-06 reported "9 of
    today's 10 requests left" with three runs already made.

    A JST midnight ends in "+09:00". A raw "+" in a query string means a
    space, so GitHub read a malformed date and returned an empty list
    rather than an error. Measured on the same three runs: unencoded
    gave 0, encoded gave 3. An allowance that always reads zero is an
    allowance that never binds.
    """

    def query(self, since="2026-11-06T00:00:00+09:00"):
        seen = {}

        class Fake(ask.Course):
            def _request(self, method, path, body=None):
                seen["method"] = method
                seen["path"] = path
                return {"workflow_runs": []}

        Fake("t", "org", "course-operations", "grade.yml").runs_today(since)
        return seen["path"]

    def test_the_timestamp_is_percent_encoded(self):
        assert "%2B09%3A00" in self.query()

    def test_no_raw_plus_reaches_the_query(self):
        """The whole bug in one assertion. A "+" here is a space there."""
        assert "+" not in self.query()

    def test_the_comparison_is_encoded_too(self):
        assert "created=%3E%3D" in self.query()

    def test_it_asks_only_for_dispatched_runs(self):
        """A scheduled sweep is nobody's request, so it must not be
        counted -- and filtering here is cheaper than filtering later."""
        assert "event=workflow_dispatch" in self.query()

    def test_it_asks_for_a_full_page(self):
        assert "per_page=100" in self.query()

    def test_a_utc_timestamp_survives_as_well(self):
        """The day is a JST day deliberately, but the encoding must not
        depend on which offset the timestamp carries."""
        path = self.query("2026-11-05T15:00:00+00:00")
        assert "2026-11-05T15%3A00%3A00%2B00%3A00" in path

    def test_it_is_a_GET(self):
        assert self.query  # the method under test
        seen = {}

        class Fake(ask.Course):
            def _request(self, method, path, body=None):
                seen["method"] = method
                return {"workflow_runs": []}

        Fake("t", "o", "r", "w").runs_today("2026-11-06T00:00:00+09:00")
        assert seen["method"] == "GET"
class TestSwitchingAutomaticGradingOnCostsNothing:
    """Committing the marker is a push with the marker present, so it
    asked for feedback -- on a commit that changed no code. Three billed
    minutes to be told nothing had changed, as the very first thing a
    learner does after opting in.

    The rule is narrow on purpose: the marker AND NOTHING ELSE. A push
    that adds the marker alongside real work still asks, because then
    there is something to grade.
    """

    def payload(self, tmp_path, body):
        import json
        f = tmp_path / "event.json"
        f.write_text(json.dumps(body), encoding="utf-8")
        return str(f)

    def test_a_real_push_payload_is_read(self, tmp_path):
        """The shape GitHub actually sends. Tested against a file rather
        than asserted about, because the first version of this did it
        with a jq expression in the workflow that nothing here could
        run."""
        path = self.payload(tmp_path, {"commits": [
            {"added": [".grade-on-push"], "modified": [], "removed": []}]})
        assert ask.changed_paths(path) == [".grade-on-push"]

    def test_several_commits_in_one_push_are_all_counted(self):
        """A push can carry more than one commit, and the marker arriving
        in the same push as real work must still count as work."""
        import json, tempfile, os
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"commits": [
                {"added": [".grade-on-push"]},
                {"modified": ["exercises/01-blink-with-a-delay/main.c"]}]}, fh)
        try:
            found = ask.changed_paths(path)
            assert ".grade-on-push" in found
            assert "exercises/01-blink-with-a-delay/main.c" in found
            assert ask.only_the_marker_changed(found) is False
        finally:
            os.unlink(path)

    def test_a_workflow_dispatch_payload_has_no_commits(self, tmp_path):
        """Which reads as unknown, and asks."""
        path = self.payload(tmp_path, {"inputs": {}})
        assert ask.changed_paths(path) == []
        assert ask.only_the_marker_changed(ask.changed_paths(path)) is False

    def test_a_missing_or_unreadable_payload_is_not_fatal(self, tmp_path):
        assert ask.changed_paths(None) == []
        assert ask.changed_paths(str(tmp_path / "nope.json")) == []
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert ask.changed_paths(str(bad)) == []

    def test_the_marker_alone_is_recognised(self):
        assert ask.only_the_marker_changed([ask.MARKER]) is True

    def test_the_marker_with_anything_else_is_not(self):
        assert ask.only_the_marker_changed(
            [ask.MARKER, "exercises/01-blink-with-a-delay/main.c"]) is False

    def test_an_unknown_changed_set_is_not(self):
        """The asymmetry that decides this rule's default. Wrongly
        skipping leaves a learner who asked with silence, which is the
        fault this whole change exists to end. Wrongly asking costs three
        minutes. So 'I do not know' means ask."""
        assert ask.only_the_marker_changed([]) is False
        assert ask.only_the_marker_changed(None) is False
        assert ask.only_the_marker_changed([""]) is False

    def test_blank_entries_do_not_make_it_look_like_more(self):
        """The workflow passes a comma-joined string, so an empty tail
        is easy to produce and must not defeat the rule."""
        assert ask.only_the_marker_changed(["", ask.MARKER, " "]) is True

    def test_another_file_alone_is_not_the_marker(self):
        assert ask.only_the_marker_changed(["README.md"]) is False

    def test_switching_on_sends_nothing(self):
        send, _, _ = ask.decide(marker_present=True, asked_by_hand=False,
                                used=0, only_marker=True)
        assert send is False

    def test_and_says_so_without_sounding_like_a_refusal(self):
        _, level, message = ask.decide(True, False, 0, only_marker=True)
        assert level == "notice"
        assert "Automatic grading is on" in message
        assert "no request was used" in message
        assert "next push will be graded" in message

    def test_switching_off_says_that_instead(self):
        """Removing the marker puts it in the changed set too, and the
        learner should be told which way the switch went."""
        _, level, message = ask.decide(False, False, 0, only_marker=True)
        assert level == "notice"
        assert "Automatic grading is off" in message
        assert "Ask for feedback" in message, "and how to ask once"

    def test_it_is_checked_before_the_allowance(self):
        """'Nothing to grade' is a truer answer than 'you are out of
        requests', and neither costs anything."""
        _, _, message = ask.decide(True, False, used=10, only_marker=True)
        assert "Automatic grading is on" in message
        assert "allowance" not in message

    def test_the_button_still_asks_even_if_only_the_marker_changed(self):
        """An explicit request is an explicit request. The learner
        pressed the button; they are not guessing."""
        send, _, _ = ask.decide(True, True, 0, only_marker=True)
        assert send is True

    def test_the_marker_with_real_work_still_asks(self):
        """The case the narrow rule is narrow for."""
        send, _, _ = ask.decide(True, False, 0, only_marker=False)
        assert send is True

class TestAPushTheCourseMadeIsNotASubmission:
    """`refresh_learner_copies.py --write` commits into a learner's
    repository, which is a push, and until 2026-11-09 nothing here looked at
    who pushed. So the course bringing a learner's README into line spent one
    of that learner's ten daily requests and started a grading run on code
    they never pushed.

    The cost did not stay linear either. A grading request grades every
    ACTIVE learner, and `grade.yml` is `cancel-in-progress: false`, so runs
    queue rather than cancel: refreshing thirty learners would have been
    thirty queued full grading sweeps rather than thirty cheap pushes.
    """

    def payload(self, tmp_path, body, name="event.json"):
        import json
        f = tmp_path / name
        f.write_text(json.dumps(body), encoding="utf-8")
        return str(f)

    def course_commit(self, message=None):
        return {"message": message or (
            "Course material updated\n\n%s" % ask.COURSE_WROTE_THIS)}

    def test_the_courses_own_push_is_recognised(self, tmp_path):
        path = self.payload(tmp_path, {"commits": [self.course_commit()]})
        assert ask.every_commit_is_the_courses(path) is True

    def test_two_course_commits_in_one_push(self, tmp_path):
        path = self.payload(tmp_path, {"commits": [self.course_commit(),
                                                   self.course_commit()]})
        assert ask.every_commit_is_the_courses(path) is True

    def test_a_learners_push_is_not_the_courses(self, tmp_path):
        path = self.payload(tmp_path, {"commits": [
            {"message": "fix the timer"}]})
        assert ask.every_commit_is_the_courses(path) is False

    def test_a_push_carrying_both_is_the_learners(self, tmp_path):
        """EVERY commit, not any. Being wrong this way costs a learner one
        request; being wrong the other way would silently never grade a
        push they made."""
        path = self.payload(tmp_path, {"commits": [
            self.course_commit(), {"message": "my own work"}]})
        assert ask.every_commit_is_the_courses(path) is False

    def test_head_commit_is_read_when_there_is_no_commits_list(self,
                                                               tmp_path):
        path = self.payload(tmp_path,
                            {"head_commit": self.course_commit()})
        assert ask.every_commit_is_the_courses(path) is True

    def test_a_workflow_dispatch_has_no_commits_and_is_not_the_courses(
            self, tmp_path):
        path = self.payload(tmp_path, {"inputs": {}})
        assert ask.every_commit_is_the_courses(path) is False

    def test_an_unreadable_payload_asks_rather_than_suppressing(self,
                                                                tmp_path):
        """Unknown asks, the same way round as every other unknown here. A
        course push not recognised costs one request; a learner's push
        mistaken for the course's would never be graded and nothing would
        say so."""
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert ask.every_commit_is_the_courses(str(bad)) is False
        assert ask.every_commit_is_the_courses(None) is False
        assert ask.every_commit_is_the_courses(
            str(tmp_path / "nope.json")) is False

    def test_a_commit_with_no_message_at_all_is_not_the_courses(self,
                                                               tmp_path):
        path = self.payload(tmp_path, {"commits": [{}]})
        assert ask.every_commit_is_the_courses(path) is False


class TestTheCourseWriteExemptionInMain:
    def payload(self, tmp_path, body):
        import json
        f = tmp_path / "event.json"
        f.write_text(json.dumps(body), encoding="utf-8")
        return str(f)

    def course_push(self, tmp_path):
        return self.payload(tmp_path, {"commits": [
            {"message": "Course material updated\n\n%s"
                        % ask.COURSE_WROTE_THIS}]})

    def test_it_returns_before_anything_is_spent(self, tmp_path,
                                                 monkeypatch, capsys):
        """Before the token is looked at and before any call is made, so a
        course write costs nothing at all -- not a request, not an API
        call, not a dispatch."""
        monkeypatch.setenv("GITHUB_EVENT_PATH", self.course_push(tmp_path))
        assert ask.main(["--owner", "Org", "--learner", "S001"]) == 0
        said = capsys.readouterr().out
        assert "the course made this push" in said
        assert "no request was used" in said

    def test_the_learner_is_told_on_their_run(self, tmp_path, monkeypatch,
                                             capsys):
        """A run they did not start appears either way. Saying nothing
        would leave a repository that looks like it has a mind of its
        own."""
        monkeypatch.setenv("GITHUB_EVENT_PATH", self.course_push(tmp_path))
        ask.main(["--owner", "Org", "--learner", "S001"])
        said = capsys.readouterr().out
        assert "::notice" in said
        assert "The course updated a file" in said
        assert "none of your 10 requests" in said

    def test_asking_by_hand_is_exempt_from_the_exemption(self, tmp_path,
                                                         monkeypatch,
                                                         capsys):
        """A learner who dispatched the workflow deliberately is asking,
        whatever the last commit on their branch happens to say."""
        monkeypatch.setenv("GITHUB_EVENT_PATH", self.course_push(tmp_path))
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        ask.main(["--owner", "Org", "--learner", "S001", "--by-hand"])
        assert "the course made this push" not in capsys.readouterr().out

    def test_a_learners_push_is_unaffected(self, tmp_path, monkeypatch,
                                           capsys):
        monkeypatch.setenv("GITHUB_EVENT_PATH", self.payload(
            tmp_path, {"commits": [{"message": "fix the timer"}]}))
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        ask.main(["--owner", "Org", "--learner", "S001"])
        assert "the course made this push" not in capsys.readouterr().out


class TestTheMarkerIsPinnedToWhatTheCourseWrites:
    def test_it_is_the_string_the_course_puts_in_its_commits(self):
        """`course-operations/tools/refresh_learner_copies.py` writes this
        trailer. The two live in different repositories, so a rename in one
        of them would silently start charging learners again -- which is
        why the course's `sweep.py` pins them together as well."""
        assert ask.COURSE_WROTE_THIS == "[course-update]"

    def test_it_is_not_the_grade_on_push_marker(self):
        """Two different markers with two different jobs, and conflating
        them would make deleting one do the other's work."""
        assert ask.COURSE_WROTE_THIS != ask.MARKER
