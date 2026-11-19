# /llm_harness/tests/deadlock_test.py
"""Deadlock test for llm_harness: when chats wait on each other's files in a circle (two chats, or three), each member's footer says DEADLOCK and names who waits on whom; a plain wait, or a circle whose holder has let go, does not."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-deadlock-")
RESULTS = []
STEP = [0]
MARK = "=== DEADLOCK ("


def run(session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@SESSION %s | try waiting" % session, "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def want(path):
    return ["@FILE /" + path, "@HUNK TOP | try", "--- [OLD CODE] ---", "one", "+++ [NEW CODE] +++", "two", "=== [END HUNK] ==="]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-900:].replace("\n", "\n    "))


def main():
    for n in ("a", "b", "c", "d", "x1", "x2", "x3"):
        with open(os.path.join(WS, n + ".txt"), "w") as f:
            f.write("one\n")
    run("alpha", "@SCOPE a | a.txt")
    run("beta", "@SCOPE b | b.txt")
    out = run("beta", *want("a.txt"))
    check("a single wait is not a deadlock", "WAITING ON" in out and MARK not in out, out)
    out = run("alpha", *want("b.txt"))
    check("the chat that closes the circle sees DEADLOCK naming both waits", MARK in out and "alpha waits on beta for /b.txt" in out and "beta waits on alpha for /a.txt" in out, out)
    out = run("beta")
    check("the other chat sees it in its footer too", MARK in out and "alpha waits on beta" in out, out)
    run("gamma", "@SCOPE c | c.txt")
    out = run("delta", *want("c.txt"))
    check("a plain wait on a chat that waits for nobody is no deadlock", "WAITING ON" in out and MARK not in out, out)
    run("ea", "@SCOPE x1 | x1.txt")
    run("eb", "@SCOPE x2 | x2.txt")
    run("ec", "@SCOPE x3 | x3.txt")
    run("ea", *want("x2.txt"))
    run("eb", *want("x3.txt"))
    out = run("ec", *want("x1.txt"))
    check("a circle of three chats is found", MARK in out and "ea waits on eb" in out and "eb waits on ec" in out and "ec waits on ea" in out, out)
    out = run("alpha", "@SCOPE_END")
    out = run("alpha")
    check("once a chat lets go, the circle is gone for it", "WAITING ON" in out and MARK not in out, out)
    out = run("beta")
    check("and for the other chat, which is told it is unblocked", "UNBLOCKED" in out and MARK not in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
