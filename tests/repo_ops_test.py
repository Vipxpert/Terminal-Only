# /llm_harness/tests/repo_ops_test.py
"""Repository-operation test for llm_harness: @GIT_BRANCH, @GIT_WORKTREE and @GIT_TAG go through one safety guard (no local changes, no unfinished git operation, no other active chat in the checkout) and the project's git.json policy."""
import json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
BASE = tempfile.mkdtemp(prefix="harness-repoops-")
WS = os.path.join(BASE, "proj")
RESULTS = []
STEP = [0]


def run(session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [G: step %d]" % STEP[0]] + (["@SESSION " + session] if session else []) + ["@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=WS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode("utf-8", "replace").strip()


def write(rel, text):
    with open(os.path.join(WS, rel), "w") as f:
        f.write(text)


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    os.makedirs(WS)
    write("a.txt", "one\n")
    run(None, "@GIT_INIT")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    run(None, "@GIT_COMMIT chore: start", "/a.txt", "/.gitignore", "@END_GIT_COMMIT")
    main_branch = git("rev-parse", "--abbrev-ref", "HEAD")
    write(os.path.join(".llm_harness", "git.json"), json.dumps({"version": 1, "branches": "^(feature|fix)/.+$", "tags_from": main_branch, "tag_changelog": True}))
    git("add", ".llm_harness/git.json")
    git("commit", "-q", "-m", "chore: git policy")
    out = run(None, "@GIT_BRANCH feature/x")
    check("a new branch is created from the current one", "[BRANCH] now on feature/x (new, from %s)" % main_branch in out and git("rev-parse", "--abbrev-ref", "HEAD") == "feature/x", out)
    write("a.txt", "changed\n")
    out = run(None, "@GIT_BRANCH " + main_branch)
    check("switching with local changes is refused", "[BRANCH REFUSED]" in out and "uncommitted" in out and git("rev-parse", "--abbrev-ref", "HEAD") == "feature/x", out)
    git("checkout", "--", "a.txt")
    out = run(None, "@GIT_BRANCH wip")
    check("a new branch outside the project's pattern is refused", "[BRANCH REFUSED] wip does not match" in out, out)
    out = run(None, "@GIT_WORKTREE add feature/y from " + main_branch)
    wt = os.path.join(BASE, "proj.feature-y")
    check("a worktree gets its own folder and the @WORKSPACE line to continue there", "[WORKTREE]" in out and "@WORKSPACE " + wt in out and os.path.isfile(os.path.join(wt, "a.txt")), out)
    out = run(None, "@GIT_WORKTREE list")
    check("the worktree list shows it", "proj.feature-y" in out, out)
    out = run(None, "@GIT_WORKTREE remove feature/y")
    check("a clean worktree is removed, its branch kept", "[WORKTREE] removed" in out and not os.path.isdir(wt) and git("rev-parse", "--verify", "-q", "refs/heads/feature/y") != "", out)
    out = run(None, "@GIT_BRANCH " + main_branch)
    check("an existing branch is switched to", "[BRANCH] now on %s" % main_branch in out and "(new" not in out, out)
    out = run(None, "@GIT_TAG 1.0")
    check("a tag that is not a version is refused", "not a version tag" in out, out)
    out = run(None, "@GIT_TAG v1.0.0")
    check("a required changelog section is checked", "has no '## 1.0.0' section" in out, out)
    write("CHANGELOG.md", "# Changes\n\n## 1.0.0\n- first\n")
    run(None, "@GIT_COMMIT docs: changelog for 1.0.0", "/CHANGELOG.md", "@END_GIT_COMMIT")
    out = run(None, "@GIT_TAG v1.0.0 | first release")
    check("a release tag is created, and pushing it is left to the user", "[TAGGED] v1.0.0" in out and "git push origin v1.0.0" in out and git("tag") == "v1.0.0", out)
    out = run(None, "@GIT_TAG v1.0.0")
    check("an existing tag is refused", "already exists" in out, out)
    run(None, "@GIT_BRANCH feature/x")
    write("b.txt", "feature\n")
    run(None, "@GIT_COMMIT feat: feature work", "/b.txt", "@END_GIT_COMMIT")
    out = run(None, "@GIT_TAG v1.1.0")
    check("a commit outside the tag branch's history is refused", "not part of %s's history" % main_branch in out, out)
    run("alpha | other work", "@GREP one")
    out = run("beta | switching", "@GIT_BRANCH " + main_branch)
    check("switching is refused while another chat is active in the checkout", "other chats are active in this checkout (alpha)" in out and git("rev-parse", "--abbrev-ref", "HEAD") == "feature/x", out)
    print("test workspace: " + BASE)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
