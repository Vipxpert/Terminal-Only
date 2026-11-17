# /llm_harness/tests/undo_file_test.py
"""File-level undo test for llm_harness: '@UNDO <script> | /path' restores only that file from that script (with this chat's later changes to it), leaves the script's other files alone, and respects other chats."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-undofile-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def hunk(path, old, new):
    return ["@FILE " + path, "@HUNK TOP | e", "--- [OLD CODE] ---", old, "+++ [NEW CODE] +++", new, "=== [END HUNK] ==="]


def read(rel):
    with open(os.path.join(WS, rel), encoding="utf-8") as f:
        return f.read()


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    for rel in ("a.txt", "b.txt", "c.txt"):
        with open(os.path.join(WS, rel), "w") as f:
            f.write("first %s line\n" % rel)
    run(*(hunk("/a.txt", "first a.txt line", "second a.txt line") + hunk("/b.txt", "first b.txt line", "second b.txt line")))
    run(*hunk("/c.txt", "first c.txt line", "second c.txt line"))
    run(*hunk("/a.txt", "second a.txt line", "third a.txt line"))
    out = run("@UNDO 1 | /b.txt")
    check("undoing one file of a script restores only that file", "[RESTORED] /b.txt" in out and "first b.txt" in read("b.txt") and "third a.txt" in read("a.txt"), out)
    out = run("@UNDO 3..1 | /a.txt")
    check("a range limited to one file walks back only that file's changes", "first a.txt" in read("a.txt") and "second c.txt" in read("c.txt"), out)
    out = run("@UNDO 2 | /a.txt")
    check("a script that never touched the file is passed over and says so", "that changed /a.txt" in out and "second c.txt" in read("c.txt"), out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
