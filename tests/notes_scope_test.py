# /llm_harness/tests/notes_scope_test.py
"""Scoped-notes test for llm_harness: a note can be aimed at particular chats or a name pattern; only those chats see it in their footers, listings show every note with its audience, and edits keep the audience unless a new one is given."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-notes-")
subprocess.run([sys.executable, HARNESS, "--workspace", WS, "--compact", "off"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
RESULTS = []
STEP = [0]


def run(session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [N: step %d]" % STEP[0]] + (["@SESSION " + session] if session else []) + ["@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def footer(out):
    return out.split("=== NEXT SCRIPT NUMBER")[-1].split("=== L1 CONTRACT")[0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    run("alpha | a", "@NOTE_ADD Every chat follows the monorepo layout")
    run("alpha | a", "@NOTE_ADD pin alpha | The test browser is at port 9222")
    run("alpha | a", "@NOTE_ADD for migration-* | Keep the Go module boundary")
    out = footer(run("alpha | a", "@GREP nothing here"))
    check("a project-wide note reaches every chat", "monorepo layout" in out, out)
    check("a note for this chat shows, marked as such", "pinned to this chat): The test browser is at port 9222" in out, out)
    check("a note for other chats does not show", "Go module boundary" not in out, out)
    out = footer(run("migration-go | m", "@GREP nothing here"))
    check("a name pattern reaches matching chats", "Go module boundary" in out and "port 9222" not in out and "monorepo layout" in out, out)
    out = footer(run(None, "@GREP nothing here"))
    check("without a session only project-wide notes show", "monorepo layout" in out and "port 9222" not in out and "Go module boundary" not in out, out)
    out = run("beta | b", "@NOTE_LIST")
    check("the note list shows every note with its audience", "[pin: alpha] The test browser" in out and "[pin: migration-*] Keep the Go module boundary" in out, out)
    run("beta | b", "@NOTE_EDIT N002 The test browser is at port 9333")
    out = run("beta | b", "@NOTE_LIST")
    check("an edit keeps the audience", "[pin: alpha] The test browser is at port 9333" in out, out)
    run("beta | b", "@NOTE_EDIT N002 for beta | The test browser is at port 9444")
    out = footer(run("beta | b", "@GREP nothing here"))
    check("an edit can give a new audience", "pinned to this chat): The test browser is at port 9444" in out, out)
    text = open(os.path.join(WS, ".llm_harness", "notes.md"), encoding="utf-8").read()
    check("the notes file stays plain and readable", "- [N002] [pin: beta] The test browser is at port 9444" in text and "- [N001] Every chat follows the monorepo layout" in text, text)
    run("beta | b", "@NOTE_ADD Bug: video playback freezes at a random frame")
    listing = lambda out: out.split("=== WORKSPACE NOTES")[-1].split("\n===")[0]
    out = run("beta | b", "@NOTE_LIST bug")
    check("@NOTE_LIST finds notes by category", "Bug: video playback freezes" in listing(out) and "monorepo layout" not in listing(out), out)
    out = run("beta | b", "@NOTE_LIST test browser")
    check("@NOTE_LIST finds notes by content words", "port 9444" in listing(out) and "Bug: video" not in listing(out), out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
