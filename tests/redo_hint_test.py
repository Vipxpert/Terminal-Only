# /llm_harness/tests/redo_hint_test.py
"""REDO-hint test for llm_harness: when a script's changes are refused (outside the session's write scope) or a marker is missing, the recovery hint names @REDO with corrections, so a large script is not resent whole."""
import importlib.util, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def main():
    ws = tempfile.mkdtemp(prefix="harness-redohint-")
    text = "\n".join(["@SCRIPT [C: redo hint]", "@WORKSPACE " + ws, "@SESSION alpha | alpha work", "@SCOPE alpha work | a.py", "@NEW_FILE /b.py", "x = 1", "@END_NEW_FILE"]) + "\n"
    out = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120).stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0]
    check("a change outside the write scope is refused with a hint that names @REDO", "outside this session's write scope" in out and "@REDO" in out, out)
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    check("the MALFORMED and REFUSED hints name @REDO", "@REDO" in hh.NEXT_STEPS["MALFORMED"] and "@REDO" in hh.NEXT_STEPS["REFUSED"], hh.NEXT_STEPS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
