# /llm_harness/tests/git_mode_test.py
"""Git-mode test for llm_harness: a project without git says so in every footer and leaves out the git rules; when it becomes a git repository, each chat is told once and the newly applying rules are marked [NEW] once."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-gitmode-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [P: step %d]" % STEP[0], "@SESSION alpha | try modes", "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-900:].replace("\n", "\n    "))


def main():
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("some text\n")
    out = run("@GREP some")
    check("a project without git says so in the footer and leaves out the git rules", "=== NO GIT HERE" in out and "[L1-Git Gate]" not in out, out)
    run("@GIT_INIT")
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git"] + args, cwd=WS)
    out = run("@GREP some")
    check("the first run after the switch to git greets once and marks the git rule [NEW]", "this project now uses git" in out and "[NEW] [L1-Git Gate]" in out and "=== NO GIT HERE" not in out, out)
    out = run("@GREP some")
    check("the greeting and the mark appear only once", "this project now uses git" not in out and "[NEW]" not in out and "[L1-Git Gate]" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
