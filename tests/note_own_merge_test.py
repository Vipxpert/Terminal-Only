# /llm_harness/tests/note_own_merge_test.py
"""Own-note merge test for llm_harness: the three-way merge of notes.md keeps a chat's own note ([own: <session>]) as an own note, beside a note the other machine added under the same number."""
import importlib.util, os, sys

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    base = "<!-- llm_harness_notes_next_id: 2 -->\n- [N001] Env: shared\n"
    ours = "<!-- llm_harness_notes_next_id: 3 -->\n- [N001] Env: shared\n- [N002] [own: alpha] Todo: mine\n"
    theirs = "<!-- llm_harness_notes_next_id: 3 -->\n- [N001] Env: shared\n- [N002] Todo: theirs\n"
    out = hh.merge_notes_text(base, ours, theirs)
    check("the merged file keeps the own tag and the other machine's note", "[own: alpha] Todo: mine" in out and "Todo: theirs" in out and "Env: shared" in out, out)
    notes, _ = hh.parse_notes_text(out)
    mine = [n for n in notes if n["text"] == "Todo: mine"]
    check("the merge parser reads it as an own note pinned to its chat", len(mine) == 1 and mine[0].get("own") is True and mine[0]["for"] == ["alpha"], notes)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
