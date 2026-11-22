# /llm_harness/tests/hollow_git_test.py
"""Hollow-repository test for llm_harness: a .git folder with no repository inside (no HEAD, only harness state) is not a git repository, so the run says NO GIT HERE and @GIT_INIT creates a real one; a run in a folder without git never leaves a .git folder behind."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, *lines):
    text = "\n".join(["@SCRIPT [C: hollow]", "@WORKSPACE " + ws] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def real_repo(ws):
    return subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ws, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0


def main():
    plain = tempfile.mkdtemp(prefix="harness-nogit-")
    run(plain, "@LIST_DIR /")
    check("a run in a folder without git leaves no .git folder behind", not os.path.exists(os.path.join(plain, ".git")), os.listdir(plain))
    hollow = tempfile.mkdtemp(prefix="harness-hollow-")
    os.makedirs(os.path.join(hollow, ".git", "llm_harness"))
    out = run(hollow, "@LIST_DIR /")
    check("a .git folder with no repository inside is not taken for git: the run says NO GIT HERE", "NO GIT HERE" in out and not real_repo(hollow), [l[:160] for l in out.split("\n") if "Workspace:" in l or "NO GIT HERE" in l])
    out = run(hollow, "@GIT_INIT")
    check("@GIT_INIT turns it into a real repository instead of saying it is one already", real_repo(hollow) and "already a git repository" not in out, out.split("=== L1 CONTRACT")[0][-700:])
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
