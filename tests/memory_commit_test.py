# /llm_harness/tests/memory_commit_test.py
"""Memory-commit test for llm_harness: in a git project the harness commits its project memory (goal, notes, verdicts, git policy) after a script changed it; it leaves them alone, with a note, on a protected branch and when .gitignore hides them, and does nothing in a project without git."""
import json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
BASE = tempfile.mkdtemp(prefix="harness-memory-")
RESULTS = []
STEP = [0]


def run(ws, *lines, **kw):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0]] + (["@SESSION %s | memory" % kw["session"]] if kw.get("session") else []) + ["@WORKSPACE " + ws]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def git(ws, *args):
    return subprocess.run(["git"] + list(args), cwd=ws, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode("utf-8", "replace").strip()


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    ws = os.path.join(BASE, "proj")
    os.makedirs(ws)
    with open(os.path.join(ws, "a.txt"), "w") as f:
        f.write("one\n")
    run(ws, "@GIT_INIT")
    git(ws, "config", "user.email", "t@t")
    git(ws, "config", "user.name", "t")
    run(ws, "@GIT_COMMIT chore: start", "/a.txt", "/.gitignore", "@END_GIT_COMMIT")
    main_branch = git(ws, "rev-parse", "--abbrev-ref", "HEAD")
    out = run(ws, "@NOTE_ADD Decision: keep the Go module boundary")
    check("a note is committed by the harness itself", "[MEMORY COMMITTED]" in out and git(ws, "log", "-1", "--format=%s") == "chore(harness): update project memory (notes.md)" and git(ws, "status", "--porcelain", "--", ".llm_harness/notes.md") == "", out)
    out = run(ws, "@GOAL Keep the harness reliable")
    check("a goal is committed too", "[MEMORY COMMITTED]" in out and "goal.md" in git(ws, "log", "-1", "--format=%s"), out)
    out = run(ws, "@GREP one")
    check("a script that changed no memory commits nothing", "[MEMORY" not in out, out)
    out = run(ws, "@VERDICT /a.txt | done | fine as it is", session="alpha")
    check("a verdict is committed", "[MEMORY COMMITTED]" in out and "verdicts.json" in git(ws, "log", "-1", "--format=%s"), out)
    with open(os.path.join(ws, ".llm_harness", "git.json"), "w") as f:
        json.dump({"version": 1, "protected": [main_branch]}, f)
    out = run(ws, "@NOTE_ADD Env: the test browser is at port 9222")
    check("on a protected branch the memory is left uncommitted, with a note", "[MEMORY]" in out and "protected branch" in out and "[MEMORY COMMITTED]" not in out and git(ws, "status", "--porcelain", "--", ".llm_harness/notes.md") != "", out)
    git(ws, "checkout", "-q", "-b", "feature/x")
    out = run(ws, "@NOTE_ADD Bug: video freezes at a random frame")
    log = git(ws, "show", "--stat", "--format=%s", "HEAD")
    check("on a feature branch the pending memory, git policy included, is committed", "[MEMORY COMMITTED]" in out and "git.json" in log and "notes.md" in log, out + log)
    hidden = os.path.join(BASE, "hidden")
    os.makedirs(hidden)
    with open(os.path.join(hidden, ".gitignore"), "w") as f:
        f.write(".llm_harness/*\n")
    with open(os.path.join(hidden, "a.txt"), "w") as f:
        f.write("one\n")
    git(hidden, "init", "-q")
    git(hidden, "config", "user.email", "t@t")
    git(hidden, "config", "user.name", "t")
    git(hidden, "add", ".")
    git(hidden, "commit", "-q", "-m", "chore: start")
    out = run(hidden, "@NOTE_ADD Env: something worth keeping")
    check("memory hidden by .gitignore is reported, not forced in", "is ignored by .gitignore" in out and "[MEMORY COMMITTED]" not in out, out)
    plain = os.path.join(BASE, "plain")
    os.makedirs(plain)
    out = run(plain, "@NOTE_ADD Env: no git here")
    check("a project without git is left alone", "[MEMORY" not in out, out)
    print("test workspace: " + BASE)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
