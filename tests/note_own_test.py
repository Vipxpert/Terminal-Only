# /llm_harness/tests/note_own_test.py
"""Own-note test for llm_harness: @NOTE_ADD own | <text> pins a to-do to the running chat and marks it as that chat's own; footers print it as the chat's own, never the user's, while pinned and plain notes stay the user's; @NOTE_LIST and notes.md show [own: <session>]; other chats do not see it; a plain edit keeps the mark; without a session it is refused."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: own %d]" % COUNT[0], "@WORKSPACE " + ws] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def main():
    ws = tempfile.mkdtemp(prefix="harness-ownnote-")
    subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--compact", "off"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    run(ws, "@SESSION alpha | alpha work", "@NOTE_ADD own | Todo: finish the alpha part", "@NOTE_ADD Todo: a note for every chat", "@NOTE_ADD pin alpha | Todo: the owner's pinned plan")
    out = run(ws, "@SESSION alpha | alpha work", "@NOTE_LIST")
    check("the own note prints as this chat's own; the pinned and the plain note stay the user's",
          "(this chat's own to-do, written by the AI, not the user's): Todo: finish the alpha part" in out
          and "(the user's, pinned to this chat): Todo: the owner's pinned plan" in out
          and "(the user's): Todo: a note for every chat" in out, out)
    with open(os.path.join(ws, ".llm_harness", "notes.md"), "r", encoding="utf-8") as f:
        stored = f.read()
    check("@NOTE_LIST and notes.md show [own: alpha]", "[own: alpha] Todo: finish the alpha part" in out and "[own: alpha] Todo: finish the alpha part" in stored and "[pin: alpha] Todo: the owner's pinned plan" in stored, (out, stored))
    other = run(ws, "@SESSION beta | beta work", "@LIST_DIR /")
    check("another chat does not see it", "finish the alpha part" not in other and "a note for every chat" in other, other)
    edited = run(ws, "@SESSION alpha | alpha work", "@NOTE_EDIT N001 Todo: alpha part half done")
    check("a plain edit keeps the own mark", "(this chat's own to-do, written by the AI, not the user's): Todo: alpha part half done" in edited, edited)
    lone = run(ws, "@NOTE_ADD own | Todo: nobody's")
    with open(os.path.join(ws, ".llm_harness", "notes.md"), "r", encoding="utf-8") as f:
        stored = f.read()
    check("without a session it is refused and nothing is stored", "[NOTE ERROR]" in lone and "nobody's" not in stored, (lone, stored))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
