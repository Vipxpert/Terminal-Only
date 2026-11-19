# /llm_harness/tests/git_push_test.py
"""Push test for llm_harness: @GIT_PUSH publishes the current branch (setting its upstream the first time) or one tag to a remote; it is never forced, never takes a protected branch, reports a rejected push without overriding it, and a raw git push through @RUN is still refused."""
import json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
BASE = tempfile.mkdtemp(prefix="harness-push-")
RESULTS = []
STEP = [0]


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.stdout.decode("utf-8", "replace").strip()


def run(ws, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + ws]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def put(ws, rel, text="x\n"):
    with open(os.path.join(ws, rel), "w") as f:
        f.write(text)


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-900:].replace("\n", "\n    "))


def main():
    origin, proj, other = (os.path.join(BASE, n) for n in ("origin.git", "proj", "other"))
    git(BASE, "init", "-q", "--bare", origin)
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    os.makedirs(proj)
    git(proj, "init", "-q")
    git(proj, "checkout", "-q", "-b", "main")
    put(proj, "a.txt")
    git(proj, "add", ".")
    git(proj, "commit", "-q", "-m", "chore: start")
    git(proj, "remote", "add", "origin", origin)
    git(proj, "push", "-q", "-u", "origin", "main")
    put(proj, "b.txt")
    out = run(proj, "@GIT_COMMIT feat(b): add b", "/b.txt", "@END_GIT_COMMIT", "@GIT_PUSH")
    check("a commit and its push in one script: the remote has it", "[COMMITTED]" in out and "[PUSHED] main -> origin/main" in out and "feat(b): add b" in git(origin, "log", "--oneline", "main"), out)
    out = run(proj, "@GIT_PUSH")
    check("nothing to push is said, not an error", "nothing to push" in out and "[PUSH REFUSED]" not in out, out)
    git(BASE, "clone", "-q", origin, other)
    put(other, "o.txt")
    git(other, "add", ".")
    git(other, "commit", "-q", "-m", "feat(o): from the other device")
    git(other, "push", "-q", "origin", "main")
    put(proj, "c.txt")
    out = run(proj, "@GIT_COMMIT feat(c): add c", "/c.txt", "@END_GIT_COMMIT", "@GIT_PUSH")
    remote_log = git(origin, "log", "--oneline", "main")
    check("a push the remote would reject is reported and never forced", "[PUSH REJECTED]" in out and "feat(c): add c" not in remote_log and "feat(o)" in remote_log, out + remote_log)
    git(proj, "pull", "-q", "--rebase", "origin", "main")
    out = run(proj, "@GIT_PUSH")
    check("after the user brings the remote's commits in, the push goes through", "[PUSHED]" in out and "feat(c): add c" in git(origin, "log", "--oneline", "main"), out)
    put(proj, "d.txt")
    git(proj, "add", ".")
    git(proj, "commit", "-q", "-m", "feat(d): direct on main")
    os.makedirs(os.path.join(proj, ".llm_harness"), exist_ok=True)
    with open(os.path.join(proj, ".llm_harness", "git.json"), "w") as f:
        json.dump({"version": 1, "protected": ["main"]}, f)
    out = run(proj, "@GIT_PUSH")
    check("a protected branch is not pushed", "[PUSH REFUSED]" in out and "protected branch" in out and "feat(d)" not in git(origin, "log", "--oneline", "main"), out)
    out = run(proj, "@GIT_BRANCH feature/x")
    put(proj, "e.txt")
    out = run(proj, "@GIT_COMMIT feat(e): add e", "/e.txt", "@END_GIT_COMMIT", "@GIT_PUSH")
    check("a feature branch is pushed and gets its upstream", "[PUSHED] feature/x -> origin/feature/x" in out and git(origin, "branch", "--list", "feature/x") != "" and git(proj, "rev-parse", "--abbrev-ref", "@{u}") == "origin/feature/x", out)
    out = run(proj, "@GIT_TAG v1.0.0 | first")
    out = run(proj, "@GIT_PUSH tag v1.0.0")
    check("a tag is pushed by name", "[PUSHED] tag v1.0.0" in out and "v1.0.0" in git(origin, "tag", "--list"), out)
    out = run(proj, "@GIT_PUSH tag v9.9.9")
    check("a tag that does not exist is refused", "[PUSH REFUSED]" in out and "no tag v9.9.9" in out, out)
    out = run(proj, "@GIT_PUSH --force")
    check("nothing but the branch or one tag can be asked for: no force", "[PUSH REFUSED]" in out and "use '@GIT_PUSH'" in out, out)
    out = run(proj, "@RUN git push")
    check("a raw git push through @RUN is still refused, pointing to @GIT_PUSH", "[REFUSED]" in out and "@GIT_PUSH" in out, out)
    lone = os.path.join(BASE, "lone")
    os.makedirs(lone)
    git(lone, "init", "-q")
    put(lone, "a.txt")
    git(lone, "add", ".")
    git(lone, "commit", "-q", "-m", "chore: start")
    out = run(lone, "@GIT_PUSH")
    check("without a remote the push is refused with the way to add one", "[PUSH REFUSED]" in out and "no remote" in out, out)
    print("test workspace: " + BASE)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
