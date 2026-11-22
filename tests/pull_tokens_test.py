# /llm_harness/tests/pull_tokens_test.py
"""Pull test for llm_harness: @GIT_PULL fast-forwards a checkout whose only local change is the harness's own tokens.json, even when the incoming commits changed tokens.json too (two machines pushing their token counts)."""
import json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def TOK(n):
    """A tokens.json document with one bucket holding n tokens."""
    return json.dumps({"buckets": {"acct@m": {"tokens": n, "pastes": 1, "chars": n * 4, "sessions": {}}}})


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def git(cwd, *args):
    p = subprocess.run(["git"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.decode("utf-8", "replace").strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(text)


def main():
    root = tempfile.mkdtemp(prefix="harness-pull-")
    remote, a, b = (os.path.join(root, n) for n in ("remote.git", "a", "b"))
    git(root, "init", "-q", "--bare", remote)
    git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    os.makedirs(a)
    git(a, "init", "-q")
    git(a, "checkout", "-q", "-b", "main")
    for repo in (a,):
        git(repo, "config", "user.email", "t@example.com")
        git(repo, "config", "user.name", "T")
    write(os.path.join(a, "a.txt"), "x\n")
    write(os.path.join(a, ".llm_harness", "tokens.json"), TOK(10))
    git(a, "add", "-A")
    git(a, "commit", "-q", "-m", "init")
    git(a, "remote", "add", "origin", remote)
    git(a, "push", "-q", "-u", "origin", "main")
    git(root, "clone", "-q", remote, b)
    git(b, "config", "user.email", "t@example.com")
    git(b, "config", "user.name", "T")
    write(os.path.join(b, ".llm_harness", "tokens.json"), TOK(40))
    git(b, "commit", "-q", "-am", "other machine's token counts")
    git(b, "push", "-q", "origin", "main")
    write(os.path.join(a, ".llm_harness", "tokens.json"), TOK(25))
    text = "@SCRIPT [C: pull]\n@WORKSPACE %s\n@GIT_PULL\n" % a
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    out = p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]
    check("@GIT_PULL fast-forwards although only tokens.json is modified locally and the incoming commit changed it too", git(a, "rev-parse", "HEAD") == git(b, "rev-parse", "HEAD"), out + "\n" + git(a, "status", "--short"))
    try:
        with open(os.path.join(a, ".llm_harness", "tokens.json"), "r", encoding="utf-8") as f:
            merged = json.load(f)["buckets"]["acct@m"]["tokens"]
    except (OSError, ValueError, KeyError) as exc:
        merged = repr(exc)
    check("the local and incoming counts are merged (25 + 40 - 10 = 55) and the file stays uncommitted", merged == 55 and git(a, "status", "--short").startswith("M"), (merged, git(a, "status", "--short")))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
