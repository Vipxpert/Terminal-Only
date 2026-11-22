# /llm_harness/tests/branch_tokens_test.py
"""Branch-switch test for llm_harness: @GIT_BRANCH switches to a branch whose committed tokens.json differs from this one's while the local tokens.json is modified (it changes with every paste and is never committed alone), and keeps the local counts, as @GIT_PULL does."""
import json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def TOK(n):
    return json.dumps({"buckets": {"acct@m": {"tokens": n, "pastes": 1, "chars": n * 4, "sessions": {}}}})


def git(ws, *args):
    p = subprocess.run(["git"] + list(args), cwd=ws, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.decode("utf-8", "replace").strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(text)


def main():
    ws = tempfile.mkdtemp(prefix="harness-branchtok-")
    tokens = os.path.join(ws, ".llm_harness", "tokens.json")
    git(ws, "init", "-q")
    git(ws, "checkout", "-q", "-b", "main")
    git(ws, "config", "user.email", "t@example.com")
    git(ws, "config", "user.name", "T")
    write(os.path.join(ws, "a.txt"), "x\n")
    write(tokens, TOK(10))
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", "init")
    git(ws, "branch", "b")
    write(tokens, TOK(40))
    git(ws, "commit", "-q", "-am", "main moves on")
    write(tokens, TOK(25))
    text = "@SCRIPT [C: switch]\n@WORKSPACE %s\n@GIT_BRANCH b\n" % ws
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    out = p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]
    head = git(ws, "rev-parse", "--abbrev-ref", "HEAD")
    check("@GIT_BRANCH switches although only tokens.json is modified locally and the branches hold different committed counts", head == "b", out + "\n" + git(ws, "status", "--short"))
    try:
        with open(tokens, "r", encoding="utf-8") as f:
            kept = json.load(f)["buckets"]["acct@m"]["tokens"]
    except (OSError, ValueError, KeyError) as exc:
        kept = repr(exc)
    check("the local counts survive the switch and the file stays uncommitted", kept == 25 and git(ws, "status", "--short").startswith("M"), (kept, git(ws, "status", "--short")))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
