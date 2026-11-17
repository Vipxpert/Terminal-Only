# /llm_harness/tests/comments_test.py
"""Removed-comment test for llm_harness: a change that deletes a 'Comment' line (a recorded reason) is flagged so the reason gets a second look; ordinary comments and kept Comment lines are not."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-comments-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def hunk(path, old, new):
    return ["@FILE " + path, "@HUNK TOP | e", "--- [OLD CODE] ---"] + old + ["+++ [NEW CODE] +++"] + new + ["=== [END HUNK] ==="]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    with open(os.path.join(WS, "w.py"), "w") as f:
        f.write("# /w/w.py\ndef work(lock):\n    # Comment (order): release the lock before awaiting the task\n    lock.release()\n    # plain note about the loop\n    x = 1\n    return x\n")
    with open(os.path.join(WS, "s.go"), "w") as f:
        f.write("package s\n\n// Comment (constraint): the device accepts at most 3 retries\nconst retries = 3\n")
    out = run(*hunk("/w.py", ["    x = 1"], ["    x = 2"]))
    check("a change that keeps the Comment line is not flagged", "[COMMENT REMOVED]" not in out and "[OK] /w.py" in out, out)
    out = run(*hunk("/w.py", ["    # plain note about the loop", "    x = 2"], ["    x = 3"]))
    check("removing an ordinary comment is not flagged", "[COMMENT REMOVED]" not in out, out)
    out = run(*hunk("/w.py", ["    # Comment (order): release the lock before awaiting the task", "    lock.release()"], ["    lock.release()"]))
    check("removing a Comment line is flagged with its text", "[COMMENT REMOVED] /w.py: # Comment (order): release the lock before awaiting the task" in out and "[OK] /w.py" in out, out)
    out = run(*hunk("/s.go", ["// Comment (constraint): the device accepts at most 3 retries"], ["// Comment (constraint): the device accepts at most 5 retries"]))
    check("rewording a Comment line flags the old wording too, also with // comments", "[COMMENT REMOVED] /s.go: // Comment (constraint): the device accepts at most 3 retries" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
