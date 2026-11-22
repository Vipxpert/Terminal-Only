# /llm_harness/tests/early_exit_session_test.py
"""Early-exit test for llm_harness: a refusal that ends the run before anything executes (a @REPEATABLE script that carries a number, a @REDO of a script that was never saved) still prints the chat's own session line in its footer, like a normal run."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, script_line, *lines):
    text = "\n".join([script_line, "@WORKSPACE " + ws] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def main():
    ws = tempfile.mkdtemp(prefix="harness-earlyexit-")
    first = run(ws, "@SCRIPT [C: first]", "@SESSION alpha | alpha work", "@LIST_DIR /")
    check("control: a normal run names the session", "=== THIS SESSION: alpha" in first, first)
    rep = run(ws, "@SCRIPT [C-7: repeat]", "@REPEATABLE", "@SESSION alpha | alpha work", "@LIST_DIR /")
    check("a @REPEATABLE script that carries a number is refused, and its footer names the session", "[REFUSED] a @REPEATABLE" in rep and "=== THIS SESSION: alpha" in rep, rep)
    redo = run(ws, "@SCRIPT [C: redo]", "@SESSION alpha | alpha work", "@REDO 999")
    check("a @REDO of a script that was never saved is refused, and its footer names the session", "[REFUSED]" in redo and "=== THIS SESSION: alpha" in redo, redo)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
