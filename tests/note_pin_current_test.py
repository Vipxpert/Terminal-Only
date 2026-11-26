# /llm_harness/tests/note_pin_current_test.py
"""Pin-current test for llm_harness: @NOTE_PIN <id> current pins a note to the chats that exist now and not to chats that appear later; @NOTE_PIN <id> * brings later chats in again, and current takes them out again, never touching the note's text."""
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
    text = "\n".join(["@SCRIPT [C: pincur %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-pincur-")
    subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--compact", "off"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    run(ws, "alpha", "@LIST_DIR /")
    run(ws, "beta", "@LIST_DIR /")
    run(ws, "alpha", "@NOTE_ADD Todo: CUR-NOTE")
    out = run(ws, "alpha", "@NOTE_PIN N001 current")
    check("current is accepted and names the chats that exist now", "[NOTE PINNED] N001" in out and "alpha" in out and "beta" in out, out)
    seen = run(ws, "beta", "@LIST_DIR /")
    check("a chat that exists now sees the note", "CUR-NOTE" in seen, seen)
    later = run(ws, "gamma", "@LIST_DIR /")
    check("a chat that appears later does not", "CUR-NOTE" not in later, later)
    run(ws, "alpha", "@NOTE_PIN N001 *")
    wide = run(ws, "delta", "@LIST_DIR /")
    run(ws, "alpha", "@NOTE_PIN N001 current")
    after = run(ws, "epsilon", "@LIST_DIR /")
    check("* lets the next new chat see it, and current stops the one after that", "CUR-NOTE" in wide and "CUR-NOTE" not in after, (wide, after))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
