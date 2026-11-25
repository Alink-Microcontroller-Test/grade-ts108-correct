# -*- coding: utf-8 -*-
"""Telling a learner, on their Issue, that the allowance is spent.

Task 3.8 of `tell-the-learner-what-is-left`.

The test that earns its place more than the others is
`TestTheTwoAnswersCannotDrift`: `decide` and `refused_for_allowance` ask
the same question in two places, and a parity check over every
combination is the only thing stopping them diverging silently.
"""
import io
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import ask_for_feedback as ask  # noqa: E402


TODAY = "2026-11-06"
YESTERDAY = "2026-11-05"


def issue(number, state="open", body=None, updated="2026-11-06T00:00:00Z"):
    return {"number": number, "state": state, "updated_at": updated,
            "body": ask.COURSE_ISSUE_MARKER + "01-x -->"
                    if body is None else body}


# --------------------------------------------------------------------

class TestTheTwoAnswersCannotDrift:
    """`decide` refuses on the allowance in its own branch, and
    `refused_for_allowance` answers the same question for main(). If they
    ever disagree, either a learner is told nothing when refused, or a
    learner who was not refused gets a comment about allowances."""

    @pytest.mark.parametrize("marker", [True, False])
    @pytest.mark.parametrize("by_hand", [True, False])
    @pytest.mark.parametrize("only_marker", [True, False])
    @pytest.mark.parametrize("used", [0, 9, 10, 11])
    def test_they_agree_on_every_combination(self, marker, by_hand,
                                             only_marker, used):
        send, _, message = ask.decide(marker, by_hand, used,
                                      only_marker=only_marker)
        predicted = ask.refused_for_allowance(marker, by_hand, used,
                                              only_marker=only_marker)
        if predicted:
            assert send is False
            assert "allowance" in message, (
                "refused_for_allowance says yes, decide said something else")
        else:
            assert not (send is False and "allowance of" in message), (
                "decide refused on the allowance, refused_for_allowance "
                "did not notice")


class TestOnlyARealRefusalPostsAnything:
    """Three things make decide() return False and only one is a refusal.
    A learner who never asked must not find the course talking to them
    about allowances."""

    def test_not_opted_in_is_not_a_refusal(self):
        assert ask.refused_for_allowance(False, False, 0) is False

    def test_not_opted_in_with_the_allowance_spent_is_still_not(self):
        assert ask.refused_for_allowance(False, False, 99) is False

    def test_flipping_the_switch_is_not_a_refusal(self):
        assert ask.refused_for_allowance(True, False, 99,
                                         only_marker=True) is False

    def test_the_button_overrides_the_switch_rule(self):
        """Pressing the button on a marker-only push IS a request, so
        running out of allowance there IS a refusal."""
        assert ask.refused_for_allowance(True, True, 10,
                                         only_marker=True) is True

    def test_an_exhausted_push_is_a_refusal(self):
        assert ask.refused_for_allowance(True, False, 10) is True

    def test_an_exhausted_button_is_a_refusal(self):
        assert ask.refused_for_allowance(False, True, 10) is True


# --------------------------------------------------------------------

class TestChoosingTheIssue:

    def test_the_most_recently_updated_open_course_issue(self):
        found = ask.course_issue([
            issue(1, updated="2026-11-01T00:00:00Z"),
            issue(2, updated="2026-11-06T05:00:00Z"),
            issue(3, updated="2026-11-03T00:00:00Z"),
        ])
        assert found["number"] == 2

    def test_a_closed_issue_is_used_when_there_is_no_open_one(self):
        """MEASURED ON S006, 2026-11-06T07:43Z. Requiring an open Issue
        was the first rule and it left the commonest learner silent: pass
        an exercise and the course closes its Issue, so a learner who has
        passed everything so far has none open. The log said
        `refusal notice: no-issue` and nothing reached them."""
        found = ask.course_issue([issue(1, state="closed")])
        assert found is not None and found["number"] == 1

    def test_an_issue_the_course_did_not_open_is_not_chosen(self):
        """A learner may open their own Issues. The course's carry a
        marker in the body; a learner's will not."""
        assert ask.course_issue([issue(1, body="help me please")]) is None

    def test_a_pull_request_is_not_an_issue(self):
        """GitHub's issues endpoint returns pull requests too, and
        commenting on one would be posting in the wrong place."""
        pr = issue(1)
        pr["pull_request"] = {"url": "..."}
        assert ask.course_issue([pr]) is None

    def test_no_issues_at_all(self):
        assert ask.course_issue([]) is None
        assert ask.course_issue(None) is None

    def test_a_closed_one_updated_later_does_not_win(self):
        found = ask.course_issue([
            issue(1, updated="2026-11-01T00:00:00Z"),
            issue(2, state="closed", updated="2026-11-09T00:00:00Z"),
        ])
        assert found["number"] == 1


class TestTellingThemOnlyOnce:

    def test_todays_notice_suppresses_a_second(self):
        posted = [{"body": ask.NOTICE_MARKER % TODAY + "\n..."}]
        assert ask.already_told_today(posted, TODAY) is True

    def test_yesterdays_notice_does_not(self):
        posted = [{"body": ask.NOTICE_MARKER % YESTERDAY + "\n..."}]
        assert ask.already_told_today(posted, TODAY) is False

    def test_the_courses_own_comments_do_not_count(self):
        posted = [{"body": "<!-- course-operations exercise=01-x -->\n..."}]
        assert ask.already_told_today(posted, TODAY) is False

    def test_no_comments_at_all(self):
        assert ask.already_told_today([], TODAY) is False
        assert ask.already_told_today(None, TODAY) is False


class TestWhatTheNoticeSays:

    def test_it_states_the_three_facts(self):
        body = ask.refusal_notice(TODAY, 10)
        assert "使い切りました" in body, "that the allowance is spent"
        assert "毎日" not in body and "0時（JST）に戻ります" in body, "when it returns"
        assert "コンパイルの確認は実行されています" in body, "that the check ran"

    def test_it_does_not_say_tomorrow(self):
        """A JST day. Someone refused at 23:00 gets it back in an hour."""
        assert "明日" not in ask.refusal_notice(TODAY, 10)

    def test_it_does_not_send_them_to_a_teacher(self):
        """The hint cap's notice does, and should: that cap is reached by
        failing ten times. This one is reached by pushing ten times, which
        a learner can do while passing everything."""
        assert "教員" not in ask.refusal_notice(TODAY, 10)

    def test_it_names_requests_and_not_hints(self):
        body = ask.refusal_notice(TODAY, 10)
        assert "依頼" in body
        assert "ヒント" not in body

    def test_it_carries_todays_marker(self):
        assert ask.NOTICE_MARKER % TODAY in ask.refusal_notice(TODAY, 10)

    def test_it_states_the_allowance_it_was_given(self):
        assert "7回" in ask.refusal_notice(TODAY, 7)


# --------------------------------------------------------------------

class FakeRepo:
    def __init__(self, issues, comments=None):
        self._issues = issues
        self._comments = comments or []
        self.posted = []

    def issues(self, state="all"):
        return self._issues

    def comments(self, number):
        return self._comments

    def comment(self, number, body):
        self.posted.append((number, body))
        return {"id": 1}


class TestTheThreeOutcomes:

    def test_posted(self):
        repo = FakeRepo([issue(4)])
        assert ask.tell_them_on_the_issue(repo, TODAY) == "posted"
        assert repo.posted[0][0] == 4
        assert "使い切りました" in repo.posted[0][1]

    def test_already_told_today(self):
        repo = FakeRepo([issue(4)],
                        [{"body": ask.NOTICE_MARKER % TODAY}])
        assert ask.tell_them_on_the_issue(repo, TODAY) == "already"
        assert repo.posted == []

    def test_no_issue_to_post_on(self):
        repo = FakeRepo([])
        assert ask.tell_them_on_the_issue(repo, TODAY) == "no-issue"
        assert repo.posted == []

    def test_yesterdays_notice_does_not_suppress_todays(self):
        repo = FakeRepo([issue(4)],
                        [{"body": ask.NOTICE_MARKER % YESTERDAY}])
        assert ask.tell_them_on_the_issue(repo, TODAY) == "posted"


# --------------------------------------------------------------------

class TestTheDispatchCarriesTheCounts:

    def test_both_counts_are_sent_as_strings(self):
        sent = {}

        class Recording(ask.Course):
            def _request(self, method, path, body=None):
                sent.update(body or {})
                return {}

        Recording("t", "org", "course-operations", "grade.yml").dispatch(
            "main", "S006", left=6, allowance=10)
        inputs = sent["inputs"]
        assert inputs["requests_left"] == "6"
        assert inputs["requests_allowance"] == "10"
        assert all(isinstance(v, str) for v in inputs.values()), (
            "workflow_dispatch inputs must all be strings")

    def test_the_existing_inputs_are_untouched(self):
        sent = {}

        class Recording(ask.Course):
            def _request(self, method, path, body=None):
                sent.update(body or {})
                return {}

        Recording("t", "org", "course-operations", "grade.yml").dispatch(
            "main", "S006", left=0, allowance=10)
        assert sent["inputs"]["learner"] == "S006"
        assert sent["inputs"]["dry_run"] == "false"

    def test_the_api_asks_for_closed_issues_too(self):
        """The fix to Finding A is in two places and a test on the pure
        function alone would pass while production stayed broken: if the
        query still said state=open, a closed Issue would never reach
        course_issue to be chosen."""
        asked = {}

        class Recording(ask.OwnRepository):
            def _request(self, method, path, body=None):
                asked["path"] = path
                return []

        Recording("t", "org", "S006").issues()
        assert "state=all" in asked["path"]
        assert "state=open" not in asked["path"]


class TestAskingTheApiWhatThePushChanged:
    """Finding B, fixed. MEASURED ON S006, 2026-11-06T08:00Z: the event
    payload's `commits` is present and populated, and each commit object
    carries no `added`, `modified` or `removed` arrays at all. So the
    payload cannot answer the question, and the marker-only rule read
    every push as "unknown" and asked anyway -- three times.

    The API can answer it, and only became reachable when the workflow
    gained a token for its own repository.
    """

    class FakeApi:
        def __init__(self, files, expect=None):
            self.files = files
            self.expect = expect
            self.called = None

        def commit_detail(self, sha):
            self.called = ("commit", sha)
            return {"files": self.files}

        def compare(self, base, head):
            self.called = ("compare", base, head)
            return {"files": self.files}

    def test_an_ordinary_push_uses_compare(self):
        """A push can carry several commits and the rule is about the
        push, not about its last commit."""
        api = self.FakeApi([{"filename": ".grade-on-push"}])
        got = ask.changed_in_this_push(api, "aaa", "bbb")
        assert got == [".grade-on-push"]
        assert api.called == ("compare", "aaa", "bbb")

    def test_a_new_branch_uses_the_head_commit(self):
        """GitHub sends forty zeros as `before`, and there is no range
        to compare against."""
        api = self.FakeApi([{"filename": "main.c"}])
        got = ask.changed_in_this_push(api, "0" * 40, "bbb")
        assert got == ["main.c"]
        assert api.called == ("commit", "bbb")

    def test_a_missing_before_also_uses_the_head_commit(self):
        api = self.FakeApi([{"filename": "main.c"}])
        ask.changed_in_this_push(api, "", "bbb")
        assert api.called == ("commit", "bbb")

    def test_no_head_means_nothing_is_known(self):
        api = self.FakeApi([{"filename": "main.c"}])
        assert ask.changed_in_this_push(api, "aaa", "") == []
        assert api.called is None, "must not call the API with no sha"

    def test_several_files(self):
        api = self.FakeApi([{"filename": "a.c"}, {"filename": "b.c"}])
        assert ask.changed_in_this_push(api, "a", "b") == ["a.c", "b.c"]

    def test_an_empty_files_list(self):
        assert ask.changed_in_this_push(self.FakeApi([]), "a", "b") == []

    def test_a_response_with_no_files_key(self):
        class NoFiles:
            def compare(self, base, head):
                return {}
        assert ask.changed_in_this_push(NoFiles(), "a", "b") == []

    def test_entries_without_a_filename_are_dropped(self):
        api = self.FakeApi([{"filename": "a.c"}, {"status": "renamed"}])
        assert ask.changed_in_this_push(api, "a", "b") == ["a.c"]

    def test_the_marker_alone_is_recognised_through_this_path(self):
        """The whole point: turning automatic grading on must now be
        free, because the API says the push touched only the marker."""
        api = self.FakeApi([{"filename": ask.MARKER}])
        got = ask.changed_in_this_push(api, "aaa", "bbb")
        assert ask.only_the_marker_changed(got) is True

    def test_the_marker_with_real_work_is_not(self):
        api = self.FakeApi([{"filename": ask.MARKER},
                            {"filename": "exercises/01/main.c"}])
        got = ask.changed_in_this_push(api, "aaa", "bbb")
        assert ask.only_the_marker_changed(got) is False


class TestReadingThePushRange:

    def test_before_and_after(self, tmp_path):
        p = tmp_path / "e.json"
        p.write_text('{"before": "aaa", "after": "bbb"}', encoding="utf-8")
        assert ask.push_range(str(p)) == ("aaa", "bbb")

    def test_a_missing_file(self, tmp_path):
        assert ask.push_range(str(tmp_path / "gone.json")) == ("", "")

    def test_no_path_at_all(self):
        assert ask.push_range(None) == ("", "")
        assert ask.push_range("") == ("", "")

    def test_a_payload_without_them(self, tmp_path):
        """A workflow_dispatch has neither, and must not crash."""
        p = tmp_path / "e.json"
        p.write_text('{"inputs": {}}', encoding="utf-8")
        assert ask.push_range(str(p)) == ("", "")

    def test_unparseable(self, tmp_path):
        p = tmp_path / "e.json"
        p.write_text("{", encoding="utf-8")
        assert ask.push_range(str(p)) == ("", "")

    def test_forty_zeros_is_a_new_branch(self):
        assert ask.a_branch_was_just_created("0" * 40) is True
        assert ask.a_branch_was_just_created("") is True
        assert ask.a_branch_was_just_created(None) is True
        assert ask.a_branch_was_just_created("abc123") is False


class TestSayingWhyTheChangedSetWasEmpty:
    """Finding B. `changed_paths` returns [] for four different reasons
    and reported the same thing for all of them, which is why the
    marker-only rule failed twice in production with nothing learned.

    Verified separately on 2026-11-06 that the parsing is correct against
    a real push payload, so what these distinguish is the environment.
    """

    def test_the_variable_is_not_set(self):
        assert "not set" in ask.describe_event(None)
        assert "not set" in ask.describe_event("")

    def test_the_file_is_missing(self, tmp_path):
        missing = str(tmp_path / "nope.json")
        assert "not a file" in ask.describe_event(missing)

    def test_the_file_is_not_json(self, tmp_path):
        bad = tmp_path / "event.json"
        bad.write_text("{not json", encoding="utf-8")
        assert "unreadable" in ask.describe_event(str(bad))

    def test_a_payload_with_no_commits_key(self, tmp_path):
        """A workflow_dispatch has no `commits` at all. Told apart from
        a push that carried none, because they mean different things."""
        p = tmp_path / "event.json"
        p.write_text('{"inputs": {}}', encoding="utf-8")
        said = ask.describe_event(str(p))
        assert "commits=ABSENT" in said

    def test_a_push_that_carried_no_commits(self, tmp_path):
        p = tmp_path / "event.json"
        p.write_text('{"ref": "refs/heads/main", "commits": []}',
                     encoding="utf-8")
        said = ask.describe_event(str(p))
        assert "commits=0" in said
        assert "ABSENT" not in said

    def test_a_normal_push_reports_its_commits(self, tmp_path):
        p = tmp_path / "event.json"
        p.write_text('{"ref": "r", "commits": [{"modified": ["a.c"]}]}',
                     encoding="utf-8")
        said = ask.describe_event(str(p))
        assert "commits=1" in said
        assert "keys=" in said

    def test_the_four_answers_are_all_different(self, tmp_path):
        """The whole point. If any two read alike, the next investigation
        learns as little as the last two did."""
        good = tmp_path / "ok.json"
        good.write_text('{"commits": []}', encoding="utf-8")
        bad = tmp_path / "bad.json"
        bad.write_text("{", encoding="utf-8")
        answers = [ask.describe_event(None),
                   ask.describe_event(str(tmp_path / "gone.json")),
                   ask.describe_event(str(bad)),
                   ask.describe_event(str(good))]
        assert len(set(answers)) == 4


class TestTheCredentialsStaySeparate:

    def test_the_two_credentials_are_separate_classes(self):
        """The course token cannot touch the learner's repository and the
        repository token cannot touch the course. Keeping them in one
        class is how one gets used where the other was meant."""
        assert ask.OwnRepository is not ask.Course
        assert not issubclass(ask.OwnRepository, ask.Course)


# --------------------------------------------------------------------
class TestWhichWayTheSwitchWasFlipped:
    """A marker-only push must say which way it went.

    `only_the_marker_changed` is True for REMOVING the marker as well as
    adding it -- its own docstring says so -- so both arrive at the same
    branch of `decide`, and only `marker_present` separates them. Nothing
    asserted on that until now: reversing the two messages, or dropping
    the inner branch, would tell a learner who had just turned automatic
    grading OFF that it was on from now on, and their next push would go
    ungraded while they believed the opposite. Measured in production on
    2026-11-09 for the ON direction only.
    """

    def message(self, marker_present):
        send, level, text = ask.decide(marker_present, False, 0,
                                       only_marker=True)
        assert send is False
        return text

    def test_adding_it_says_grading_is_on(self):
        assert "on from now on" in self.message(True)

    def test_removing_it_says_grading_is_off(self):
        assert "off from now on" in self.message(False)

    def test_the_two_directions_do_not_say_the_same_thing(self):
        assert self.message(True) != self.message(False)

    def test_removing_it_never_claims_the_next_push_is_graded(self):
        off = self.message(False)
        assert "Your next push will be graded" not in off
        assert "on from now on" not in off

    def test_removing_it_still_says_how_to_ask(self):
        """Turning the switch off must not read as losing the feature."""
        assert "Ask for feedback" in self.message(False)

    def test_neither_direction_mentions_the_allowance(self):
        """Nothing was spent, so nothing about counting belongs here."""
        for present in (True, False):
            text = self.message(present)
            assert "allowance" not in text
            assert "requests left" not in text

    def test_the_button_is_not_a_switch_flip(self):
        """`--by-hand` means they asked, whatever the push touched."""
        send, _, _ = ask.decide(True, True, 0, only_marker=True)
        assert send is True
        send, _, _ = ask.decide(False, True, 0, only_marker=True)
        assert send is True


class TestTheCountInTheDispatchMessage:
    """The number the learner is told is the number after this request.

    `allowance - used - 1`, and an off-by-one here is invisible: the
    message is plausible either way. Pinned against the production
    measurement of 2026-11-09, where a learner's first request of the
    day sent `requests_left=9` of `10`.
    """

    def left(self, used, allowance=10):
        send, _, text = ask.decide(True, False, used, allowance=allowance)
        assert send is True
        return text

    def test_the_first_request_of_the_day_leaves_nine_of_ten(self):
        assert "9 of today's 10 requests left" in self.left(0)

    def test_the_last_request_of_the_day_leaves_none(self):
        assert "0 of today's 10 requests left" in self.left(9)

    def test_it_never_offers_a_negative_count(self):
        """One below the allowance is the highest `used` that dispatches."""
        for used in range(10):
            send, _, _ = ask.decide(True, False, used, allowance=10)
            assert send is True
        send, _, _ = ask.decide(True, False, 10, allowance=10)
        assert send is False

    def test_the_message_uses_the_shared_function(self):
        """The message and the dispatch input cannot be made to disagree.

        They were two copies of `allowance - used - 1`. Now both call
        `requests_left_after_this`, and this asserts the message shows
        exactly what that function returns -- so an edit to the formula
        moves both numbers or neither.
        """
        for used in range(0, 10):
            expected = ask.requests_left_after_this(used, 10)
            assert "%d of today's 10 requests left" % expected                 in self.left(used)

    def test_the_arithmetic_is_written_in_exactly_one_place(self):
        """A third copy would reintroduce the drift this removed.

        Prose mentions are skipped by ignoring any line with a backtick:
        `requests_left_after_this` quotes the old expression to explain
        what it replaced, and that explanation is worth keeping.
        """
        source = io.open(ask.__file__.replace(".pyc", ".py"),
                         encoding="utf-8").read()
        in_code = [line for line in source.splitlines()
                   if "used - 1" in line and "`" not in line]
        assert len(in_code) == 1, in_code


class TestTheSharedCount:

    def test_a_fresh_day(self):
        assert ask.requests_left_after_this(0, 10) == 9

    def test_the_last_one(self):
        assert ask.requests_left_after_this(9, 10) == 0

    def test_it_is_never_negative(self):
        """`decide` refuses first, but this must not be the weak link."""
        for used in (10, 11, 50):
            assert ask.requests_left_after_this(used, 10) == 0

    def test_it_defaults_to_the_course_allowance(self):
        assert ask.requests_left_after_this(0) == ask.DAILY_ALLOWANCE - 1

    def test_an_allowance_of_one(self):
        assert ask.requests_left_after_this(0, 1) == 0


# --------------------------------------------------------------------
class TestACrashStillTellsTheLearner:
    """The step carries `continue-on-error: true`, so before the guard
    any unhandled exception left a green tick, no annotation and no
    feedback -- the exact silence this change exists to end, reachable
    from any bug above. It happened on 2026-11-06: a SyntaxError in this
    file killed the step and nothing anywhere said so.
    """

    def crash(self, capsys, exc):
        def boom():
            raise exc
        code = ask.say_something_even_if_this_crashed(boom)
        return code, capsys.readouterr().out

    def test_a_crash_is_annotated(self, capsys):
        _, out = self.crash(capsys, ValueError("nope"))
        assert "::warning title=Feedback::" in out

    def test_the_annotation_names_the_fault(self, capsys):
        """So whoever maintains the course can find it from the summary."""
        _, out = self.crash(capsys, ValueError("nope"))
        assert "ValueError" in out
        assert "nope" in out

    def test_it_says_the_code_was_still_checked(self, capsys):
        """A learner must not read this as 'your program is broken'."""
        _, out = self.crash(capsys, RuntimeError("x"))
        assert "still checked" in out

    def test_it_says_the_sweep_will_reach_them(self, capsys):
        _, out = self.crash(capsys, RuntimeError("x"))
        assert "sweeps twice a day" in out

    def test_it_does_not_claim_the_request_was_sent(self, capsys):
        """Not knowable from there, so it must not be asserted."""
        _, out = self.crash(capsys, RuntimeError("x"))
        assert "Asked the course" not in out
        assert "requests left" not in out

    def test_it_exits_zero_after_reporting(self, capsys):
        """Non-zero now means the program could not START, which is the
        workflow's job to report. The two must not both fire."""
        code, _ = self.crash(capsys, RuntimeError("x"))
        assert code == 0

    def test_a_normal_return_is_passed_through(self, capsys):
        assert ask.say_something_even_if_this_crashed(lambda: 0) == 0
        assert ask.say_something_even_if_this_crashed(lambda: 3) == 3

    def test_a_clean_run_annotates_nothing(self, capsys):
        ask.say_something_even_if_this_crashed(lambda: 0)
        assert capsys.readouterr().out == ""

    @pytest.mark.parametrize("exc", [SystemExit(1), KeyboardInterrupt()])
    def test_the_runner_stopping_us_is_not_a_feedback_fault(self, exc):
        """A cancelled run must not be reported as a green success with
        a feedback warning. These three propagate."""
        def boom():
            raise exc
        with pytest.raises(type(exc)):
            ask.say_something_even_if_this_crashed(boom)


class TestBothCrashGuardsAreWired:
    """One guard inside the tool, one in each workflow, and the division
    between them only works if both are present.
    """

    def workflow(self, name):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".github", "workflows", name)
        return io.open(path, encoding="utf-8").read()

    @pytest.mark.parametrize(
        "name", ["check-my-work.yml", "ask-for-feedback.yml"])
    def test_the_workflow_reports_a_tool_that_could_not_start(self, name):
        text = self.workflow(name)
        assert "ec=0" in text
        assert "|| ec=$?" in text
        assert "::warning title=Feedback::" in text

    def settings(self, name):
        """Config lines only. A comment that merely mentions a setting is
        prose, and an earlier version of this test matched its own
        explanation of `continue-on-error` and called it configured.
        """
        return [line.strip() for line in self.workflow(name).splitlines()
                if line.strip() and not line.strip().startswith("#")]

    def test_the_push_check_does_not_turn_red(self):
        """On a push, red would say "your code is wrong", which would be
        a lie about a compile check that may well have passed. The guard
        exists BECAUSE of this: with the step's failure hidden, something
        else has to speak."""
        assert "continue-on-error: true" in self.settings("check-my-work.yml")

    def test_the_button_workflow_is_allowed_to_turn_red(self):
        """Deliberately the opposite, and asserted so it stays that way.

        That workflow only asks -- there is no compile result for red to
        be misread as. A learner who pressed a button and got nothing
        should see a failed run, so it carries no `continue-on-error`.
        The guard there reports and then re-raises the code, because a
        shell `if` always succeeds and would otherwise have turned this
        green.
        """
        lines = self.settings("ask-for-feedback.yml")
        assert not [l for l in lines if l.startswith("continue-on-error")]
        assert "exit $ec" in self.workflow("ask-for-feedback.yml")

    @pytest.mark.parametrize(
        "name", ["check-my-work.yml", "ask-for-feedback.yml"])
    def test_the_guard_does_not_swallow_the_exit_code(self, name):
        assert "exit $ec" in self.workflow(name)

    def test_the_tool_guard_is_what_main_is_called_through(self):
        source = io.open(ask.__file__.replace(".pyc", ".py"),
                         encoding="utf-8").read()
        assert "sys.exit(say_something_even_if_this_crashed(main))" in source
        assert "sys.exit(main())" not in source


# --------------------------------------------------------------------
class TestTheTemplateIsNotALearner:
    """The course template carries the marker from
    `grade-on-push-by-default`, runs `check-my-work.yml` on every push,
    and holds no secrets at all (measured 2026-11-09: `total=0`). Without
    this it would annotate `COURSE_GRADE_TRIGGER is missing` on every
    push to the course's own repository -- telling us to fix something
    that is correct, in the words of the message that exists to catch a
    genuinely misconfigured learner. An alarm that fires on every push to
    the course is how a real one gets ignored.
    """

    class Repo:
        def __init__(self, answer):
            self.answer = answer
            self.asked = 0

        def detail(self):
            self.asked += 1
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer

    def test_the_template_says_so(self):
        assert ask.this_is_the_course_template(
            self.Repo({"is_template": True})) is True

    def test_a_learner_does_not(self):
        assert ask.this_is_the_course_template(
            self.Repo({"is_template": False})) is False

    def test_a_missing_field_is_not_a_template(self):
        assert ask.this_is_the_course_template(self.Repo({})) is False

    @pytest.mark.parametrize("fault", [
        urllib.error.URLError("down"),
        OSError("socket"),
        ValueError("not json"),
    ])
    def test_a_fault_leaves_the_warning_in_place(self, fault):
        """The caller uses this to SUPPRESS a warning about a missing
        credential. A learner whose credential really is missing must
        still be told, so an unanswerable question must not silence it.
        """
        assert ask.this_is_the_course_template(self.Repo(fault)) is False

    def test_it_asks_by_property_and_not_by_name(self):
        """A name is a guess that goes stale on the first rename.

        The CODE only, with the docstring cut away: that docstring names
        the repositories the property was measured on, which is the
        record ADR-0029 asks for and has to stay.
        """
        source = io.open(ask.__file__.replace(".pyc", ".py"),
                         encoding="utf-8").read()
        whole = source.partition("def this_is_the_course_template")[2]
        whole = whole.partition("\ndef ")[0]
        code = whole.split(chr(34) * 3)[2]
        assert "is_template" in code
        assert "nucleo-f401re" not in code
        assert ".repo ==" not in code

    def test_the_question_is_asked_only_where_it_is_needed(self):
        """Once per push for every learner would be a wasted API call on
        the common path. It belongs in the branch that is otherwise
        wrong."""
        source = io.open(ask.__file__.replace(".pyc", ".py"),
                         encoding="utf-8").read()
        assert source.count("this_is_the_course_template(") == 2
        after = source.partition("    if not args.token:")[2]
        assert "this_is_the_course_template(" in after.partition(
            "\n    course = Course(")[0]


# --------------------------------------------------------------------
class TestTheTemplateArrivingIsNotASubmission:
    """Creating a repository from the template is a push, and it used to
    cost the learner a request.

    Measured on S007, 2026-11-09, the first repository created after the
    marker entered the template:

        01:54:21  S007 "Check my work"      <- the initial commit
        01:54:48  grade: requested by S007

    All 71 files changed, the marker among them, so `only the marker`
    was correctly False and the tool asked. The run then reported
    `Nothing new from 2 active learner(s)` and skipped the new learner,
    because the roster had not moved them to `active`. One of their ten
    spent on their first day, and nothing back for it.
    """

    class Repo:
        def __init__(self, detail):
            self.detail = detail
            self.asked = []

        def commit_detail(self, sha):
            self.asked.append(sha)
            if isinstance(self.detail, Exception):
                raise self.detail
            return self.detail

    # The real shape, from S007's c393f28.
    INITIAL = {"parents": [], "files": [{"filename": "README.md"}]}
    ORDINARY = {"parents": [{"sha": "abc123"}],
                "files": [{"filename": "exercises/01/main.c"}]}

    def test_a_parentless_commit_is_the_repository_arriving(self):
        assert ask.the_repository_was_just_created(
            self.Repo(self.INITIAL), "c393f28") is True

    def test_a_commit_with_a_parent_is_not(self):
        """A learner creating a branch also arrives with no `before`."""
        assert ask.the_repository_was_just_created(
            self.Repo(self.ORDINARY), "deadbee") is False

    def test_a_missing_parents_key_is_not_assumed_to_be_initial(self):
        """Absent is not the same as empty, but both read as 'no
        parents' here -- and that is the WRONG direction to guess, so
        this pins which way it goes."""
        assert ask.the_repository_was_just_created(
            self.Repo({"files": []}), "x") is True

    def test_no_head_is_not_a_creation(self):
        repo = self.Repo(self.INITIAL)
        assert ask.the_repository_was_just_created(repo, "") is False
        assert repo.asked == [], "it asked the API with nothing to ask about"

    @pytest.mark.parametrize("fault", [
        urllib.error.URLError("down"),
        OSError("socket"),
    ])
    def test_a_fault_propagates_rather_than_deciding(self, fault):
        """`changed_in_this_push` raises on a network fault and the
        caller reads that as 'unknown, so ask'. This must behave the
        same way: silently answering False would be a guess that costs
        nothing, but answering True would skip a real submission."""
        with pytest.raises(type(fault)):
            ask.the_repository_was_just_created(self.Repo(fault), "x")

    def test_it_is_only_asked_when_there_is_no_before(self):
        """One API call, on a path taken about once per repository."""
        source = io.open(ask.__file__.replace(".pyc", ".py"),
                         encoding="utf-8").read()
        call = source.partition("the_repository_was_just_created(own")[0]
        assert call.rstrip().endswith("a_branch_was_just_created(before) and \\")

    def test_the_learner_is_told_rather_than_left_wondering(self):
        """A notice, not silence: somebody looking at a brand new
        repository's first green tick should know why nothing happened.
        """
        source = io.open(ask.__file__.replace(".pyc", ".py"),
                         encoding="utf-8").read()
        after = source.partition("the repository's first commit")[2]
        said = after.partition("return 0")[0]
        assert "no request was used" in said
        assert "nothing to grade yet" in said
