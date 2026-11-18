# /llm_harness/tests/loop_check_test.py
"""Loop-check test for llm_harness: after three footer-only scripts in a row a chat's footer says LOOP CHECK (the standing rule then tells the AI to drop the manifest and ask the user whether they are still there); any script that does something resets it."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-loop-")
RESULTS = []
STEP = [0]


def run(session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [P: step %d]" % STEP[0], "@SESSION %s | try loops" % session, "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("something\n")
    out1, out2 = run("alpha"), run("alpha")
    check("one or two footer-only scripts give no loop check", "=== LOOP CHECK:" not in out1 and "=== LOOP CHECK:" not in out2, out2)
    out3 = run("alpha")
    check("the third footer-only script in a row says LOOP CHECK", "=== LOOP CHECK: this chat's last 3 scripts did nothing" in out3, out3)
    check("the standing rule tells the AI what to do then", "while the footer shows LOOP CHECK" in out3, out3)
    out = run("beta")
    check("another chat is not affected", "=== LOOP CHECK:" not in out, out)
    out = run("alpha", "@GREP something")
    check("a script that reads something resets the count", "=== LOOP CHECK:" not in out, out)
    run("alpha")
    out = run("alpha")
    check("it takes three in a row again", "=== LOOP CHECK:" not in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
