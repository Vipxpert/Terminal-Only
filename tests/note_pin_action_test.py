# /llm_harness/tests/note_pin_action_test.py
"""Pin-action test for llm_harness: @NOTE_PIN changes only a note's audience (* for every chat with a session, new ones too; names; all for a plain note that also reaches runs without a session; own for the chat's own to-do), and a note's text before ' || ' is all a footer prints, with @NOTE_LIST <id> printing it whole."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, session, *lines):
    COUNT[0] += 1
    head = ["@SCRIPT [C: pinact %d]" % COUNT[0], "@WORKSPACE " + ws]
    if session:
        head.append("@SESSION %s | %s work" % (session, session))
    p = subprocess.run([sys.executable, HARNESS], input=("\n".join(head + list(lines)) + "\n").encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-pinact-")
    subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--compact", "off"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    run(ws, "alpha", "@NOTE_ADD pin alpha | Todo: PIN-NOTE")
    run(ws, "alpha", "@NOTE_PIN N001 *")
    out = run(ws, "beta", "@LIST_DIR /")
    check("@NOTE_PIN * reaches a chat that appeared later", "PIN-NOTE" in out, out)
    run(ws, "alpha", "@NOTE_PIN N001 alpha")
    mine, later = run(ws, "alpha", "@LIST_DIR /"), run(ws, "gamma", "@LIST_DIR /")
    check("a named pin hides the note from a later chat and keeps its text", "PIN-NOTE" in mine and "PIN-NOTE" not in later, (mine, later))
    run(ws, "alpha", "@NOTE_PIN N001 all")
    out = run(ws, None, "@LIST_DIR /")
    check("all makes it a plain note that also reaches a run without a session", "(the user's): Todo: PIN-NOTE" in out, out)
    out = run(ws, "alpha", "@NOTE_PIN N001 own", "@LIST_DIR /")
    check("own makes the footer call it this chat's own to-do", "this chat's own to-do" in out and "PIN-NOTE" in out, out)
    run(ws, "alpha", "@NOTE_ADD Env: SHORT-PART || LONG-DETAIL")
    foot = run(ws, "alpha", "@LIST_DIR /")
    full = run(ws, "alpha", "@NOTE_LIST N002")
    check("a brief note prints only its first part in the footer, and @NOTE_LIST <id> prints the rest", "SHORT-PART (more: @NOTE_LIST N002)" in foot and "LONG-DETAIL" not in foot and "LONG-DETAIL" in full, (foot, full))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
