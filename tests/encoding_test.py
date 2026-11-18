# /llm_harness/tests/encoding_test.py
"""Encoding test for llm_harness: a Python program run through @RUN prints non-Latin text (Vietnamese here) correctly, even when its standard streams would default to a legacy code page."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-encoding-")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    name = "python" if os.name == "nt" else "python3"
    script = "@SCRIPT [P: vietnamese]\n@WORKSPACE %s\n@RUN %s -c \"print('Ti\\u1ebfng Vi\\u1ec7t')\"\n" % (WS, name)
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    p = subprocess.run([sys.executable, HARNESS], input=script.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, env=env)
    out = p.stdout.decode("utf-8", "replace")
    check("a Python child prints Vietnamese through @RUN", "Ti\u1ebfng Vi\u1ec7t" in out, out)
    check("and does not fail with an encoding error", "UnicodeEncodeError" not in out and "[exit 0 |" in out, out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
