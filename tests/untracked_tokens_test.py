# /llm_harness/tests/untracked_tokens_test.py
"""Untracked-memory test for llm_harness: a git project whose only uncommitted item is an untracked .llm_harness folder holding just tokens.json keeps the git rule folded, because the token counts change on every paste and are never committed alone."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def git(ws, *args):
    return subprocess.run(["git"] + list(args), cwd=ws, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def run(ws):
    text = "@SCRIPT [C: untracked tokens]\n@WORKSPACE %s\n" % ws
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def main():
    ws = tempfile.mkdtemp(prefix="harness-untracked-")
    git(ws, "init", "-q")
    git(ws, "config", "user.email", "t@example.com")
    git(ws, "config", "user.name", "T")
    with open(os.path.join(ws, "a.txt"), "w", newline="\n") as f:
        f.write("x\n")
    git(ws, "add", "a.txt")
    git(ws, "commit", "-q", "-m", "init")
    os.makedirs(os.path.join(ws, ".llm_harness"))
    with open(os.path.join(ws, ".llm_harness", "tokens.json"), "w", newline="\n") as f:
        f.write("{}\n")
    status = git(ws, "status", "--porcelain").stdout.decode("utf-8", "replace").strip()
    check("the scenario is real: git reports the untracked memory folder as the only change", status.startswith("??") and "a.txt" not in status, status)
    out = run(ws)
    check("the git rule stays folded when the only change is a lone untracked tokens.json", "[L1-Git Gate] (brief;" in out and "(expanded: uncommitted changes in workspace)" not in out, [l for l in out.split("\n") if l.startswith("[L1-Git Gate]")])
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
