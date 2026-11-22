# /llm_harness/tests/setup_cmd_getver_test.py
"""setup.cmd version-reader test for llm_harness: the :getver subroutine, cut out of the real setup.cmd and run alone with cmd /c, reads the VERSION line of a harness.py, says none for a missing file and unknown for a file without a version line. Windows only."""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP = os.path.join(os.path.dirname(HERE), "setup.cmd")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def main():
    if os.name != "nt" or not os.path.isfile(SETUP):
        print("SKIP setup.cmd needs Windows cmd")
        sys.exit(0)
    with open(SETUP, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().replace("\r", "").split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip().lower() == ":getver"), None)
    check("setup.cmd has a :getver subroutine", start is not None, lines[-12:])
    if start is None:
        sys.exit(1)
    tmp = tempfile.mkdtemp(prefix="harness-getver-")
    wrapper = os.path.join(tmp, "wrap.cmd")
    with open(wrapper, "w", newline="\r\n") as f:
        f.write("\n".join(["@echo off", "call :getver \"%~1\" V", "echo [%V%]", "exit /b 0"] + lines[start:]) + "\n")

    def read(path):
        p = subprocess.run(["cmd", "/c", wrapper, path], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        return p.stdout.decode("utf-8", "replace").replace("\r", "").strip()

    good, bare = os.path.join(tmp, "harness.py"), os.path.join(tmp, "bare.py")
    with open(good, "w") as f:
        f.write('"""stub"""\nVERSION = "9.9"\n')
    with open(bare, "w") as f:
        f.write("x = 1\n")
    out = read(good)
    check("a harness.py with VERSION = \"9.9\" reads 9.9", out == "[9.9]", out)
    out = read(os.path.join(tmp, "missing.py"))
    check("a missing file reads none, and one without a version line reads unknown", out == "[none]" and read(bare) == "[unknown]", (out, read(bare)))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
