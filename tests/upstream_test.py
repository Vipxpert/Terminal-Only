# /llm_harness/tests/upstream_test.py
"""Upstream test for llm_harness: the footer's UPSTREAM line says what the remote has that this checkout lacks (sorted into inside your scope, project memory and other files) without changing any file; @GIT_PULL fast-forwards a clean checkout and bookmarks where it was, and refuses a dirty checkout, a diverged branch (naming conflicts from a dry-run merge) and a branch without an upstream."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
BASE = tempfile.mkdtemp(prefix="harness-upstream-")
RESULTS = []
STEP = [0]


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.stdout.decode("utf-8", "replace").strip()


def run(ws, *lines, **kw):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0]] + (["@SESSION alpha | try upstream"] if kw.get("session") else []) + ["@WORKSPACE " + ws]
    env = dict(os.environ, LLM_HARNESS_FETCH="0")
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=env)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def put(ws, rel, text):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path) or ws, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def get(ws, rel):
    with open(os.path.join(ws, rel)) as f:
        return f.read()


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
    for n in ("a.txt", "b.txt", "c.txt"):
        put(proj, n, "line one\nline two\n")
    git(proj, "add", ".")
    git(proj, "commit", "-q", "-m", "chore: start")
    git(proj, "remote", "add", "origin", origin)
    git(proj, "push", "-q", "-u", "origin", "main")
    git(BASE, "clone", "-q", origin, other)
    out = run(proj, session=True)
    check("level with the upstream: no UPSTREAM line", "=== UPSTREAM" not in out, out)
    put(other, "a.txt", "line one\nREMOTE two\n")
    put(other, "d.txt", "new\n")
    put(other, ".llm_harness/notes.md", "- [N001] a note from the other device\n")
    git(other, "add", "-f", ".")
    git(other, "commit", "-q", "-m", "feat(a): remote change")
    git(other, "push", "-q", "origin", "main")
    out = run(proj, "@SCOPE a | a.txt", session=True)
    check("incoming files are sorted: inside the scope, project memory, other files", "=== UPSTREAM: origin/main has 1 commit(s) this checkout lacks" in out and "INSIDE YOUR SCOPE: a.txt" in out and "project memory: .llm_harness/notes.md" in out and "other files: d.txt" in out, out)
    check("looking changes no file", get(proj, "a.txt") == "line one\nline two\n", "")
    out = run(proj)
    check("without a scope nothing is inside it", "=== UPSTREAM" in out and "INSIDE YOUR SCOPE:" not in out, out)
    put(proj, "dirty.txt", "x\n")
    out = run(proj, "@GIT_PULL", session=True)
    check("a pull is refused while the checkout has uncommitted changes", "[PULL REFUSED]" in out and "uncommitted" in out and get(proj, "a.txt").endswith("line two\n"), out)
    os.remove(os.path.join(proj, "dirty.txt"))
    out = run(proj, "@GIT_PULL", session=True)
    marks = git(proj, "for-each-ref", "refs/llm_harness/backup")
    check("a clean checkout fast-forwards and the files change", "[PULLED] fast-forwarded 1 commit(s) from origin/main" in out and "INSIDE YOUR SCOPE: a.txt" in out and "REMOTE two" in get(proj, "a.txt") and os.path.exists(os.path.join(proj, "d.txt")), out)
    check("the old position is bookmarked", "refs/llm_harness/backup/" in marks, marks)
    out = run(proj, "@GIT_PULL", session=True)
    check("pulling again says it is up to date", "already up to date" in out and "=== UPSTREAM" not in out, out)
    put(proj, "b.txt", "local one\nline two\n")
    git(proj, "commit", "-q", "-am", "feat(b): local change")
    put(other, "c.txt", "line one\nREMOTE c\n")
    git(other, "commit", "-q", "-am", "feat(c): remote change")
    git(other, "push", "-q", "origin", "main")
    before = git(proj, "rev-parse", "HEAD")
    out = run(proj, "@GIT_PULL", session=True)
    check("a diverged branch that would merge cleanly is reported, not merged", "[PULL REFUSED]" in out and "fast-forward is impossible" in out and "would be clean" in out and git(proj, "rev-parse", "HEAD") == before, out)
    put(proj, "a.txt", "LOCAL one\nREMOTE two\n")
    git(proj, "commit", "-q", "-am", "feat(a): local change")
    put(other, "a.txt", "REMOTE one\nREMOTE two\n")
    git(other, "commit", "-q", "-am", "feat(a): another remote change")
    git(other, "push", "-q", "origin", "main")
    before = git(proj, "rev-parse", "HEAD")
    out = run(proj, "@GIT_PULL", session=True)
    check("a diverged branch whose merge would conflict names the file and changes nothing", "[PULL REFUSED]" in out and "would conflict in: a.txt" in out and git(proj, "rev-parse", "HEAD") == before, out)
    lone = os.path.join(BASE, "lone")
    os.makedirs(lone)
    git(lone, "init", "-q")
    put(lone, "a.txt", "x\n")
    git(lone, "add", ".")
    git(lone, "commit", "-q", "-m", "chore: start")
    out = run(lone, "@GIT_PULL")
    check("a branch without an upstream is refused", "[PULL REFUSED]" in out and "no upstream" in out, out)
    git(proj, "remote", "set-url", "origin", os.path.join(BASE, "gone.git"))
    out = run(proj, session=True)
    check("when the remote cannot be reached the run stays quiet", "fatal" not in out.lower() and "error:" not in out.lower() and "Traceback" not in out, out)
    print("test workspace: " + BASE)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
