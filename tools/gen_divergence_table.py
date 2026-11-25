"""Generate the readable divergence tables from divergences.json.

The register is the source. These documents are derived from it, so a
divergence cannot be recorded in the data and missing from the prose, or
corrected in one and left stale in the other. ADR-0002.

    python tools/gen_divergence_table.py           # write the documents
    python tools/gen_divergence_table.py --check    # fail if they are stale

The sweep runs --check, so a register edit that was not regenerated is caught
rather than discovered by a reader.
"""

import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTER = os.path.join(ROOT, "divergences.json")

ORDER = {"permanent": 0, "outstanding": 1, "fixed": 2}

TEXT = {
    "en": {
        "file": "DIVERGENCES.md",
        "partner": "DIVERGENCES.ja.md",
        "title": "What the simulator gets wrong",
        "intro": [
            "Every known way the simulated board differs from a real ST",
            "NUCLEO-F401RE.",
            "",
            "**This file is generated.** The source is",
            "[`divergences.json`](divergences.json); edit that and run",
            "`python tools/gen_divergence_table.py`. The verification sweep fails",
            "if the two disagree.",
        ],
        "traps_head": "Differences that let wrong code look right",
        "traps_intro": [
            "These are the dangerous ones. In each case the simulator is more",
            "permissive than the hardware, so a mistake produces working",
            "simulation and a failure on a real board — and the learner is told",
            "nothing at the point they make it. The exercise material must warn",
            "about each of these where it bites.",
        ],
        "rest_head": "The rest",
        "cols": ("What Renode does", "What the board does", "Status"),
        "warn_in": "Warned about in",
        "fixed_by": "Fixed by",
        "source": "Source",
        "partner_note": "> This document has a Japanese version: [`{0}`]({0}).",
        "counts": "{0} divergences: {1} permanent, {2} outstanding, {3} corrected.",
    },
    "ja": {
        "file": "DIVERGENCES.ja.md",
        "partner": "DIVERGENCES.md",
        "title": "シミュレータと実機の違い",
        "intro": [
            "シミュレーション上のボードが実機の ST NUCLEO-F401RE と異なる点の一覧です。",
            "",
            "**このファイルは自動生成されます。** 元データは",
            "[`divergences.json`](divergences.json) です。編集したら",
            "`python tools/gen_divergence_table.py` を実行してください。両者が食い違う",
            "場合、検証スイープが失敗します。",
        ],
        "traps_head": "誤ったコードが正しく見えてしまう違い",
        "traps_intro": [
            "これらは特に危険です。いずれもシミュレータのほうが実機より寛容なため、",
            "誤りがあってもシミュレーションでは動作し、実機では失敗します。しかも",
            "誤った時点では何も知らされません。該当する課題の教材では、これらを必ず",
            "注意喚起してください。",
        ],
        "rest_head": "その他",
        "cols": ("Renode の挙動", "実機の挙動", "状態"),
        "warn_in": "注意喚起する課題",
        "fixed_by": "対処",
        "source": "出典",
        "partner_note": "> この文書は [`{0}`]({0}) の日本語版です。",
        "counts": "全 {0} 件: 恒久的 {1} 件、未対応 {2} 件、対処済み {3} 件。",
    },
}

STATUS_WORD = {
    "en": {"permanent": "permanent", "outstanding": "outstanding", "fixed": "corrected"},
    "ja": {"permanent": "恒久的", "outstanding": "未対応", "fixed": "対処済み"},
}


def render(rows, lang):
    t = TEXT[lang]
    sw = STATUS_WORD[lang]
    renode_key = "renode" if lang == "en" else "renode_ja"
    board_key = "board" if lang == "en" else "board_ja"

    out = ["# " + t["title"], ""]
    out.extend(t["intro"])
    out.append("")
    out.append(t["partner_note"].format(t["partner"]))
    out.append("")

    counts = {"permanent": 0, "outstanding": 0, "fixed": 0}
    for row in rows:
        counts[row.get("status", "permanent")] += 1
    out.append(t["counts"].format(len(rows), counts["permanent"],
                                  counts["outstanding"], counts["fixed"]))
    out.append("")

    traps = [r for r in rows if r.get("hides_mistake")]
    rest = [r for r in rows if not r.get("hides_mistake")]

    def block(items, heading, intro=None):
        if not items:
            return
        out.append("## " + heading)
        out.append("")
        if intro:
            out.extend(intro)
            out.append("")
        for row in sorted(items, key=lambda r: (ORDER.get(r.get("status"), 9),
                                                r.get("id", ""))):
            out.append("### " + row.get("id", "?"))
            out.append("")
            out.append("**" + t["cols"][0] + "** " + row.get(renode_key, ""))
            out.append("")
            out.append("**" + t["cols"][1] + "** " + row.get(board_key, ""))
            out.append("")
            out.append("**" + t["cols"][2] + "** " +
                       sw.get(row.get("status"), row.get("status", "")))
            out.append("")
            if row.get("fixed_by"):
                out.append("**" + t["fixed_by"] + "** " + row["fixed_by"])
                out.append("")
            if row.get("warn_in"):
                out.append("**" + t["warn_in"] + "** " + ", ".join(row["warn_in"]))
                out.append("")
            out.append("**" + t["source"] + "** " + row.get("source", ""))
            out.append("")

    block(traps, t["traps_head"], t["traps_intro"])
    block(rest, t["rest_head"])

    return "\n".join(out).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="fail if a generated document is out of date")
    args = parser.parse_args()

    with io.open(REGISTER, encoding="utf-8") as handle:
        rows = json.load(handle)["divergences"]

    stale = []
    for lang in ("en", "ja"):
        path = os.path.join(ROOT, TEXT[lang]["file"])
        body = render(rows, lang)
        if args.check:
            try:
                with io.open(path, encoding="utf-8") as handle:
                    current = handle.read()
            except IOError:
                current = None
            if current != body:
                stale.append(TEXT[lang]["file"])
        else:
            with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(body)
            print("wrote " + TEXT[lang]["file"])

    if args.check:
        if stale:
            print("STALE: " + ", ".join(stale))
            print("Run: python tools/gen_divergence_table.py")
            return 1
        print("divergence tables are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
