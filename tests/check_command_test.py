# /llm_harness/tests/check_command_test.py
"""Check-command test for llm_harness: the user's own check command (set with the terminal command --check, kept on this machine for this project only) runs after a change to a file of that type and only reports; a script cannot set it, a failing command rolls nothing back, and a clear removes it."""
import os, shutil, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-check-")
STORE = os.path.join(tempfile.mkdtemp(prefix="harness-checkstore-"), "checks.json")
ENV = dict(os.environ, LLM_HARNESS_CHECKS=STORE)
RESULTS = []
STEP = [0]
PY = "python" if shutil.which("python") else "python3"


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def user(*args):
    p = subprocess.run([sys.executable, HARNESS, "--workspace", WS] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ENV, stdin=subprocess.DEVNULL)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=ENV)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def edit(path, old, new):
    return run("@FILE /" + path, "@HUNK TOP | edit", "--- [OLD CODE] ---", old, "+++ [NEW CODE] +++", new, "=== [END HUNK] ===")


def main():
    for name, body in (("ok.py", "print('all good')\n"), ("bad.py", "import sys\nprint('boom: the build is broken')\nsys.exit(3)\n"), ("a.cs", "class A { }\n")):
        with open(os.path.join(WS, name), "w", newline="\n") as f:
            f.write(body)
    out = user("--check", ".cs", PY, "ok.py")
    check("the user's terminal command sets a check command", "CHECK SET" in out and ".cs" in out, out)
    out = user("--check")
    check("without arguments it lists them", ".cs -> %s ok.py" % PY in out, out)
    out = edit("a.cs", "class A { }", "class A { int x; }")
    check("a change to a file of that type runs the command and reports PASS", "PASS (project check: %s ok.py)" % PY in out, out)
    user("--check", ".cs", PY, "bad.py")
    out = edit("a.cs", "class A { int x; }", "class A { int y; }")
    with open(os.path.join(WS, "a.cs")) as f:
        kept = f.read()
    check("a failing command is reported with its output and rolls nothing back", "CHECK FAILED" in out and "boom: the build is broken" in out and "class A { int y; }" in kept, out + kept)
    out = run("@RUN %s %s --workspace %s --check .cs calc" % (PY, HARNESS.replace("\\", "/"), WS.replace("\\", "/")))
    check("a script cannot set it", "[REFUSED]" in out and "--check" in out, out)
    with open(os.path.join(WS, "b.py"), "w") as f:
        f.write("x = 1\n")
    out = edit("b.py", "x = 1", "x = 2")
    check("other file types are not affected", "project check" not in out and "CHECK" not in out.split("EXECUTION SCORECARD")[-1], out)
    user("--check", ".cs", "--clear")
    out = edit("a.cs", "class A { int y; }", "class A { int z; }")
    check("a cleared command no longer runs", "project check" not in out and "CHECK FAILED" not in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
