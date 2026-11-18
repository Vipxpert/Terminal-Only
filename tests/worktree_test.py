# /llm_harness/tests/worktree_test.py
"""Worktree test for llm_harness: a git worktree (where .git is a file) runs in git mode, shares script numbering with the main checkout, and keeps its own sessions, scopes and undo journal."""
import os, shutil, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
BASE = tempfile.mkdtemp(prefix="harness-worktree-")
MAIN = os.path.join(BASE, "proj")
WT = os.path.join(BASE, "proj.feature-a")
RESULTS = []
STEP = [0]


def run(ws, session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0]] + (["@SESSION " + session] if session else []) + ["@WORKSPACE " + ws]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def git(cwd, *args):
    return subprocess.run(["git"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode("utf-8", "replace").strip()


def hunk(path, old, new):
    return ["@FILE " + path, "@HUNK TOP | e", "--- [OLD CODE] ---", old, "+++ [NEW CODE] +++", new, "=== [END HUNK] ==="]


def read(ws, rel):
    with open(os.path.join(ws, rel), encoding="utf-8") as f:
        return f.read()


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    os.makedirs(MAIN)
    with open(os.path.join(MAIN, "a.txt"), "w") as f:
        f.write("shared line one\n")
    run(MAIN, None, "@GIT_INIT")
    git(MAIN, "config", "user.email", "t@t")
    git(MAIN, "config", "user.name", "t")
    run(MAIN, None, "@GIT_COMMIT chore: start", "/a.txt", "/.gitignore", "@END_GIT_COMMIT")
    git(MAIN, "worktree", "add", "-q", "-b", "feature/a", WT)
    out = run(WT, None, "@GREP shared")
    check("a worktree runs in git mode and says it is a worktree", "git mode, worktree" in out and "no-git" not in out, out)
    check("it continues the main checkout's numbering", "[ASSIGNED] C-3" in out, out)
    out = run(MAIN, None, "@GREP shared")
    check("the main checkout continues after the worktree's number", "[ASSIGNED] C-4" in out, out)
    run(MAIN, "alpha | main work", "@SCOPE a | a.txt")
    out = run(WT, "beta | feature work", "@SCOPE a | a.txt", *hunk("/a.txt", "shared line one", "feature line one"))
    check("a claim in one checkout does not block the same path in another", "scope set" in out and "[OK] /a.txt" in out and "shared line one" in read(MAIN, "a.txt"), out)
    num = STEP[0]
    out = run(WT, "beta | feature work", "@UNDO %d" % num)
    check("undo in the worktree restores the worktree's own file", "shared line one" in read(WT, "a.txt"), out)
    print("test workspace: " + BASE)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
