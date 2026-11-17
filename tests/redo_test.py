# /llm_harness/tests/redo_test.py
"""@REDO test for llm_harness: an earlier script's saved text runs again under a new number, with corrections and extra directives, instead of being resent whole."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-redo-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def read(rel):
    with open(os.path.join(WS, rel), encoding="utf-8") as f:
        return f.read()


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("first line\nsecond line\n")
    out = run("@FILE /a.txt", "@HUNK TOP | fix both", "--- [OLD CODE] ---", "frist line", "second line", "+++ [NEW CODE] +++", "line one", "line two", "=== [END HUNK] ===")
    check("the original script fails on a typo", "[MISMATCH]" in out and "first line" in read("a.txt"), out)
    out = run("@REDO 1", "--- [OLD TEXT] ---", "frist line", "+++ [NEW TEXT] +++", "first line", "=== [END TEXT] ===", "@GREP line")
    check("@REDO runs the saved script with the correction", "[REDO]" in out and "[OK] /a.txt" in out and "line one\nline two\n" in read("a.txt"), out)
    check("extra directives after the @REDO block run too", "=== GREP: line" in out, out)
    out = run("@REDO 99")
    check("@REDO of an unknown script is refused", "no saved text for script 99" in out and "Nothing was run" in out, out)
    out = run("@REDO 1", "--- [OLD TEXT] ---", "text that is nowhere", "+++ [NEW TEXT] +++", "x", "=== [END TEXT] ===")
    check("a correction that does not match is refused", "found 0 times" in out and "Nothing was run" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
