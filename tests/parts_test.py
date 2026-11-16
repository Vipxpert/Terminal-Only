# /llm_harness/tests/parts_test.py
"""Part test for llm_harness: scripts marked @PART i/n print the standing rules only in the last part, so two scripts in one reply do not repeat the footer."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-parts-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [P: step %d]" % STEP[0], "@SESSION alpha | try parts", "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("some searchable text\n")
    out = run("@PART 1/2", "@GREP searchable")
    check("part 1 of 2 shows its results and the next number, but no standing rules", "/a.txt:" in out and "=== NEXT SCRIPT NUMBER" in out and "PART 1 of 2" in out and "[L1-Harness]" not in out and "=== GOAL" not in out, out)
    out = run("@PART 2/2", "@GREP searchable")
    check("the last part prints the goal and the standing rules", "=== GOAL" in out and "[L1-Harness]" in out and "PART 2 of 2" not in out, out)
    out = run("@GREP searchable")
    check("a script without @PART prints everything as before", "[L1-Harness]" in out, out)
    out = run("@PART two", "@GREP searchable")
    check("a malformed @PART is reported and the footer stays complete", "expected '@PART <i>/<n>'" in out and "[L1-Harness]" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
