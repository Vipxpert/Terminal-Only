# /llm_harness/tests/note_pin_switch_test.py
"""Pin-switch test for llm_harness: a note pinned with * reaches a chat that appears later; @NOTE_EDIT can narrow it to named chats (a later chat no longer sees it) and widen it back to * (a later chat sees it again); a plain edit keeps the pin."""
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
    text = "\n".join(["@SCRIPT [C: pinswitch %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-pinswitch-")
    subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--compact", "off"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    run(ws, "alpha", "@NOTE_ADD pin * | Todo: WIDE-NOTE")
    out = run(ws, "beta", "@LIST_DIR /")
    check("a note pinned with * reaches a chat that appeared later", "WIDE-NOTE" in out, out)
    run(ws, "alpha", "@NOTE_EDIT N001 pin alpha | Todo: WIDE-NOTE")
    mine = run(ws, "alpha", "@LIST_DIR /")
    later = run(ws, "gamma", "@LIST_DIR /")
    check("narrowed to alpha, alpha still sees it and a chat that appears later does not", "WIDE-NOTE" in mine and "WIDE-NOTE" not in later, (mine, later))
    run(ws, "alpha", "@NOTE_EDIT N001 pin * | Todo: WIDE-NOTE")
    out = run(ws, "delta", "@LIST_DIR /")
    check("widened back to *, a chat that appears after that sees it again", "WIDE-NOTE" in out, out)
    run(ws, "alpha", "@NOTE_EDIT N001 Todo: WIDE-NOTE two")
    out = run(ws, "epsilon", "@LIST_DIR /")
    check("a plain edit keeps the * pin", "WIDE-NOTE two" in out, out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
