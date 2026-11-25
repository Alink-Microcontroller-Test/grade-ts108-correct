"""Ask the course to grade this repository, if today's allowance allows it.

WHY THIS IS A TOOL AND NOT FOUR LINES OF WORKFLOW
-------------------------------------------------
Every rule in here is a condition that has to hold when nobody is
watching: how many requests have already been made, whether this learner
switched automatic grading on, and what to say when the answer is no. A
condition written into an Actions `if:` expression cannot be tested at
all, and this one decides whether money is spent.

WHAT IT COSTS, AND WHY THE COUNTING HAPPENS HERE
-------------------------------------------------
A grading run bills three minutes in the course's repository. This script
runs inside the compile check that the push had already started and
already paid for, so counting here is free -- and refusing here means a
learner who has run out can push twenty more times at no cost to the
course at all.

Counting on the course's side would have been simpler and authoritative,
and it would have billed a minute to say no. The learner most likely to
be refused is the one pushing in a loop, which is exactly the case that
has to be free. ADR-0040 records the arithmetic.

HOW THE COUNT IS TAKEN
----------------------
By listing the course's grading runs for today and matching the run name,
which carries who asked. The runs list endpoint does not return a
dispatch's inputs, so the name is the only place the asker survives into
a listing -- which is why `run-name:` in the course's grade.yml is
load-bearing and not decoration.

The day is a JST day. A learner in Japan who runs out at 23:00 gets their
allowance back in an hour, not in ten.

WHEN ASKING PRODUCES NOTHING
----------------------------
The course answers by commenting on the learner's Issue, and it only
comments when it has something to say: a verdict that has moved, a new
exercise attempted, a failure that is now a pass. A learner who asks
having changed nothing gets a grading run and silence.

That is right -- repeating yesterday's verdict is noise -- but silence
after being told to expect an answer is the exact complaint this whole
mechanism was built to end, so the message below says it in advance.
Observed on 2026-11-06: a request whose four exercises came back
passed / unchanged / not-started / unchanged produced no comment, and
nothing told the learner why.

WHAT THE CREDENTIAL CAN DO
--------------------------
`Actions: write` on the course's repository, and nothing else. It cannot
read one byte of content there, so it cannot reach the reference
solutions, the ledger or the roster. You can print it out of this
workflow if you want to; ADR-0041 says what that gets you, which is the
ability to start the grading runs you could already start.

    python tools/ask_for_feedback.py --owner ORG --learner S001
"""

import argparse
import datetime
import json
import os
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request

# Ten a day, per learner. Not a measurement -- 45 commits across five
# learners contain no day on which one learner pushed ten times, so
# nothing observed says what the right number is. It is a budget figure:
# ten requests is thirty billed minutes, and a cohort of 100 all
# exhausting it every weekday is still inside what the course can afford.
#
# The nightly run counts are what will say whether it is wrong.
# NOT THE ONLY DAILY LIMIT OF TEN. This one bounds how many grading runs
# a learner may START in a day, and it is enforced here, in their own
# repository. The other, DAILY_CAP in `course-operations/tools/assist.py`,
# bounds how many assistant responses the course will spend on one
# learner.
#
# They do not bind together: one run judges every exercise, so a single
# request can spend several responses there, and this allowance can still
# read as having requests left when the assistant cap has bound. The
# course's sweep checks that this number never exceeds that one.
DAILY_ALLOWANCE = 10

# The marker that turns grading on for every push. The template ships it,
# empty, so grading is on from the moment a learner is enrolled, and
# deleting it is how a learner turns grading off.
#
# Deliberately NOT one of the course-owned paths refresh_learner_copies.py
# keeps current: restoring it would override that choice on the next
# refresh, turning a learner's own switch into one the course holds down.
MARKER = ".grade-on-push"

# The trailer the course puts in a commit message when IT writes into a
# learner's repository, from
# `course-operations/tools/refresh_learner_copies.py`. A push carrying it on
# every commit is the course's own and asks for nothing.
#
# Pinned across the two repositories by a check in the course's `sweep.py`,
# because the string lives in one tree and is read in the other, and a
# rename in one of them would silently start charging learners again.
#
# A learner CAN put this in their own commit message. The consequence is
# that their push is not graded, which costs them the feedback they wanted
# and nothing else -- so it is a way to hurt yourself rather than a way to
# cheat, and worth less complication than it would take to prevent.
COURSE_WROTE_THIS = "[course-update]"

JST = datetime.timezone(datetime.timedelta(hours=9))

# How an Issue opened by the course is recognised from this side. The
# course writes it into the Issue BODY -- one Issue per exercise -- and
# `deliver.py` finds its own Issues the same way. Matching the prefix
# rather than a whole marker is deliberate: this side does not know or
# care which exercise the Issue belongs to.
COURSE_ISSUE_MARKER = "<!-- course-operations exercise="

# How this tool recognises its own refusal notice, carrying the JST date
# so yesterday's notice does not suppress today's. The tool keeps no state
# between runs, so the Issue is where "already told" is remembered.
NOTICE_MARKER = "<!-- ask-for-feedback allowance %s -->"


def annotate(level, message):
    """A GitHub Actions annotation, which shows in the run summary.

    NOT the primary channel, and this docstring used to say the opposite.
    It claimed the run log is "the only place a learner is already looking
    when they are waiting for feedback" and credited ADR-0039 for it.
    ADR-0039 says no such thing: it rejected the Actions log precisely
    because a report left there reaches nobody, on the evidence of three
    faults that ran for weeks while the evidence sat in a log the whole
    time, and it chose an Issue instead.

    A learner waiting for feedback is reading their Issue. The annotation
    is for somebody who went to the Actions tab -- useful, but second.
    A refused request is reported on the Issue as well (ADR-0042).
    """
    print("::%s title=Feedback::%s" % (level, message))


class Course:
    """The two calls this needs against the course's repository."""

    def __init__(self, token, owner, repo, workflow):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.workflow = workflow

    def _request(self, method, path, body=None):
        url = "https://api.github.com%s" % path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "Bearer %s" % self.token)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}

    def runs_today(self, since):
        """Grading runs created since `since`, as (display_title, ...).

        One call. `per_page=100` is well past a day's worth: the whole
        cohort would have to ask a hundred times between them.

        `since` is percent-encoded, and that is not tidiness. A JST
        timestamp ends in "+09:00", and a raw "+" in a query string
        means a space -- so the filter arrives as a malformed date and
        GitHub answers with an empty list rather than an error. The
        count then reads as "no requests today" on every push and the
        allowance never binds, which is the one thing in this design
        standing between a learner pushing in a loop and the course
        paying three minutes a time for it.

        Measured against three runs it should have found: unencoded
        returned 0, encoded returned 3.
        """
        path = ("/repos/%s/%s/actions/workflows/%s/runs"
                "?event=workflow_dispatch&per_page=100&created=%%3E%%3D%s"
                % (self.owner, self.repo, self.workflow,
                   urllib.parse.quote(since, safe="")))
        found = self._request("GET", path)
        return [r.get("display_title", "") or r.get("name", "")
                for r in found.get("workflow_runs", [])]

    def dispatch(self, ref, learner, left="", allowance=""):
        # Both inputs are STRINGS, including the boolean one. The API
        # takes workflow_dispatch inputs as strings and the previous
        # dispatcher sent "false" the same way, measured working over
        # dozens of real runs -- so this is the proven shape rather than
        # the obvious one.
        #
        # `dry_run` is sent explicitly, and it is not noise. It defaults
        # to TRUE on that workflow so a person pressing the button there
        # changes nothing by accident, and a learner's request is a
        # workflow_dispatch too: letting the default stand would grade
        # and then deliver nothing, in silence. grade.yml locks the same
        # door from its side by requiring an empty `learner`; either
        # alone is sufficient, which is why there are two.
        self._request(
            "POST",
            "/repos/%s/%s/actions/workflows/%s/dispatches"
            % (self.owner, self.repo, self.workflow),
            {"ref": ref, "inputs": {
                "learner": learner,
                "dry_run": "false",
                # Strings, like every other input, for the reason above.
                # The course prints these and never acts on them: the
                # allowance is enforced here, in the learner's own
                # repository, so these add no trust the design did not
                # already extend (ADR-0041, ADR-0042).
                "requests_left": str(left),
                "requests_allowance": str(allowance)}})


def requests_used(titles, learner):
    """How many of today's runs this learner asked for.

    Pure, so the matching is testable without a network -- and the
    matching is the part that can go quietly wrong. It must not count
    S0011's runs toward S001, which a bare substring test would: the
    name "grade: requested by S0011" contains "requested by S001".
    """
    wanted = "requested by %s" % learner
    used = 0
    for title in titles:
        if not title.endswith(wanted):
            continue
        used += 1
    return used


def changed_paths(event_path):
    """Every path this push touched, from the Actions event payload.

    Read here rather than with `git diff` because the checkout is
    shallow, so the previous head is not in the clone -- and rather than
    with jq in the workflow, because a shell expression in a YAML string
    is the one part of this that could not be tested.

    Returns [] for anything that is not a push: a workflow_dispatch has
    no commits, and [] means "unknown", which asks.
    """
    if not event_path or not os.path.isfile(event_path):
        return []
    try:
        with open(event_path, encoding="utf-8") as handle:
            event = json.load(handle)
    except (OSError, ValueError):
        return []
    found = []
    for commit in event.get("commits") or ():
        for key in ("added", "modified", "removed"):
            found.extend(commit.get(key) or ())
    return found


def every_commit_is_the_courses(event_path):
    """Did the course make this push, rather than the learner?

    Read from the payload, which costs no API call. The payload's commits
    carry no file lists -- that is why the marker-only rule has to ask the
    API -- but they do carry messages, and a message is all this needs.

    EVERY commit, not any. A push carrying one of the course's commits and
    one of the learner's is the learner's push and must be graded; being
    wrong in that direction costs a learner a request, and being wrong in
    the other costs them the grading they asked for.

    Unknown returns False, which asks. The same way round as every other
    unknown here: a push the course made and failed to recognise spends a
    request, while a learner's push mistaken for the course's would
    silently never be graded.
    """
    if not event_path or not os.path.isfile(event_path):
        return False
    try:
        with open(event_path, encoding="utf-8") as handle:
            event = json.load(handle)
    except (OSError, ValueError):
        return False

    commits = list(event.get("commits") or ())
    if not commits:
        # A payload may carry `head_commit` with no `commits` list.
        head = event.get("head_commit") or {}
        commits = [head] if head else []
    if not commits:
        # A workflow_dispatch has none, and neither does a push whose
        # payload could not be read. Not the course's.
        return False

    return all(COURSE_WROTE_THIS in (c.get("message") or "")
               for c in commits)


def push_range(event_path):
    """(before, after) for this push, from the payload. ("", "") if unknown.

    Only these two fields are taken from the payload, because only these
    two were measured present. Everything about which FILES changed comes
    from the API.
    """
    if not event_path or not os.path.isfile(event_path):
        return "", ""
    try:
        with open(event_path, encoding="utf-8") as handle:
            event = json.load(handle)
    except (OSError, ValueError):
        return "", ""
    if not isinstance(event, dict):
        return "", ""
    return event.get("before") or "", event.get("after") or ""


def a_branch_was_just_created(before):
    """GitHub sends forty zeros as `before` for a new branch."""
    return not before or set(before) == {"0"}


def changed_in_this_push(repo, before, after):
    """Every path this push changed, from the API rather than the payload.

    Authoritative. The payload's commit objects were measured on
    2026-11-06 to carry no file lists at all -- `commits` is present and
    populated, and each commit lacks `added`, `modified` and `removed` --
    which is why the marker-only rule read every push as "unknown" and
    asked anyway.

    `compare` rather than one commit, because a push can carry several
    and the rule is about the push. For a newly created branch there is
    no range, so the head commit alone is the whole of it.

    Raises on a network fault. The caller decides what that means, and it
    means "ask", for the same reason an unreadable count does.
    """
    if not after:
        return []
    data = (repo.commit_detail(after) if a_branch_was_just_created(before)
            else repo.compare(before, after))
    return [f.get("filename") for f in (data.get("files") or ())
            if f.get("filename")]


def the_repository_was_just_created(repo, after):
    """Is this push the repository's very first commit?

    A repository made from the course template arrives as a single
    commit with NO PARENT, carrying every file the template has. That is
    the course putting a learner's repository there, not the learner
    submitting anything, and asking for it costs them one of their ten
    on their first day and returns nothing -- the roster has not moved
    them to `active`, so the run that starts skips them.

    Asked by `parents`, because a commit with none is the one thing that
    cannot be anything else. A learner creating a branch pushes a commit
    that has a parent, and so does a force-push. The file count would
    not do: a learner may legitimately touch every file, and the first
    commit of an empty repository touches none.

    Raises on a network fault, like `changed_in_this_push`, and the
    caller treats it the same way: unknown means ask.

    One API call, and only on a push where `before` is absent -- a
    repository being created or a branch being made. `commit_detail` is
    then fetched again by `changed_in_this_push` on the branch case.
    Twice on a path taken about once in a repository's life is a price
    worth paying to leave that function and its tests alone.
    """
    if not after:
        return False
    return not (repo.commit_detail(after).get("parents") or ())


def describe_event(event_path):
    """Which of the four ways of getting an empty changed-set happened.

    `changed_paths` collapses all of them to [], which is right for the
    decision and useless for the diagnosis -- the marker-only rule has
    failed twice in production and each investigation got the same
    uninformative []. Verified on 2026-11-06 that the parsing itself is
    correct against a real push payload, so what is left is the shape of
    the environment.

    Pure except for reading the file. Returns a sentence for the log.
    """
    if not event_path:
        return "GITHUB_EVENT_PATH is not set"
    if not os.path.isfile(event_path):
        return "GITHUB_EVENT_PATH=%s is not a file" % event_path
    try:
        with open(event_path, encoding="utf-8") as handle:
            event = json.load(handle)
    except (OSError, ValueError) as exc:
        return "GITHUB_EVENT_PATH=%s unreadable (%s)" % (event_path, exc)
    if not isinstance(event, dict):
        return "GITHUB_EVENT_PATH=%s holds %s, not an object" % (
            event_path, type(event).__name__)
    commits = event.get("commits")
    return ("GITHUB_EVENT_PATH read; keys=%s; commits=%s"
            % (sorted(event)[:12],
               "ABSENT" if commits is None else len(commits)))


def only_the_marker_changed(paths):
    """Did this push change the marker and nothing else?

    `paths` is what the push event says changed. Unknown or empty returns
    False, deliberately: this rule may only suppress a request when it is
    CERTAIN there is nothing to grade. Wrongly skipping leaves a learner
    who asked with silence, which is the fault this change exists to end.
    Wrongly asking costs three billed minutes. Those are not symmetrical.

    True for removing the marker as well as adding it -- the file is in
    the changed set either way, and neither is a submission.
    """
    seen = {p.strip() for p in paths or () if p and p.strip()}
    return seen == {MARKER}


def refused_for_allowance(marker_present, asked_by_hand, used,
                          allowance=DAILY_ALLOWANCE, only_marker=False):
    """Was this request refused because the allowance was spent?

    The same question `decide` answers on its way to a message, asked
    separately because only this refusal gets a comment on the Issue --
    "automatic grading is off" and "you only flipped the switch" are not
    refusals and must not post anything.

    Duplicating the branch would let the two drift, so a test asserts they
    agree across every combination of inputs rather than trusting that
    they look alike.
    """
    if only_marker and not asked_by_hand:
        return False
    if not marker_present and not asked_by_hand:
        return False
    return used >= allowance


def refusal_notice(today, allowance=DAILY_ALLOWANCE):
    """What a learner reads on their Issue when the allowance is spent.

    Japanese, because every other comment on that Issue is Japanese and a
    lone English one reads as a different system intruding.

    Three facts, and deliberately not the fourth. The course's hint-cap
    notice ends by sending the learner to a teacher, which is right there
    -- that cap is reached by failing ten times. This one is reached by
    pushing ten times, which a learner can do while passing everything,
    and repeating the sentence where it does not apply devalues it where
    it does.

    0時（JST）rather than 明日: the allowance is a JST day, so a learner
    who runs out at 23:00 gets it back in an hour, not in ten.
    """
    return "\n".join([
        NOTICE_MARKER % today,
        "",
        "**本日の依頼回数を使い切りました。**",
        "",
        "本日の依頼は%d回までです。この push は採点に送られていません。"
        "回数は0時（JST）に戻ります。" % allowance,
        "",
        "コンパイルの確認は実行されています。"
        "Actions タブの「Check my work」で結果を見てください。",
    ])


def course_issue(issues):
    """The Issue to post a refusal on: the most recently updated open one
    the course opened, or None.

    Deriving the exercise from the push instead was tried on paper and has
    three holes: the manual button carries no push payload at all, a push
    can touch two exercises, and a push can touch none. The button decides
    it -- a learner who pressed a button and got silence is the sharpest
    form of the fault this exists to fix.

    In the case that actually produces refusals, a learner pushing
    repeatedly at one exercise, both rules give the same answer: the Issue
    they are iterating on IS the most recently updated one.

    AN OPEN ISSUE IS PREFERRED, BUT A CLOSED ONE WILL DO. Requiring an
    open one was the first version and it was measured failing on S006 on
    2026-11-06: the learner had passed exercise 01, so the course had
    closed its Issue, and the refusal reached nobody. Having passed
    everything so far is the most ordinary state there is, so that rule
    left the commonest case silent.

    Commenting on a closed Issue is NOT as good, and `deliver_issue` says
    so in the course: it reopens first, because a learner scanning open
    Issues sees nothing. The difference is what the comment is for. A
    result is about the learner's code and belongs where they will look
    for it; this is a transient notice about their allowance, and GitHub
    emails the participants of a closed Issue just as it does an open one.

    Reopening instead was rejected. An Issue that reopens says the
    exercise regressed, which would be a lie told in a louder voice.

    Pure. `issues` is whatever the API returned; the sort is done here
    rather than trusted from the query.
    """
    ours = [i for i in issues or ()
            if COURSE_ISSUE_MARKER in (i.get("body") or "")
            and not i.get("pull_request")]
    if not ours:
        return None

    def newest(issue):
        return (issue.get("updated_at") or "", issue.get("number") or 0)

    still_open = [i for i in ours if i.get("state") == "open"]
    return max(still_open or ours, key=newest)


def already_told_today(comments, today):
    """Has this tool already posted today's refusal notice?

    Keyed on the marker and the date together, so yesterday's notice does
    not suppress today's and today's is not posted twice. Pure.
    """
    wanted = NOTICE_MARKER % today
    return any(wanted in (c.get("body") or "") for c in comments or ())


class OwnRepository:
    """The learner's own repository, reached with the BUILT-IN token.

    A separate class from `Course` because it is a separate credential
    with a separate reach, and conflating them is how one ends up being
    used where the other was meant. The course credential cannot touch
    this repository; this one cannot touch the course (ADR-0042).
    """

    def __init__(self, token, owner, repo):
        self.token = token
        self.owner = owner
        self.repo = repo

    def _request(self, method, path, body=None):
        url = "https://api.github.com%s" % path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "Bearer %s" % self.token)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}

    def issues(self, state="all"):
        """Open AND closed, deliberately.

        Asking only for open ones was the first version and it left the
        commonest learner silent: pass an exercise and the course closes
        its Issue, so a learner who has passed everything so far has no
        open Issue at all.
        """
        return self._request(
            "GET", "/repos/%s/%s/issues?state=%s&per_page=100&sort=updated"
            % (self.owner, self.repo, state))

    def detail(self):
        return self._request(
            "GET", "/repos/%s/%s" % (self.owner, self.repo))

    def commit_detail(self, sha):
        return self._request(
            "GET", "/repos/%s/%s/commits/%s" % (self.owner, self.repo, sha))

    def compare(self, base, head):
        return self._request(
            "GET", "/repos/%s/%s/compare/%s...%s"
            % (self.owner, self.repo, base, head))

    def comments(self, number):
        return self._request(
            "GET", "/repos/%s/%s/issues/%s/comments?per_page=100"
            % (self.owner, self.repo, number))

    def comment(self, number, body):
        return self._request(
            "POST", "/repos/%s/%s/issues/%s/comments"
            % (self.owner, self.repo, number), {"body": body})


def this_is_the_course_template(repo):
    """Is this the repository learners are created FROM, rather than one?

    Asked by `is_template`, which GitHub maintains, rather than by
    comparing the repository's name against one written down here. A name
    is a guess that goes stale the first time somebody renames anything;
    this is the property that makes the thing what it is.

    Measured 2026-11-09 in `<your-organisation>`: true on `nucleo-f401re`, false
    on `S002`, `S006` and `course-operations`.

    Returns False when it cannot be asked, and that direction is
    deliberate. The only caller uses this to SUPPRESS a message about a
    missing credential, and a learner whose credential really is missing
    must still be told. So a network fault leaves the warning in place
    rather than silencing it.
    """
    try:
        return bool(repo.detail().get("is_template"))
    except (urllib.error.URLError, OSError, ValueError):
        return False


def tell_them_on_the_issue(repo, today, allowance=DAILY_ALLOWANCE):
    """Post the refusal where the learner is waiting. Returns what happened.

    ADR-0039 decided that a report reaching nobody is not a report, and
    rejected the Actions log on the evidence of three faults that ran for
    weeks while the evidence sat in a log. A learner waiting for feedback
    is reading their Issue.

    Returns one of "posted", "already", "no-issue" -- for the annotation,
    and so a test can tell the three apart without inspecting calls.
    """
    issue = course_issue(repo.issues())
    if issue is None:
        return "no-issue"
    number = issue.get("number")
    if already_told_today(repo.comments(number), today):
        return "already"
    repo.comment(number, refusal_notice(today, allowance))
    return "posted"


def requests_left_after_this(used, allowance=DAILY_ALLOWANCE):
    """How many requests the learner has left once this one is sent.

    One function because there are two callers and they must not be able
    to disagree: the message `decide` writes into the Actions annotation,
    and the `requests_left` input `Course.dispatch` sends on to
    `deliver.py`, which puts it in the comment on the learner's Issue.
    Those two numbers are read minutes apart by the same person. Both
    were spelled `allowance - used - 1` in their own place, which is an
    off-by-one waiting for an edit to only one of them -- and an
    off-by-one here is invisible, because either number is plausible.

    Never negative: `decide` refuses before this is reached when the
    allowance is spent, but a caller that did not would otherwise print
    `-1 requests left`.
    """
    return max(0, allowance - used - 1)


def decide(marker_present, asked_by_hand, used, allowance=DAILY_ALLOWANCE,
           only_marker=False):
    """Returns (should_dispatch, level, message). Pure.

    Four outcomes now, and each one says something, because the failure
    this whole change was written to fix was a learner watching for an
    answer that was never coming.
    """
    if only_marker and not asked_by_hand:
        # Checked before the allowance, because "nothing to grade" is a
        # truer answer than "you are out of requests" and costs nothing
        # either way.
        if marker_present:
            return (False, "notice",
                    "Automatic grading is on from now on. This push only "
                    "added %s, so there is nothing new to grade and no "
                    "request was used. Your next push will be graded."
                    % MARKER)
        return (False, "notice",
                "Automatic grading is off from now on. Pushing will run "
                "this check only. You can still ask once at a time with "
                "the 'Ask for feedback' action in the Actions tab.")

    if not marker_present and not asked_by_hand:
        return (False, "notice",
                "This push was not graded. Pushing runs this check only. "
                "To be graded, use the 'Ask for feedback' action in the "
                "Actions tab -- or commit an empty %s file to be graded on "
                "every push from now on." % MARKER)

    if used >= allowance:
        return (False, "warning",
                "Today's allowance of %d feedback requests is used up, so "
                "this one was not sent. It costs nothing, and the allowance "
                "returns at midnight JST. Your code was still checked above."
                % allowance)

    left = requests_left_after_this(used, allowance)
    return (True, "notice",
            "Asked the course for feedback. It usually answers in about "
            "three minutes, as a comment on your Issue. If nothing has "
            "changed in your work since it last looked, it has nothing to "
            "add and will not comment -- that is normal, not a fault. %d of "
            "today's %d requests left after this one." % (left, allowance))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--learner", required=True,
                        help="the learner's repository name, e.g. S001")
    parser.add_argument("--course-repo", default="course-operations")
    parser.add_argument("--workflow", default="grade.yml")
    parser.add_argument("--ref", default="main",
                        help="the course's ref to run grading on")
    parser.add_argument("--changed", default="",
                        help="comma-separated paths this push changed. "
                             "Empty asks the API what the push changed, "
                             "and falls back to GITHUB_EVENT_PATH, which "
                             "was measured on 2026-11-06 to carry no file "
                             "lists. Still unknown after both means "
                             "unknown, which asks for feedback")
    parser.add_argument("--by-hand", action="store_true",
                        help="the learner pressed the button, so the "
                             "marker file is not consulted")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"),
                        help="reaches the course and nothing else")
    # A SECOND credential, and not interchangeable with the first. The
    # course token cannot touch this repository, and this one cannot touch
    # the course. It is the workflow's built-in token, passed under its own
    # name because the step sets GITHUB_TOKEN to the course credential.
    parser.add_argument("--repo-token",
                        default=os.environ.get("LEARNER_REPO_TOKEN"),
                        help="reaches this repository's Issues and its own "
                             "commits, and nothing else. Absent means the "
                             "refusal is annotated rather than posted, and "
                             "the changed-file list falls back to the push "
                             "payload")
    args = parser.parse_args(argv)

    marker_present = os.path.exists(MARKER)
    event_path = os.environ.get("GITHUB_EVENT_PATH")

    # FIRST, and before any token is looked at or any call is made: a push
    # the course made itself is not a submission. It costs the learner
    # nothing and asks for nothing.
    #
    # `--by-hand` is exempt from the exemption: a learner who dispatched
    # the workflow deliberately is asking, whatever the last commit on the
    # branch happens to say.
    if not args.by_hand and every_commit_is_the_courses(event_path):
        print("the course made this push, so there is nothing to grade "
              "and no request was used")
        annotate("notice",
                 "The course updated a file in this repository, and that "
                 "is what started this run. Nothing was graded and none of "
                 "your %d requests for today was used. The commit message "
                 "says what changed." % DAILY_ALLOWANCE)
        return 0

    source = "--changed"
    changed = [p for p in args.changed.split(",") if p.strip()]

    if not changed and args.repo_token:
        before, after = push_range(event_path)
        own = OwnRepository(args.repo_token, args.owner, args.learner)
        try:
            # Before the changed set is even looked at, because on this
            # push the changed set is every file the template has and
            # looks exactly like a learner who rewrote everything.
            if a_branch_was_just_created(before) and \
                    the_repository_was_just_created(own, after):
                print("the repository's first commit: the template "
                      "arriving, not a submission")
                annotate("notice",
                         "This repository has just been created from the "
                         "course template. There is nothing to grade yet "
                         "and no request was used. Push your work and it "
                         "will be graded.")
                return 0

            changed = changed_in_this_push(own, before, after)
            source = "the API"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # Unknown, which asks. Never fail the step over it: the cost
            # of being wrong here is three billed minutes, and the cost
            # of refusing on an unreadable answer is a learner who asked
            # and was ignored.
            print("could not ask what this push changed (%s)" % exc)

    if not changed:
        # The payload, which was the only source before the learner
        # workflow had a token for its own repository. Kept as a
        # fallback, and measured not to work on 2026-11-06 -- the commit
        # objects carry no file lists -- so this is a floor, not a
        # second opinion.
        changed = changed_paths(event_path)
        source = "the payload"

    only_marker = only_the_marker_changed(changed)

    # Plain stdout, not an annotation: it belongs in the step log for
    # whoever is debugging, not in the learner's run summary. Added
    # 2026-11-06 because the marker-only rule worked against every
    # payload shape tested here and did not fire against the real one,
    # and guessing at the difference twice was enough.
    print("changed paths seen: %r from %s (only the marker: %s)"
          % (changed, source, only_marker))
    if not changed:
        # Only when it came out empty, which is the case that has gone
        # unexplained twice. A normal push logs the line above and stops.
        print("  why it was empty: %s"
              % describe_event(os.environ.get("GITHUB_EVENT_PATH")))

    if only_marker and not args.by_hand:
        # Before the token is looked at, like the case below: a push that
        # only flips the switch needs no credential and should not
        # complain about one.
        _, level, message = decide(marker_present, False, 0,
                                   only_marker=True)
        annotate(level, message)
        return 0

    if not marker_present and not args.by_hand:
        # Decided before the token is looked at, so a repository with no
        # marker and no secret is silent rather than complaining about a
        # credential it was never going to use.
        _, level, message = decide(False, False, 0)
        annotate(level, message)
        return 0

    if not args.token:
        # The course template reaches here on every push once it carries
        # the marker, and it has no credential because it is not a
        # learner and has nobody to ask for. Checked HERE rather than at
        # the top of main, so the extra API call happens only on the one
        # path that would otherwise be wrong -- not on every push by
        # every learner.
        if args.repo_token and this_is_the_course_template(
                OwnRepository(args.repo_token, args.owner, args.learner)):
            print("this is the course template rather than a learner's "
                  "repository, so there is nobody to ask for")
            return 0

        # A finding, not a silent pass. This is the failure mode ADR-0040
        # calls the worst in the design: without the secret every request
        # fails and nothing says why.
        annotate("error",
                 "Cannot ask for feedback: this repository has no grading "
                 "credential. That is the course's setup to fix, not "
                 "yours -- tell whoever runs the course that "
                 "COURSE_GRADE_TRIGGER is missing from this repository. "
                 "Enrolment restores it on its next run.")
        return 0

    course = Course(args.token, args.owner, args.course_repo, args.workflow)
    midnight = datetime.datetime.now(JST).replace(
        hour=0, minute=0, second=0, microsecond=0)

    try:
        used = requests_used(course.runs_today(midnight.isoformat()),
                             args.learner)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # Cannot count, so cannot know. Ask anyway and say so: refusing
        # on an unreadable count would make a transient API fault look
        # to the learner exactly like an exhausted allowance, and the
        # cost of being wrong is three billed minutes.
        annotate("warning",
                 "Could not check today's allowance (%s), so the request "
                 "was sent without counting it." % exc)
        used = 0

    send, level, message = decide(marker_present, args.by_hand, used,
                                  only_marker=only_marker)
    annotate(level, message)

    if not send:
        if refused_for_allowance(marker_present, args.by_hand, used,
                                 only_marker=only_marker):
            # Only THIS refusal gets a comment. "Automatic grading is off"
            # and "you only flipped the switch" are not refusals, and a
            # learner who did not ask for anything should not find the
            # course talking to them about allowances.
            today = datetime.datetime.now(JST).strftime("%Y-%m-%d")
            if not args.repo_token:
                annotate("warning",
                         "No repository token, so this refusal was not "
                         "posted to your Issue. The message above is the "
                         "whole of it.")
            else:
                try:
                    what = tell_them_on_the_issue(
                        OwnRepository(args.repo_token, args.owner,
                                      args.learner), today)
                    print("refusal notice: %s" % what)
                except (urllib.error.URLError, OSError, ValueError) as exc:
                    # Never fail the step for this. The compile check above
                    # is still the learner's result, and turning it red
                    # would tell them their code is wrong, which is a lie.
                    annotate("warning",
                             "Could not post the refusal to your Issue "
                             "(%s). The message above is the whole of it."
                             % exc)
        return 0

    try:
        course.dispatch(args.ref, args.learner,
                        left=requests_left_after_this(used),
                        allowance=DAILY_ALLOWANCE)
    except (urllib.error.URLError, OSError) as exc:
        annotate("error",
                 "The course did not accept the request (%s). Your code "
                 "was still checked above. The course sweeps twice a day, "
                 "so this work will be graded even if nobody acts." % exc)
    return 0


def say_something_even_if_this_crashed(run):
    """Run `main`, and make sure the learner is told even if it threw.

    The step that calls this carries `continue-on-error: true`, for a
    good reason argued in the workflow: a problem reaching the course
    must not turn a passing check red, because that would tell a learner
    their code is wrong, which would be a lie.

    The cost of that is this: before this wrapper, ANY unhandled
    exception left the learner with a green tick, no annotation and no
    feedback -- the precise failure this whole change exists to end,
    reachable by any bug anywhere above. It happened on 2026-11-06, when
    a bad edit put a SyntaxError in this file: the step died, the check
    stayed green, and nothing anywhere said so.

    So every exit from here says something. Returns an exit code.

    Exits 0 after reporting, deliberately. A non-zero exit from this
    program now means it could not START -- a syntax error, a failed
    import, no interpreter -- which the workflow reports itself, because
    by then nothing in this file is running to do it.
    """
    try:
        return run()
    except Exception as exc:
        # `Exception`, not `BaseException`. A bug raises Exception. The
        # three that do not -- SystemExit, KeyboardInterrupt and
        # GeneratorExit -- are the runner stopping this on purpose, and
        # reporting a cancellation as "something went wrong asking for
        # feedback" would be both wrong and reassuring, which is the
        # worst pair. They propagate.
        # Deliberately vague about whether the request was sent: it is
        # not knowable from here, and guessing either way would be a
        # claim about something the learner cannot check. What IS true
        # is that their code was checked and the sweep will reach them.
        annotate("warning",
                 "Something went wrong while asking the course for "
                 "feedback (%s: %s). Your code was still checked above. "
                 "The course also sweeps twice a day, so this work will "
                 "be graded even if nobody acts."
                 % (type(exc).__name__, exc))
        # To the log, where whoever maintains the course will look. The
        # learner gets the sentence above; this is for us.
        traceback.print_exc()
        return 0


if __name__ == "__main__":
    sys.exit(say_something_even_if_this_crashed(main))
