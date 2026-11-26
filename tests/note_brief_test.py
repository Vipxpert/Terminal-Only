# /llm_harness/tests/note_brief_test.py
"""Note-brief test for llm_harness: @NOTE_BRIEF <id> | <short> puts a short part before a note's existing text, so the footer prints only the short part with a pointer and @NOTE_LIST <id> prints it all; the note's pin stays."""
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
    text = "\n".join(["@SCRIPT [C: brief %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-brief-")
    subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--compact", "off"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    run(ws, "alpha", "@NOTE_ADD Env: LONG-DETAIL stays whole")
    out = run(ws, "alpha", "@NOTE_BRIEF N001 | SHORT-PART", "@LIST_DIR /")
    check("the footer prints only the short part, with a pointer", "SHORT-PART (more: @NOTE_LIST N001)" in out and "LONG-DETAIL" not in out.split("=== NOTE N001")[-1], out)
    full = run(ws, "alpha", "@NOTE_LIST N001")
    check("@NOTE_LIST <id> prints the short part and the full text", "SHORT-PART || Env: LONG-DETAIL stays whole" in full, full)
    run(ws, "alpha", "@NOTE_PIN N001 alpha")
    run(ws, "alpha", "@NOTE_BRIEF N001 | NEWER-SHORT")
    mine, later = run(ws, "alpha", "@LIST_DIR /"), run(ws, "beta", "@LIST_DIR /")
    check("a new short part replaces the old one, the text stays and the pin stays", "NEWER-SHORT (more:" in mine and "SHORT-PART" not in mine and "NEWER-SHORT" not in later, (mine, later))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
