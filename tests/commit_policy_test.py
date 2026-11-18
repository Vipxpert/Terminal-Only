# /llm_harness/tests/commit_policy_test.py
"""Commit-policy test for llm_harness: @GIT_COMMIT messages must be type(scope): subject with a conventional type; an optional .llm_harness/git.json refuses commits on protected branches, limits header length and warns about branch names."""
import json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-commitpolicy-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [G: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=WS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode("utf-8", "replace").strip()


def commit(msg, n):
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("version %d\n" % n)
    return run("@GIT_COMMIT " + msg, "/a.txt", "@END_GIT_COMMIT")


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out.split("=== L1 CONTRACT")[0][-800:].replace("\n", "\n    "))


def main():
    run("@GIT_INIT")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    out = commit("update stuff", 1)
    check("a message without type(scope): subject is refused", "[COMMIT REFUSED]" in out and "type(scope): subject" in out and "[COMMITTED]" not in out, out)
    out = commit("feature: add a", 2)
    check("an unknown type is refused", "type 'feature' is not one of" in out and "[COMMITTED]" not in out, out)
    out = commit("feat(core): add a", 3)
    check("a conventional message commits", "[COMMITTED]" in out, out)
    main_branch = git("rev-parse", "--abbrev-ref", "HEAD")
    with open(os.path.join(WS, ".llm_harness", "git.json"), "w") as f:
        json.dump({"version": 1, "protected": [main_branch], "branches": "^(feature|fix)/.+$", "header_max": 30}, f)
    out = commit("fix: on the protected branch", 4)
    check("a commit on a protected branch is refused", "is a protected branch" in out and "[COMMITTED]" not in out, out)
    check("the footer names the branch as protected", "=== GIT POLICY: on branch %s (protected" % main_branch in out, out)
    git("checkout", "-q", "-b", "feature/a")
    out = commit("fix: a header that is far too long for the limit", 5)
    check("a header over the project's limit is refused", "allows at most 30" in out and "[COMMITTED]" not in out, out)
    out = commit("fix: short one", 6)
    check("a valid commit on a feature branch goes through", "[COMMITTED]" in out and "[BRANCH NAME]" not in out, out)
    git("checkout", "-q", "-b", "wip")
    out = commit("fix: on wip", 7)
    check("a branch name outside the pattern is warned about, not refused", "[BRANCH NAME] wip" in out and "[COMMITTED]" in out, out)
    with open(os.path.join(WS, ".llm_harness", "git.json"), "w") as f:
        f.write("{\"protected\": [\"wip\"]}")
    out = commit("fix: policy without a version", 8)
    check("a policy file without a version is ignored, with a note", "is ignored" in out and "[COMMITTED]" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
