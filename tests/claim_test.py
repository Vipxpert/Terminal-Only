# /llm_harness/tests/claim_test.py
"""Claim-before-change test for llm_harness: a chat changes only files inside its own write scope; a claim in the same script runs first, a user grant also counts, and runs without a session are not limited."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-claim-")
RESULTS = []
STEP = [0]


def run(session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0]] + (["@SESSION " + session] if session else []) + ["@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def edit(path, old, new):
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
            f.write("original line of %s\n" % rel)
    out = run("alpha | edit a", *edit("/a.txt", "original line of a.txt", "changed line of a.txt"))
    check("a change outside this chat's scope is refused", "outside this session's write scope" in out and "changed" not in read("a.txt"), out)
    out = run("alpha | edit a", "@SCOPE edit a | a.txt", *edit("/a.txt", "original line of a.txt", "changed line of a.txt"))
    check("a claim in the same script lets the change through", "[OK] /a.txt" in out and "changed" in read("a.txt"), out)
    out = run("alpha | edit a", *edit("/b.txt", "original line of b.txt", "changed line of b.txt"))
    check("a file outside the claimed ones is still refused", "outside this session's write scope" in out and "changed" not in read("b.txt"), out)
    g = subprocess.run([sys.executable, HARNESS, "--workspace", WS, "--grant", "alpha", "b.txt"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = run("alpha | edit a", *edit("/b.txt", "original line of b.txt", "changed line of b.txt"))
    check("a user grant counts as covered", "GRANTED" in g.stdout.decode() and "changed" in read("b.txt"), out)
    out = run(None, *edit("/c.txt", "original line of c.txt", "changed line of c.txt"))
    check("a run without a session is not limited", "changed" in read("c.txt"), out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
