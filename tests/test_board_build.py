"""Building an exercise from the board view, without Renode or a browser.

The plugin targets the IronPython 2 inside Renode and cannot be imported here,
so three functions are lifted out by source and run against stubs -- the same
trick `test_board_edits.py` uses, and the reason the new code prints with call
syntax rather than the statement form used elsewhere in that file.

What this covers is the logic that can be wrong without anybody noticing: which
requests are refused, which of the build's three outcomes is reported, and
whether a learner's sensor readings are put back. What it cannot cover is the
simulator itself -- that is `test_firmware_reload.py`, which needs a real board.
"""

import io
import json
import os
import re
import threading
import types
import zipfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(os.path.dirname(HERE), "vis", "vis_f401re.py")

with open(PLUGIN, encoding="utf-8") as handle:
    SOURCE = handle.read()


def _slice(start, end):
    return SOURCE[SOURCE.index(start):SOURCE.index(end)]


# Two contiguous ranges. `exercises_in` and `outcome_of` are deliberately
# adjacent and self-contained so one range covers both.
PURE = _slice("def exercises_in(", "def run_course_build(")
UPLOAD = _slice("def firmware_from_upload(", "class _NoRedirect(")
REPO = _slice("def repository_from_config(", "def _read_text(")
NEWEST = _slice("def newest_build_of(", "def fetch_ci_build(")
# Only the retry wrapper. It calls _artifact_bytes_once and
# touches nothing else, so it lifts without urllib2 -- which is
# the whole reason it is a separate function.
RETRY = _slice("def _artifact_bytes(", "def _artifact_bytes_once(")
# Two pieces, not one range: between them sits a class whose base is
# urllib2.HTTPRedirectHandler, and a class body is evaluated when the
# source is exec'd -- so a single slice would need urllib2 here, which
# Python 3 does not have. The harness needs these two functions and
# nothing in between.
BUILD = (_slice("def say_build(", "def repository_from_config(")
         + _slice("def build_exercise(", "def message_received("))


class Harness(object):
    """The plugin's build logic with everything around it replaced."""

    def __init__(self, exercises, code=0, output="Built it", loads=True):
        self.messages = []      # broadcast, to every page
        self.direct = []        # to the page that asked, and only that one
        self.loaded = []
        self.restored = 0
        self.buttons = 0
        self.code = code
        self.output = output
        self.loads = loads

        namespace = {
            "os": os,
            "EXERCISES_DIR": str(exercises),
            "send_message": self.messages.append,
            "send_to": lambda client, message: self.direct.append(message),
            "dumps": json.dumps,
            "build_lock": threading.Lock(),
            "building": [False],
            "run_course_build": lambda target: (self.code, self.output),
            "load_firmware": self._load,
            "restore_learner_values": self._restore,
            "report_buttons": self._report,
        }
        exec(compile(PURE, PLUGIN, "exec"), namespace)
        exec(compile(BUILD, PLUGIN, "exec"), namespace)
        self.namespace = namespace

    def _load(self, elf):
        self.loaded.append(elf)
        return self.loads

    def _restore(self):
        self.restored += 1

    def _report(self):
        self.buttons += 1

    def build(self, exercise):
        self.namespace["build_exercise"]("a-client", exercise)

    @property
    def verdict(self):
        """The BUILD message, read the way the page has to read it.

        The output is the last field because it is JSON and JSON can contain
        the separator, so everything after the third one is rejoined before
        parsing. A test that split naively would pass while the page broke.
        """
        return self._read(self.messages)

    @property
    def refusal(self):
        """The BUILD message sent back to the page that asked, if any."""
        return self._read(self.direct)

    @staticmethod
    def _read(where):
        for message in where:
            if message.startswith("BUILD|"):
                fields = message.split("|")
                return fields[1], fields[2], json.loads("|".join(fields[3:]))
        return None

    @property
    def building_announced(self):
        return [m for m in self.messages if m.startswith("BUILDING|")]


@pytest.fixture
def exercises(tmp_path):
    for name in ("01-first", "02-second"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "main.c").write_text("int main(void) { return 0; }\n")
    # A directory with no main.c is not an exercise.
    (tmp_path / "notes").mkdir()
    return tmp_path


def _built(exercises, name):
    (exercises / name / "firmware.elf").write_bytes(b"\x7fELF not really")


# --- the two pure functions -------------------------------------------------

def test_only_directories_with_a_main_c_are_exercises(exercises):
    found = Harness(exercises).namespace["exercises_in"](str(exercises))
    assert found == ["01-first", "02-second"]


def test_an_exercise_added_later_is_found_without_a_code_change(exercises):
    later = exercises / "99-written-after-this-test"
    later.mkdir()
    (later / "main.c").write_text("int main(void) { return 0; }\n")
    found = Harness(exercises).namespace["exercises_in"](str(exercises))
    assert "99-written-after-this-test" in found


def test_a_missing_directory_is_no_exercises_rather_than_an_error(tmp_path):
    absent = str(tmp_path / "nothing-here")
    assert Harness(tmp_path).namespace["exercises_in"](absent) == []


def test_the_three_exit_codes_mean_three_different_things(exercises):
    outcome_of = Harness(exercises).namespace["outcome_of"]
    assert outcome_of(0) == "BUILT"
    assert outcome_of(1) == "DID_NOT_COMPILE"
    assert outcome_of(2) == "COULD_NOT_BUILD"
    # Anything unexpected is treated as the learner's code, not as a course
    # defect: saying "not your fault" wrongly sends somebody to ask for help
    # about an error they could have read.
    assert outcome_of(7) == "DID_NOT_COMPILE"


# --- what is refused --------------------------------------------------------

def test_an_unknown_exercise_is_refused_and_nothing_is_built(exercises):
    harness = Harness(exercises)
    harness.build("../../etc")
    name, token, text = harness.refusal
    assert (name, token) == ("../../etc", "REFUSED_UNKNOWN")
    assert text == "", "a refusal has no machine output; the page says the words"
    assert harness.loaded == []
    assert harness.building_announced == [], "nothing was started, so say nothing"


def test_a_second_build_while_one_runs_is_refused(exercises):
    _built(exercises, "01-first")
    harness = Harness(exercises)
    harness.namespace["building"][0] = True        # one already in flight
    harness.build("01-first")
    _, token, text = harness.refusal
    assert (token, text) == ("REFUSED_BUSY", "")
    assert harness.loaded == [], "the board must be left as it was"


def test_a_refusal_goes_only_to_the_page_that_asked(exercises):
    """Measured on 2026-11-11, with four pages pressing build together.

    Refusals were broadcast, so every page reported one -- including the page
    whose build was actually running, because somebody else's refusal arrived
    before its own result. The plugin was behaving correctly and every page
    was wrong about it.

    An outcome is everybody's business: the board they are all watching has
    changed. A refusal is about one request and belongs to the page that made
    it. No unit test could have found this; it took four real connections.
    """
    harness = Harness(exercises)
    harness.build("nope")
    assert harness.refusal is not None, "the page that asked was not told"
    assert harness.messages == [], (
        "a refusal was broadcast. Other pages will report a refusal they "
        "never caused, and one of them may be mid-build: %s" % harness.messages)


def test_an_outcome_is_broadcast_to_every_page(exercises):
    """The other half of the rule above, so neither can drift back."""
    _built(exercises, "01-first")
    harness = Harness(exercises)
    harness.build("01-first")
    assert harness.verdict is not None, "the board changed and nobody was told"
    assert harness.refusal is None, (
        "an outcome went to one page only; the others are watching the same "
        "board and will not know it changed")


def test_the_flag_is_released_so_the_next_build_runs(exercises):
    _built(exercises, "01-first")
    harness = Harness(exercises)
    harness.build("01-first")
    assert harness.namespace["building"][0] is False
    harness.build("01-first")
    assert len(harness.loaded) == 2


# --- what is reported -------------------------------------------------------

def test_a_successful_build_loads_the_firmware_and_restores_readings(exercises):
    _built(exercises, "01-first")
    harness = Harness(exercises)
    harness.build("01-first")

    assert harness.building_announced, "the page is told before the wait, not after"
    name, token, output = harness.verdict
    assert (name, token) == ("01-first", "BUILT")
    assert output == "Built it"
    assert harness.loaded == [os.path.join(str(exercises), "01-first",
                                           "firmware.elf")]
    assert harness.restored == 1, "a rebuild must not lose the learner's readings"


def test_code_that_does_not_compile_is_reported_as_theirs(exercises):
    harness = Harness(exercises, code=1, output="main.c:12: error: expected ';'")
    harness.build("01-first")
    _, token, output = harness.verdict
    assert token == "DID_NOT_COMPILE"
    assert "expected ';'" in output
    assert harness.loaded == []
    assert harness.restored == 0


def test_a_build_that_could_not_be_attempted_is_reported_as_ours(exercises):
    harness = Harness(exercises, code=2,
                      output="arm-none-eabi-gcc is not on PATH")
    harness.build("01-first")
    _, token, output = harness.verdict
    assert token == "COULD_NOT_BUILD"
    assert "not on PATH" in output


def test_success_without_a_firmware_is_not_treated_as_success(exercises):
    """Exit 0 and no firmware.elf. The build cannot be believed over the disk."""
    harness = Harness(exercises, code=0)
    harness.build("01-first")                      # no _built() call
    _, token, output = harness.verdict
    assert token == "COULD_NOT_BUILD"
    assert "wrote no firmware" in output
    assert harness.loaded == []


def test_a_build_the_simulator_will_not_load_is_not_a_pass(exercises):
    _built(exercises, "01-first")
    harness = Harness(exercises, loads=False)
    harness.build("01-first")
    _, token, output = harness.verdict
    assert token == "COULD_NOT_BUILD"
    assert "would not load" in output
    assert harness.restored == 0, "nothing to restore onto a board that did not reload"


def test_every_token_the_plugin_sends_has_a_sentence_in_both_languages():
    """The plugin names an outcome; the page says it. Neither side can drift.

    The plugin deliberately contains no learner-facing prose -- it has no
    Japanese in it at all -- so a token it can emit and the page cannot name
    would show a learner the key instead of a sentence, in silence. This is
    the same guard check_documented_commands is: the two halves live in
    different files and only a test can hold them together.
    """
    page_path = os.path.join(os.path.dirname(HERE), "vis", "index.html")
    with open(page_path, encoding="utf-8") as handle:
        page = handle.read()

    def declared(name):
        block = re.search(name + r" = \((.*?)\)\n", SOURCE, re.S)
        assert block, "the plugin no longer declares %s" % name
        return set(re.findall(r'"([A-Z_]+)"', block.group(1)))

    handled = {}
    for plugin_name, page_name in (("BUILD_TOKENS", "BUILD_SAYS"),
                                   ("ENVIRONMENT_TOKENS", "ENV_SAYS")):
        emitted = declared(plugin_name)
        says = re.search(r"const " + page_name + r" = \{(.*?)\};", page, re.S)
        assert says, "the page no longer has a %s table" % page_name
        mapped = dict(re.findall(r'([A-Z_]+):\s*\["([a-z.]+)"', says.group(1)))

        assert emitted, "%s is empty" % plugin_name
        assert emitted == set(mapped), (
            "%s and %s disagree.\n"
            "  only the plugin declares: %s\n"
            "  only the page handles:    %s"
            % (plugin_name, page_name, sorted(emitted - set(mapped)),
               sorted(set(mapped) - emitted)))
        handled.update(mapped)

    # And the declarations must be what the code actually sends, or they are
    # just a comment that happens to be checked. Every token literal in a
    # position that reaches a page has to be one of the declared ones.
    sent = set(re.findall(r'say_build\([^,]+,\s*"([A-Z_]+)"', SOURCE))
    sent |= set(re.findall(r'\btoken = "([A-Z_]+)"', SOURCE))
    sent |= set(re.findall(r'\belse "([A-Z_]+)"', SOURCE))
    sent |= set(re.findall(r'\breturn "([A-Z_]+)"', PURE))
    assert sent, "found no token literals at all; these patterns have gone stale"
    undeclared = sent - declared("BUILD_TOKENS") - declared("ENVIRONMENT_TOKENS")
    assert not undeclared, (
        "the plugin sends tokens it does not declare, so no page can be held "
        "to them: %s" % sorted(undeclared))

    labels = json.loads(re.search(
        r'<script type="application/json" id="vis-labels">(.*?)</script>',
        page, re.S).group(1))
    for token, key in sorted(handled.items()):
        for language in ("ja", "en"):
            assert key in labels[language], (
                "%s maps to %r, which has no %s label" % (token, key, language))


def test_compiler_output_containing_the_separator_survives(exercises):
    """gcc says `||` about perfectly ordinary C.

    The wire format splits on `|`, so this is the case that would corrupt a
    learner's error message in the one place they are already confused.
    """
    gcc = "main.c:9: warning: suggest parentheses around `a || b`\nmain.c:9: |"
    harness = Harness(exercises, code=1, output=gcc)
    harness.build("02-second")
    name, token, output = harness.verdict
    assert (name, token) == ("02-second", "DID_NOT_COMPILE")
    assert output == gcc

# --- what a learner hands over ----------------------------------------------

def _unpacker():
    """firmware_from_upload, runnable here.

    Two substitutions, both because the plugin is written for the IronPython 2
    inside Renode, where `str` is bytes and `StringIO` exists:

      - the magic numbers arrive as bytes, since that is what Python 3's
        zipfile reads and writes;
      - `StringIO` is stood in for by `io.BytesIO`, which is the same thing
        for this purpose -- an in-memory file of bytes, which is how an
        archive arrives over HTTP.

    Nothing else is replaced. The selection logic under test is the plugin's
    own source.
    """
    namespace = {
        "zipfile": zipfile,
        "StringIO": types.SimpleNamespace(StringIO=io.BytesIO),
        "ELF_MAGIC": b"\x7fELF",
        "ZIP_MAGIC": b"PK\x03\x04",
    }
    exec(compile(UPLOAD, PLUGIN, "exec"), namespace)
    return namespace["firmware_from_upload"]


def _elf(body=b"the rest of an elf"):
    return b"\x7fELF" + body


def _zip(members):
    buffer = io.BytesIO()
    archive = zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED)
    for name, body in members.items():
        archive.writestr(name, body)
    archive.close()
    return buffer.getvalue()


def test_a_bare_elf_is_taken_as_it_is():
    """What a Release asset is."""
    image, refusal = _unpacker()(_elf(), "01-first")
    assert refusal is None
    assert image == _elf()


def test_the_archive_member_naming_this_exercise_is_chosen():
    """What an Actions artifact is: every exercise that compiled, in one zip."""
    blob = _zip({"01-first/firmware.elf": _elf(b"one"),
                 "02-second/firmware.elf": _elf(b"two"),
                 "03-third/firmware.elf": _elf(b"three")})
    image, refusal = _unpacker()(blob, "02-second")
    assert refusal is None
    assert image == _elf(b"two"), "the wrong exercise would run, silently"


def test_a_lone_member_is_taken_whatever_it_is_called():
    """A learner may rename, or zip one file themselves."""
    blob = _zip({"whatever-they-called-it.elf": _elf(b"only")})
    image, refusal = _unpacker()(blob, "01-first")
    assert refusal is None
    assert image == _elf(b"only")


def test_an_archive_naming_none_of_them_is_refused_rather_than_guessed():
    """The failure this is shaped to avoid: somebody else's exercise, in silence."""
    blob = _zip({"a.elf": _elf(b"a"), "b.elf": _elf(b"b")})
    image, refusal = _unpacker()(blob, "01-first")
    assert image is None
    assert refusal == "REFUSED_NOTHING_INSIDE"


def test_something_that_is_not_firmware_is_refused():
    image, refusal = _unpacker()(b"PDF-1.4 or a screenshot or anything", "01-first")
    assert image is None
    assert refusal == "REFUSED_NOT_FIRMWARE"


def test_an_archive_holding_no_firmware_is_refused():
    """Judged on the bytes, not the name: a .elf that is not one."""
    blob = _zip({"01-first/firmware.elf": b"I was renamed, not compiled"})
    image, refusal = _unpacker()(blob, "01-first")
    assert image is None
    assert refusal == "REFUSED_NOT_FIRMWARE"


def test_a_corrupt_archive_is_refused_rather_than_raising():
    """A truncated download. It must not take the connection down with it."""
    blob = _zip({"01-first/firmware.elf": _elf()})[:40]
    image, refusal = _unpacker()(blob, "01-first")
    assert image is None
    assert refusal == "REFUSED_NOT_FIRMWARE"


def test_an_empty_handover_is_refused():
    image, refusal = _unpacker()(b"", "01-first")
    assert image is None
    assert refusal == "REFUSED_NOT_FIRMWARE"

# --- which repository, and which run ----------------------------------------

def _lifted(source, **extra):
    namespace = dict(extra)
    exec(compile(source, PLUGIN, "exec"), namespace)
    return namespace


CONFIG_HTTPS = """[core]
	repositoryformatversion = 0
[remote "origin"]
	url = https://github.com/<your-organisation>/S008.git
	fetch = +refs/heads/*:refs/remotes/origin/*
[branch "main"]
	remote = origin
"""

CONFIG_SSH = """[remote "origin"]
	url = git@github.com:<your-organisation>/S008.git
"""

CONFIG_WITH_CREDENTIAL = """[remote "origin"]
	url = https://x-access-token:ghs_secret@github.com/<your-organisation>/S008.git
"""

CONFIG_TWO_REMOTES = """[remote "upstream"]
	url = https://github.com/Somebody-Else/not-yours.git
[remote "origin"]
	url = https://github.com/<your-organisation>/S008.git
"""


def test_the_repository_is_read_from_an_https_clone():
    where = _lifted(REPO)["repository_from_config"]
    assert where(CONFIG_HTTPS) == "<your-organisation>/S008"


def test_the_repository_is_read_from_an_ssh_clone():
    """No credential for the fetch, but the control still has to name the
    right repository in order to say so."""
    where = _lifted(REPO)["repository_from_config"]
    assert where(CONFIG_SSH) == "<your-organisation>/S008"


def test_a_credential_in_the_url_does_not_become_the_owner():
    """`https://x-access-token:...@github.com/owner/repo` is a real shape.

    Read naively, the owner becomes the token. The request would then go
    somewhere that does not exist, carrying a credential.
    """
    where = _lifted(REPO)["repository_from_config"]
    assert where(CONFIG_WITH_CREDENTIAL) == "<your-organisation>/S008"


def test_only_origin_is_read():
    """A learner may have added an upstream. Theirs is origin."""
    where = _lifted(REPO)["repository_from_config"]
    assert where(CONFIG_TWO_REMOTES) == "<your-organisation>/S008"


def test_a_directory_that_is_not_a_clone_gives_nothing():
    where = _lifted(REPO)["repository_from_config"]
    assert where("") is None
    assert where("[core]\n\tbare = false\n") is None


def _runs(*ids):
    return [{"id": i, "head_sha": "%07dabc" % i} for i in ids]


def _holds(*artifact_ids):
    """A firmware_of that finds this exercise in the named artifacts only.

    Standing in for downloading a zip and looking inside it. An artifact
    NOT named here is one from a run where this exercise did not compile:
    it exists, and it holds builds of the other exercises and none of
    this one.
    """
    wanted = set(artifact_ids)
    return lambda artifact: (b"\x7fELF" if artifact["id"] in wanted else None)


def test_the_newest_run_holding_a_build_is_chosen():
    newest = _lifted(NEWEST)["newest_build_of"]
    artifacts = {1: [{"id": 11, "expired": False}],
                 2: [{"id": 22, "expired": False}]}
    run, artifact, image, why = newest(
        "01", _runs(2, 1), lambda r: artifacts[r["id"]], _holds(11, 22))
    assert (run["id"], artifact["id"]) == (2, 22)
    assert image == b"\x7fELF"
    assert why is None


def test_a_run_with_no_build_is_passed_over():
    """Nothing compiled, so upload-artifact wrote nothing. An ordinary
    outcome, not an error."""
    newest = _lifted(NEWEST)["newest_build_of"]
    artifacts = {3: [], 2: [], 1: [{"id": 11, "expired": False}]}
    run, artifact, _, why = newest(
        "01", _runs(3, 2, 1), lambda r: artifacts[r["id"]], _holds(11))
    assert (run["id"], artifact["id"]) == (1, 11)
    assert why is None


def test_an_expired_build_is_passed_over():
    """Seven days' retention, so a learner returning after a fortnight meets
    this in the ordinary way."""
    newest = _lifted(NEWEST)["newest_build_of"]
    artifacts = {2: [{"id": 22, "expired": True}],
                 1: [{"id": 11, "expired": False}]}
    run, artifact, _, why = newest(
        "01", _runs(2, 1), lambda r: artifacts[r["id"]], _holds(11, 22))
    assert (run["id"], artifact["id"]) == (1, 11)
    assert why is None


def test_an_expired_build_is_not_downloaded_to_find_that_out():
    """Expiry is visible in the listing, so passing one over must not cost
    a round trip. The learner is already waiting on the network."""
    newest = _lifted(NEWEST)["newest_build_of"]
    asked = []

    def firmware_of(artifact):
        asked.append(artifact["id"])
        return b"\x7fELF"

    artifacts = {2: [{"id": 22, "expired": True}],
                 1: [{"id": 11, "expired": False}]}
    newest("01", _runs(2, 1), lambda r: artifacts[r["id"]], firmware_of)
    assert asked == [11]


def test_a_run_whose_build_lacks_this_exercise_is_passed_over():
    """The defect this function was rewritten for, found 2026-11-12 on a
    learner's repository.

    Run 2 broke THIS exercise and compiled the others, so it HAS an
    artifact and that artifact has no build of this one. Run 1 built
    everything. Before the rewrite the search stopped at run 2 and the
    learner was refused while their build sat unexpired in run 1 -- and
    somebody whose exercise has just stopped compiling is precisely who
    presses this control.
    """
    newest = _lifted(NEWEST)["newest_build_of"]
    artifacts = {2: [{"id": 22, "expired": False}],
                 1: [{"id": 11, "expired": False}]}
    run, artifact, image, why = newest(
        "01", _runs(2, 1), lambda r: artifacts[r["id"]], _holds(11))
    assert (run["id"], artifact["id"]) == (1, 11)
    assert image == b"\x7fELF"
    assert why is None


def test_the_search_stops_at_the_first_build_it_finds():
    """The ordinary case costs one download, as it did before the rewrite.
    Pressing this on working code must not pay for a walk back through
    every run in the window."""
    newest = _lifted(NEWEST)["newest_build_of"]
    asked = []

    def firmware_of(artifact):
        asked.append(artifact["id"])
        return b"\x7fELF"

    artifacts = {3: [{"id": 33, "expired": False}],
                 2: [{"id": 22, "expired": False}],
                 1: [{"id": 11, "expired": False}]}
    newest("01", _runs(3, 2, 1), lambda r: artifacts[r["id"]], firmware_of)
    assert asked == [33]


def test_nothing_anywhere_is_reported_rather_than_guessed():
    newest = _lifted(NEWEST)["newest_build_of"]
    assert newest("01", _runs(2, 1),
                  lambda r: [{"id": 9, "expired": True}],
                  _holds()) == (None, None, None, "REFUSED_NO_RUN")


def test_no_kept_run_holds_this_exercise_at_all():
    """Every kept artifact belongs to a run where this exercise failed.
    To a learner that is the same as having none: there is no build of
    their exercise to fetch, and `build.norun` says the useful part --
    builds last seven days, push again to make a fresh one.
    """
    newest = _lifted(NEWEST)["newest_build_of"]
    artifacts = {2: [{"id": 22, "expired": False}],
                 1: [{"id": 11, "expired": False}]}
    assert newest("01", _runs(2, 1), lambda r: artifacts[r["id"]],
                  _holds()) == (None, None, None, "REFUSED_NEVER_BUILT")


def test_no_runs_at_all():
    """A learner who has not pushed yet."""
    newest = _lifted(NEWEST)["newest_build_of"]
    assert newest("01", [], lambda r: [], _holds()) == (None, None, None, "REFUSED_NO_PUSH")


def test_the_reason_tells_a_cleared_build_from_one_that_never_existed():
    """Until 2026-11-12 all three ways of having no build shared one
    message -- "push again to make a fresh one" -- which is right for an
    expired build, useless to somebody whose code has never compiled, and
    odd for somebody who has never pushed.

    Each reason is read off the listing the search already walked, so
    telling them apart costs no extra request.
    """
    newest = _lifted(NEWEST)["newest_build_of"]

    # Pushed, built once, and the build has since been cleared.
    cleared = newest("01", _runs(1),
                     lambda r: [{"id": 11, "expired": True}], _holds())
    assert cleared[3] == "REFUSED_NO_RUN"

    # Pushed, and no run ever produced a build of anything.
    never = newest("01", _runs(2, 1), lambda r: [], _holds())
    assert never[3] == "REFUSED_NEVER_BUILT"

    # Pushed, other exercises build, this one has never compiled.
    others = newest("01", _runs(1),
                    lambda r: [{"id": 11, "expired": False}], _holds())
    assert others[3] == "REFUSED_NEVER_BUILT"

    # Never pushed.
    assert newest("01", [], lambda r: [], _holds())[3] == "REFUSED_NO_PUSH"


def test_every_reason_the_search_gives_is_a_token_the_page_can_say():
    """A refusal the page has no words for renders as whatever
    BUILD_SAYS falls back to, which is a different refusal. Both halves
    are checked: the plugin must declare the token, and the page must
    have a label for it in both languages.
    """
    import re
    source = SOURCE
    page = io.open(
        os.path.join(os.path.dirname(HERE), "vis", "index.html"),
        encoding="utf-8").read()

    for token in ("REFUSED_NO_PUSH", "REFUSED_NEVER_BUILT", "REFUSED_NO_RUN"):
        assert '"%s"' % token in source, token
        found = re.search(r'\b%s:\s*\["([a-z.]+)"' % token, page)
        assert found, "%s has no entry in BUILD_SAYS" % token
        assert page.count('"%s":' % found.group(1)) == 2, (
            "%s -> %s is not in both languages"
            % (token, found.group(1)))


# --- the fetch retry --------------------------------------------------------

def _retrying(answers):
    """The retry wrapper, over a stub that returns or raises in turn.

    `answers` is a list; a string is returned, an Exception is raised.
    """
    calls = []
    lifted = _lifted(RETRY)

    def once(repository, artifact_id, secret):
        calls.append(artifact_id)
        answer = answers[len(calls) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    lifted["_artifact_bytes_once"] = once
    return lifted["_artifact_bytes"], calls


def test_a_fetch_that_works_first_time_is_not_repeated():
    """The ordinary path must cost one request. The walk above may
    already download several artifacts, so a wrapper that always tried
    twice would double a cost that is paid per run."""
    fetch, calls = _retrying(["zip bytes"])
    assert fetch("Org/S008", 7, "secret") == "zip bytes"
    assert calls == [7]


def test_a_failed_fetch_is_tried_once_more():
    """Measured 2026-11-12: a read failed with a .NET
    `Index was outside the bounds of the array.` and the same press
    succeeded immediately afterwards. One retry turns that refusal into
    a pause nobody notices."""
    fetch, calls = _retrying(
        [RuntimeError("Index was outside the bounds of the array."),
         "zip bytes"])
    assert fetch("Org/S008", 7, "secret") == "zip bytes"
    assert calls == [7, 7]


def test_it_gives_up_rather_than_trying_for_ever():
    """A deterministic failure fails twice and is then reported. The
    learner gets the refusal they would have got before, a moment
    later -- not a board that hangs."""
    boom = RuntimeError("no")
    fetch, calls = _retrying([boom, boom, "never reached"])
    with pytest.raises(RuntimeError):
        fetch("Org/S008", 7, "secret")
    assert calls == [7, 7]


def test_the_error_reported_is_the_last_one_not_the_first():
    """Whatever is shown should describe the attempt that actually
    ended the fetch."""
    fetch, _ = _retrying([RuntimeError("first"), RuntimeError("second")])
    with pytest.raises(RuntimeError) as raised:
        fetch("Org/S008", 7, "secret")
    assert "second" in str(raised.value)


# --- the destination rule ---------------------------------------------------

def test_the_fetch_takes_a_name_and_the_host_is_not_in_it():
    """ADR-0044's first condition, asserted on the source.

    The API host and the token's location are literals in the plugin. Nothing
    reads them from a request, and there is no code path that could: a request
    carries an exercise name, which is checked against the exercises on disk
    before anything else happens.

    Asserted here rather than left to review because it is the condition the
    whole credential decision rests on, and a future edit that took a host
    from a message would look perfectly ordinary.
    """
    dispatch = SOURCE[SOURCE.index("def message_received("):]
    dispatch = dispatch[:dispatch.index("def new_client(")]
    assert 'fetch_ci_build(parts[1], client)' in dispatch, (
        "the fetch verb no longer passes exactly one field")
    for leak in ("parts[2]", "parts[3]"):
        assert leak not in dispatch.split("elif verb == \"fetch\"")[1][:200], (
            "the fetch verb reads more than a name from the page")

    fetch = SOURCE[SOURCE.index("def fetch_ci_build("):]
    fetch = fetch[:fetch.index("def load_uploaded(")]
    assert "API +" in SOURCE, "the API host is no longer a literal"
    for forbidden in ("http://", "request.get_host", "urlparse"):
        assert forbidden not in fetch, (
            "fetch_ci_build looks like it builds a destination: %r" % forbidden)


def test_the_credential_is_never_put_into_a_message():
    """ADR-0044's second condition, asserted on the source.

    The credential is read where it is used and goes to one host. Nothing
    sends it anywhere and no endpoint returns it -- but a future edit that
    logged it "while debugging", or put it into a refusal to explain what went
    wrong, would look perfectly ordinary in review.

    So no line that sends something to a page, or prints, may mention it. It
    is called `secret` rather than `token` precisely so this can be checked:
    `token` in that file means an outcome -- BUILT, LOADED, REFUSED_... -- and
    a name shared between a vocabulary and a credential is a name that ends up
    getting one of them printed. Writing this test is what found that.
    """
    sending = ("send_message(", "send_to(", "say_build(", "print(")
    for number, line in enumerate(SOURCE.splitlines(), 1):
        if not any(call in line for call in sending):
            continue
        assert not re.search(r"secret", line), (
            "vis_f401re.py:%d sends or prints something mentioning the "
            "credential, which is how one escapes: %s" % (number, line.strip()))

    opened = [l for l in SOURCE.splitlines()
              if "SECRET_FILE" in l and "open(" in l]
    assert len(opened) == 1, (
        "the credential file is opened in more than one place, so there is "
        "more than one thing to review: %s" % opened)
